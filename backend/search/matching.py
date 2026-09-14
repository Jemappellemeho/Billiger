"""Cross-retailer product matching for raw Marktguru offers.

Marktguru's own `product.id` is retailer-independent but too coarse to use as
a sole equality key: it clusters by search facette rather than exact sellable
unit (see .scratch/billiger/research/01-marktguru-api-produktdaten.md for the
Coca-Cola counterexample, where 0.33 l cans, 2 l bottles, and even Fanta/Sprite
mixed packs all share product.id=21896).

Strategy: `product.id` is used only as a weak prefilter to bucket candidates
for the first matching pass — never as the equality test itself, and never as
a gate. A second pass re-merges groups that agree on brand + normalized name +
normalized quantity even when their `product.id` differed, since Marktguru
does not guarantee that id is stable across retailers for the identical
product (see research doc, section 5).
"""
import re
from difflib import SequenceMatcher

_NAME_SIMILARITY_THRESHOLD = 0.85

_WEIGHT_UNITS_TO_GRAMS = {"kg": 1000.0, "g": 1.0}
_VOLUME_UNITS_TO_ML = {"l": 1000.0, "ml": 1.0}
_PIECE_UNITS = {"stk", "stück", "stueck", "st"}


def normalize_text(value):
    if not value:
        return ""
    value = value.lower()
    value = re.sub(r"[^a-z0-9äöüß\s]", " ", value)
    return re.sub(r"\s+", " ", value).strip()


def normalize_quantity(offer):
    """Convert an offer's unit/volume into a common base unit for comparison.

    Returns a dict {"amount": float, "unit": "g"|"ml"|"stk"} or None when the
    offer carries no usable quantity information at all.
    """
    unit = offer.get("unit") or {}
    short_name = normalize_text(unit.get("shortName"))
    volume = offer.get("volume")
    quantity = offer.get("quantity")

    if short_name in _WEIGHT_UNITS_TO_GRAMS and volume is not None:
        return {"amount": round(volume * _WEIGHT_UNITS_TO_GRAMS[short_name], 3), "unit": "g"}
    if short_name in _VOLUME_UNITS_TO_ML and volume is not None:
        return {"amount": round(volume * _VOLUME_UNITS_TO_ML[short_name], 3), "unit": "ml"}
    if short_name in _PIECE_UNITS and quantity is not None:
        return {"amount": float(quantity), "unit": "stk"}
    if quantity is not None:
        return {"amount": float(quantity), "unit": short_name or "stk"}
    return None


def _names_similar_enough(name_a, name_b):
    if name_a == name_b:
        return True
    return SequenceMatcher(None, name_a, name_b).ratio() >= _NAME_SIMILARITY_THRESHOLD


def _match_key_candidates(offer):
    """Everything needed to decide whether two offers describe the same product."""
    brand = normalize_text((offer.get("brand") or {}).get("name"))
    name = normalize_text((offer.get("product") or {}).get("name"))
    return brand, name, normalize_quantity(offer)


def _same_product(a, b):
    brand_a, name_a, qty_a = a
    brand_b, name_b, qty_b = b
    if brand_a != brand_b:
        return False
    if qty_a != qty_b:
        return False
    return _names_similar_enough(name_a, name_b)


def _cheapest(offers):
    return min(offers, key=lambda o: o["price"])


def group_offers(raw_offers):
    """Group raw Marktguru offers into cross-retailer matched products.

    Each returned group looks like:
        {
            "brand": str, "name": str, "categories": [str, ...],
            "normalized_quantity": dict | None,
            "offers": [{"advertiser": str, "price": float,
                        "old_price": float | None, "reference_price": float | None}],
            "cheapest": {"advertiser": str, "price": float},
        }
    """
    # Weak prefilter: bucket by product.id first (cheap, retailer-independent),
    # then split further within each bucket by the real equality check.
    buckets = {}
    for offer in raw_offers:
        product_id = (offer.get("product") or {}).get("id")
        buckets.setdefault(product_id, []).append(offer)

    groups = []
    for bucket in buckets.values():
        groups.extend(_cluster(bucket, key_fn=_match_key_candidates, build=_build_group))

    # product.id never gates equality — re-merge any groups from different
    # buckets that still agree on brand + name + quantity.
    return _cluster(groups, key_fn=_group_match_key, build=_merge_groups)


def _cluster(items, key_fn, build):
    """Generic single-linkage clustering: repeatedly pull an item out, collect
    everything left that matches it, and build one result per cluster."""
    remaining = list(items)
    clusters = []
    while remaining:
        seed = remaining.pop(0)
        seed_key = key_fn(seed)
        members = [seed]
        still_remaining = []
        for item in remaining:
            if _same_product(seed_key, key_fn(item)):
                members.append(item)
            else:
                still_remaining.append(item)
        remaining = still_remaining
        clusters.append(build(members))
    return clusters


def _group_match_key(group):
    return normalize_text(group["brand"]), normalize_text(group["name"]), group["normalized_quantity"]


def _build_group(members):
    brand_name = (members[0].get("brand") or {}).get("name")
    product_name = (members[0].get("product") or {}).get("name")
    categories = [c.get("name") for c in members[0].get("categories") or [] if c.get("name")]
    normalized_offers = [
        {
            "advertiser": (offer.get("advertisers") or [{}])[0].get("name"),
            "price": offer["price"],
            "old_price": offer.get("oldPrice"),
            "reference_price": offer.get("referencePrice"),
        }
        for offer in members
    ]
    return {
        "brand": brand_name,
        "name": product_name,
        "categories": categories,
        "normalized_quantity": normalize_quantity(members[0]),
        "offers": normalized_offers,
        "cheapest": _cheapest(normalized_offers),
    }


def _merge_groups(groups):
    base = groups[0]
    combined_offers = [offer for group in groups for offer in group["offers"]]
    return {
        "brand": base["brand"],
        "name": base["name"],
        "categories": base["categories"],
        "normalized_quantity": base["normalized_quantity"],
        "offers": combined_offers,
        "cheapest": _cheapest(combined_offers),
    }
