"""What each of the assistant's three write actions changes (Ticket 15).

A `Change` knows one kind of proposal end to end: how to validate the
proposed input, which state it is compared against (`snapshot`), the diff
between the two, and how to apply it once the user accepts. Only these three
kinds exist — nothing account-sensitive (email, password, deletion, payment)
has a Change, so there is no path from the assistant to it, confirmed or not.
"""
from rest_framework import serializers

from accounts import shopping_list
from accounts.serializers import MAX_LIST_ITEMS, MAX_PREFERENCE_ENTRIES
from search import services
from search.location import InvalidLocation

PREFERENCE_KINDS = ("preferred_brands", "excluded_ingredients", "excluded_stores")


class ProposalInvalid(Exception):
    """The proposed input can't become a proposal; the message is meant for the model (and the user's edit form)."""


def _describe(errors, path=""):
    """DRF's nested error structure as one readable sentence."""
    if isinstance(errors, dict):
        return " ".join(_describe(value, f"{path}.{key}" if path else key) for key, value in errors.items())
    if isinstance(errors, list) and all(isinstance(entry, str) for entry in errors):
        return f"{path}: {' '.join(errors)}" if path else " ".join(errors)
    if isinstance(errors, list):
        return " ".join(_describe(entry, f"{path}[{index}]") for index, entry in enumerate(errors) if entry)
    return f"{path}: {errors}" if path else str(errors)


def _validated(serializer_class, data, allowed):
    if not isinstance(data, dict):
        raise ProposalInvalid("Die Eingabe muss ein Objekt sein.")
    unknown = sorted(set(data) - set(allowed))
    if unknown:
        raise ProposalInvalid(
            f"Unbekannte Felder: {', '.join(unknown)}. Erlaubt sind nur: {', '.join(allowed)}."
        )
    serializer = serializer_class(data=data)
    if not serializer.is_valid():
        raise ProposalInvalid(_describe(serializer.errors))
    return serializer.validated_data


def _unique(values):
    return list(dict.fromkeys(value.strip() for value in values if value.strip()))


def _summary(entry):
    return {"id": entry["id"], "name": entry["name"], "brand": entry["brand"]}


class _ItemSerializer(serializers.Serializer):
    name = serializers.CharField(max_length=200)
    brand = serializers.CharField(max_length=100, allow_null=True, allow_blank=True, required=False)
    quantity = serializers.IntegerField(min_value=1, max_value=999, default=1)
    # Left out = keep the category the row already has.
    category = serializers.CharField(max_length=100, allow_null=True, allow_blank=True, required=False)


class _ShoppingListSerializer(serializers.Serializer):
    items = _ItemSerializer(many=True, max_length=MAX_LIST_ITEMS)


class ShoppingListChange:
    """The whole new list at once: additions, removals and quantity changes as one diff."""

    kind = "shopping_list"
    fields = ("items",)

    def parse(self, data, user):
        current = {row["id"]: row for row in shopping_list.load(user)["items"]}
        items, seen = [], set()
        for raw in _validated(_ShoppingListSerializer, data, self.fields)["items"]:
            brand = (raw.get("brand") or "").strip() or None
            row_id = shopping_list.item_id(raw["name"], brand)
            if row_id in seen:
                raise ProposalInvalid(f"„{raw['name']}“ steht mehrfach in der Liste.")
            seen.add(row_id)
            existing = current.get(row_id)
            category = raw["category"] if "category" in raw else (existing["category"] if existing else None)
            items.append(
                {
                    "id": row_id,
                    "name": raw["name"].strip(),
                    "brand": brand,
                    "category": (category or "").strip() or None,
                    "favorite": existing["favorite"] if existing else False,
                    "quantity": raw["quantity"],
                }
            )
        return {"items": items}

    def snapshot(self, user, current_zip_code):
        return {"items": shopping_list.load(user)["items"]}

    def diff(self, base, proposed):
        old = {row["id"]: row for row in base["items"]}
        added, changed, unchanged = [], [], []
        for row in proposed["items"]:
            before = old.get(row["id"])
            if before is None:
                added.append(row)
                continue
            changes = {
                field: {"before": before[field], "after": row[field]}
                for field in ("quantity", "category")
                if before[field] != row[field]
            }
            if changes:
                changed.append({**_summary(row), "changes": changes})
            else:
                unchanged.append(row)
        new_ids = {row["id"] for row in proposed["items"]}
        removed = [row for row in base["items"] if row["id"] not in new_ids]
        return {"added": added, "removed": removed, "changed": changed, "unchanged": unchanged}

    def is_empty(self, diff):
        return not (diff["added"] or diff["removed"] or diff["changed"])

    def is_stale(self, user, base):
        return self.snapshot(user, None) != base

    def apply(self, user, proposed):
        document = shopping_list.load(user)
        return {"shopping_list": shopping_list.save(user, {**document, "items": proposed["items"]})}

    def accepted_message(self, proposed):
        return "✅ Einkaufsliste aktualisiert."


def _preference_entries():
    # Same limits as the stored preferences (accounts.serializers.PreferencesSerializer);
    # blanks are dropped by `_unique`.
    return serializers.ListField(
        child=serializers.CharField(max_length=100, allow_blank=True),
        max_length=MAX_PREFERENCE_ENTRIES,
        required=False,
    )


