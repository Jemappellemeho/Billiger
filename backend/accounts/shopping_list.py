"""Server-side handling of the shopping-list document (see accounts.models.ShoppingList)."""

from accounts.models import ShoppingList
from accounts.serializers import MAX_LIST_ITEMS, MAX_PREFERENCE_ENTRIES


def empty_list():
    return {
        "items": [],
        "preferences": {
            "preferred_brands": [],
            "excluded_ingredients": [],
            "excluded_stores": [],
        },
    }


def load(user):
    stored = ShoppingList.objects.filter(user=user).first()
    return stored.data if stored else empty_list()


def save(user, data):
    ShoppingList.objects.update_or_create(user=user, defaults={"data": data})
    return data


def _union(first, second, limit):
    return list(dict.fromkeys([*first, *second]))[:limit]


def merge(stored, guest):
    """Merge a guest-mode list into an account's stored list.

    Nothing the account already has is lost or double-counted: stored rows
    stay first and in order, guest-only rows are appended, and rows present on
    both sides keep the larger quantity, so merging the same guest list a
    second time is a no-op.
    """
    items = [dict(entry) for entry in stored["items"]]
    by_id = {entry["id"]: entry for entry in items}
    for guest_item in guest["items"]:
        existing = by_id.get(guest_item["id"])
        if existing is None:
            copy = dict(guest_item)
            items.append(copy)
            by_id[copy["id"]] = copy
        else:
            existing["quantity"] = max(existing["quantity"], guest_item["quantity"])
            existing["favorite"] = existing["favorite"] or guest_item["favorite"]
            existing["category"] = existing["category"] or guest_item["category"]

    preferences = {
        kind: _union(stored["preferences"][kind], guest["preferences"][kind], MAX_PREFERENCE_ENTRIES)
        for kind in stored["preferences"]
    }
    return {"items": items[:MAX_LIST_ITEMS], "preferences": preferences}


def migrate_guest_list(user, guest):
    """First-login migration: fold the guest list (or nothing) into the account's list."""
    stored = load(user)
    if guest is None:
        return stored
    return save(user, merge(stored, guest))
