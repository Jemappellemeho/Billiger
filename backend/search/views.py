from django.conf import settings
from rest_framework.response import Response
from rest_framework.views import APIView

from search.anchor_products import apply_anchor_overrides
from search.location import InvalidLocation, LocationResolver
from search.marktguru_client import MarktguruClient
from search.matching import group_offers


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
            zip_code = self._resolve_zip_code(request)
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

    def _resolve_zip_code(self, request):
        zip_code_param = request.query_params.get("zip_code")
        lat_param = request.query_params.get("lat")
        lon_param = request.query_params.get("lon")
        try:
            lat = float(lat_param) if lat_param not in (None, "") else None
            lon = float(lon_param) if lon_param not in (None, "") else None
        except ValueError:
            raise InvalidLocation("lat/lon must be numeric.")
        return LocationResolver().resolve(zip_code=zip_code_param, lat=lat, lon=lon)

    def _marktguru_client(self):
        return MarktguruClient(
            api_key=getattr(settings, "MARKTGURU_API_KEY", None),
            client_key=getattr(settings, "MARKTGURU_CLIENT_KEY", None),
        )