class _PreferencesSerializer(serializers.Serializer):
    preferred_brands = _preference_entries()
    excluded_ingredients = _preference_entries()
    excluded_stores = _preference_entries()
    favorite_items = serializers.ListField(
        child=serializers.CharField(max_length=400), max_length=MAX_LIST_ITEMS, required=False
    )


class PreferencesChange:
    """Preferences and favorites: each part that is sent is the complete new state of that part."""

    kind = "preferences"
    fields = (*PREFERENCE_KINDS, "favorite_items")

    def parse(self, data, user):
        parsed = _validated(_PreferencesSerializer, data, self.fields)
        if not parsed:
            raise ProposalInvalid(f"Nichts angegeben. Schicke mindestens eines von: {', '.join(self.fields)}.")

        proposed = {kind: _unique(parsed[kind]) for kind in PREFERENCE_KINDS if kind in parsed}
        if "favorite_items" in parsed:
            proposed["favorite_items"] = self._resolve_favorites(parsed["favorite_items"], user)
        return proposed

    def _resolve_favorites(self, references, user):
        rows = shopping_list.load(user)["items"]
        favorites = []
        for reference in _unique(references):
            wanted = reference.lower()
            matches = [row for row in rows if row["id"] == wanted] or [
                row for row in rows if row["name"].lower() == wanted
            ]
            if not matches:
                raise ProposalInvalid(
                    f"„{reference}“ steht nicht auf der Einkaufsliste. Nur Artikel der Liste können "
                    "Favoriten sein; ein neuer Artikel muss erst per Listen-Vorschlag hinzukommen."
                )
            if len(matches) > 1:
                ids = ", ".join(row["id"] for row in matches)
                raise ProposalInvalid(f"„{reference}“ ist mehrdeutig. Nenne die id: {ids}.")
            favorites.append(matches[0]["id"])
        return list(dict.fromkeys(favorites))

    def snapshot(self, user, current_zip_code):
        document = shopping_list.load(user)
        return {
            "preferences": document["preferences"],
            "favorites": [row["id"] for row in document["items"] if row["favorite"]],
            # Also part of the base: removing a favorite's row from the list makes the proposal stale.
            "items": [_summary(row) for row in document["items"]],
        }

    def diff(self, base, proposed):
        diff = {}
        for kind in PREFERENCE_KINDS:
            if kind not in proposed:
                continue
            old, new = base["preferences"][kind], proposed[kind]
            added = [entry for entry in new if entry not in old]
            removed = [entry for entry in old if entry not in new]
            if added or removed:
                diff[kind] = {"added": added, "removed": removed}
        if "favorite_items" in proposed:
            rows = {row["id"]: row for row in base["items"]}
            added = [rows[row_id] for row_id in proposed["favorite_items"] if row_id not in base["favorites"]]
            removed = [rows[row_id] for row_id in base["favorites"] if row_id not in proposed["favorite_items"]]
            if added or removed:
                diff["favorites"] = {"added": added, "removed": removed}
        return diff

    def is_empty(self, diff):
        return not diff

    def is_stale(self, user, base):
        return self.snapshot(user, None) != base

    def apply(self, user, proposed):
        document = shopping_list.load(user)
        preferences = {**document["preferences"], **{kind: proposed[kind] for kind in PREFERENCE_KINDS if kind in proposed}}
        items = document["items"]
        if "favorite_items" in proposed:
            favorites = set(proposed["favorite_items"])
            items = [{**row, "favorite": row["id"] in favorites} for row in items]
        return {"shopping_list": shopping_list.save(user, {"items": items, "preferences": preferences})}

    def accepted_message(self, proposed):
        return "✅ Präferenzen aktualisiert."


class _LocationSerializer(serializers.Serializer):
    zip_code = serializers.CharField()


class LocationChange:
    """A new PLZ. The location lives in the client, so accepting hands it back instead of storing it here."""

    kind = "location"
    fields = ("zip_code",)

    def parse(self, data, user):
        zip_code = _validated(_LocationSerializer, data, self.fields)["zip_code"]
        try:
            return {"zip_code": services.resolve_zip_code({"zip_code": zip_code})}
        except InvalidLocation as exc:
            raise ProposalInvalid(f"Ungültige Postleitzahl: {exc}") from exc

    def snapshot(self, user, current_zip_code):
        try:
            return {"zip_code": current_zip_code()}
        except Exception:
            # Deliberately broad: an unknown or unresolvable location (the resolver's own error type
            # lives in the tools layer) only means there is no "before" to show, never a failed proposal.
            return {"zip_code": None}

    def diff(self, base, proposed):
        before = base["zip_code"]
        return {
            "before": {"zip_code": before} if before else None,
            "after": {"zip_code": proposed["zip_code"]},
        }

    def is_empty(self, diff):
        return diff["before"] is not None and diff["before"] == diff["after"]

    def is_stale(self, user, base):
        return False  # nothing here to go stale: the location is not stored on the server

    def apply(self, user, proposed):
        return {"location": {"zip_code": proposed["zip_code"]}}

    def accepted_message(self, proposed):
        return f"✅ Standort auf PLZ {proposed['zip_code']} gesetzt."


CHANGES = {change.kind: change for change in (ShoppingListChange(), PreferencesChange(), LocationChange())}
