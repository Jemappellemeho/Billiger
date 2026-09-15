"""Manually maintained mapping table for frequently-compared anchor products.

Fuzzy matching (see matching.py) works from what Marktguru actually returns
per offer, so it misses cases where retailers describe the exact same
anchor product differently enough (e.g. one lists brand "Ferrero", another
"Nutella"). This table is the accepted, hand-maintained fallback the map/spec
calls for: highest matching confidence, highest maintenance cost, so it is
kept small and reserved for the products users compare most.

Add an anchor here only for products worth the manual upkeep (see
.scratch/billiger/research/01-marktguru-api-produktdaten.md, section 6).
"""
from difflib import SequenceMatcher

from search.matching import _cheapest, normalize_text

_ALIAS_SIMILARITY_THRESHOLD = 0.85

ANCHOR_PRODUCTS = [
    {
        "id": "nutella-750g",
        "brand_aliases": ["nutella", "ferrero"],
        "name_aliases": ["nutella", "nutella nuss nougat creme"],
        "quantity": {"amount": 750.0, "unit": "g"},
    },
    {
        "id": "red-bull-250ml",
        "brand_aliases": ["red bull"],
        "name_aliases": ["red bull energy drink", "red bull"],
        "quantity": {"amount": 250.0, "unit": "ml"},
    },
    {
        "id": "cola-1-5l",
        "brand_aliases": ["coca cola", "coca-cola"],
        "name_aliases": ["cola", "coca cola"],
        "quantity": {"amount": 1500.0, "unit": "ml"},
    },
]


def _alias_matches(value, aliases):
    if not value:
        return False
    for alias in aliases:
        if value == alias or SequenceMatcher(None, value, alias).ratio() >= _ALIAS_SIMILARITY_THRESHOLD:
            return True
    return False


def _anchor_for_group(group, anchors):
    brand = normalize_text(group.get("brand"))
    name = normalize_text(group.get("name"))
    quantity = group.get("normalized_quantity")
    for anchor in anchors:
        if anchor["quantity"] != quantity:
            continue
        if _alias_matches(brand, anchor["brand_aliases"]) or _alias_matches(name, anchor["name_aliases"]):
            return anchor["id"]
    return None


def _merge(groups):
    merged_offers = [offer for group in groups for offer in group["offers"]]
    base = groups[0]
    return {
        "brand": base["brand"],
        "name": base["name"],
        "categories": base["categories"],
        "normalized_quantity": base["normalized_quantity"],
        "offers": merged_offers,
        "cheapest": _cheapest(merged_offers),
    }


def anchor_id_for_offer_group(group, anchors=ANCHOR_PRODUCTS):
    """Public entry point for callers outside this module (e.g. search.tasks)
    that need to know which anchor, if any, a matched offer group is."""
    return _anchor_for_group(group, anchors)


def apply_anchor_overrides(groups, anchors=ANCHOR_PRODUCTS):
    """Merge fuzzy-matched groups that the anchor table says are the same product."""
    by_anchor = {}
    passthrough = []
    for group in groups:
        anchor_id = _anchor_for_group(group, anchors)
        if anchor_id is None:
            passthrough.append(group)
        else:
            by_anchor.setdefault(anchor_id, []).append(group)

    merged = [_merge(matched_groups) for matched_groups in by_anchor.values()]
    return merged + passthrough
