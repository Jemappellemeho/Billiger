from rest_framework.response import Response
from rest_framework.views import APIView

from search.anchor_products import apply_anchor_overrides
from search.comparison import compare_cart, select_matching_group
from search.location import InvalidLocation, LocationResolver
from search.marktguru_client import client_from_django_settings
from search.matching import group_offers
from streaks.tracking import record_comparison


def _resolve_zip_code(source):
    """Shared by both views: `source` is anything with a dict-like .get
    (query_params for GET, request.data for POST)."""
    zip_code_param = source.get("zip_code")
    lat_param = source.get("lat")
    lon_param = source.get("lon")
    try:
        lat = float(lat_param) if lat_param not in (None, "") else None
        lon = float(lon_param) if lon_param not in (None, "") else None
    except (TypeError, ValueError):
        raise InvalidLocation("lat/lon must be numeric.")
    return LocationResolver().resolve(zip_code=zip_code_param, lat=lat, lon=lon)


class ProductSearchView(APIView):
    """GET /api/search/?q=<Freitext>&(zip_code=<PLZ>|lat=<>&lon=<>)

    Returns the cheapest offer per matched store for a free-text product
    search, without requiring the product to be added to any list.
    """

    def get(self, request):
        query = request.query_params.get("q", "").strip()
        if not query:
            return Response({"detail": "Query parameter 'q' is required."}, status=400)

        try:
            zip_code = _resolve_zip_code(request.query_params)
        except InvalidLocation as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            raw_offers = self._marktguru_client().search(query, zip_code=zip_code)
        except Exception:
            return Response(
                {"detail": "Marktguru ist derzeit nicht erreichbar."}, status=502
            )

        groups = group_offers(raw_offers)
        groups = apply_anchor_overrides(groups)
        return Response({"query": query, "zip_code": zip_code, "results": groups})

    def _marktguru_client(self):
        return client_from_django_settings()


class CartComparisonView(APIView):
    """POST /api/compare/ {"items": [{"name", "brand"?, "quantity"?}], "zip_code"|"lat"+"lon"}

    For a full shopping list, returns (a) the cheapest single store that
    covers everything, (b) the full multi-store per-product-minimum split,
    and (c) the stepped ladder between them — see search.comparison for the
    actual calculation (Ticket 11). A signed-in caller's comparison also
    counts toward their weekly streak (Ticket 13, see streaks.tracking).
    """

    def post(self, request):
        try:
            items = self._parse_items(request.data.get("items"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            zip_code = _resolve_zip_code(request.data)
        except InvalidLocation as exc:
            return Response({"detail": str(exc)}, status=400)

        client = self._marktguru_client()
        try:
            item_offers = [self._fetch_offers(client, item, zip_code) for item in items]
        except Exception:
            return Response(
                {"detail": "Marktguru ist derzeit nicht erreichbar."}, status=502
            )

        comparison = compare_cart(item_offers)
        if request.user.is_authenticated:
            record_comparison(request.user, comparison)  # counts toward the weekly streak

        return Response({"zip_code": zip_code, **comparison})

    def _parse_items(self, items_payload):
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

    def _fetch_offers(self, client, item, zip_code):
        query = f"{item['brand']} {item['name']}".strip() if item["brand"] else item["name"]
        raw_offers = client.search(query, zip_code=zip_code)
        groups = apply_anchor_overrides(group_offers(raw_offers))
        matched = select_matching_group(groups, item["name"], item["brand"])
        offers = matched["offers"] if matched else []
        return {**item, "offers": offers}

    def _marktguru_client(self):
        return client_from_django_settings()
