"""The search and cart-comparison operations behind `/api/search/` and `/api/compare/`.

The REST views and the built-in assistant (Ticket 14) both go through these,
so a price seen in the app and a price quoted by the assistant can't disagree.
Marktguru failures propagate as exceptions; each caller decides how to report them.
"""
from search.anchor_products import apply_anchor_overrides
from search.comparison import compare_cart, select_matching_group
from search.location import LocationResolver, InvalidLocation
from search.marktguru_client import client_from_django_settings
from search.matching import group_offers


MARKTGURU_UNAVAILABLE = "Marktguru ist derzeit nicht erreichbar."


def resolve_zip_code(source):
    """`source` is anything with a dict-like .get (query_params for GET, request.data for POST)."""
    zip_code_param = source.get("zip_code")
    lat_param = source.get("lat")
    lon_param = source.get("lon")
    try:
        lat = float(lat_param) if lat_param not in (None, "") else None
        lon = float(lon_param) if lon_param not in (None, "") else None
    except (TypeError, ValueError):
        raise InvalidLocation("lat/lon must be numeric.")
    return LocationResolver().resolve(zip_code=zip_code_param, lat=lat, lon=lon)


def search_products(query, zip_code, client=None):
    """Matched offer groups (cheapest offer per store) for a free-text product search."""
    client = client or client_from_django_settings()
    return apply_anchor_overrides(group_offers(client.search(query, zip_code=zip_code)))


def parse_compare_items(items_payload):
    """Validates the `items` of a comparison request; raises ValueError with a user-facing message."""
    if not isinstance(items_payload, list) or not items_payload:
        raise ValueError("'items' must be a non-empty list.")

    parsed = []
    for raw in items_payload:
        if not isinstance(raw, dict):
            raise ValueError("Every item must be an object with at least a 'name'.")
        name = (raw.get("name") or "").strip()
        if not name:
            raise ValueError("Every item needs a non-empty 'name'.")
        brand = (raw.get("brand") or "").strip() or None
        try:
            quantity = int(raw.get("quantity", 1))
        except (TypeError, ValueError):
            raise ValueError(f"'quantity' for '{name}' must be a positive integer.")
        if quantity < 1:
            raise ValueError(f"'quantity' for '{name}' must be a positive integer.")
        parsed.append({"name": name, "brand": brand, "quantity": quantity})
    return parsed


def compare_items(items, zip_code, client=None):
    """The cart comparison (see search.comparison) for parsed `items` (parse_compare_items)."""
    client = client or client_from_django_settings()
    return compare_cart([_with_offers(client, item, zip_code) for item in items])


def _with_offers(client, item, zip_code):
    query = f"{item['brand']} {item['name']}".strip() if item["brand"] else item["name"]
    groups = search_products(query, zip_code, client=client)
    matched = select_matching_group(groups, item["name"], item["brand"])
    offers = matched["offers"] if matched else []
    return {**item, "offers": offers}
