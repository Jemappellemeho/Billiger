import logging

from rest_framework.response import Response
from rest_framework.views import APIView

from accounts.authentication import OptionalTokenAuthentication
from search import services
from search.location import InvalidLocation
from streaks.tracking import record_comparison

logger = logging.getLogger(__name__)


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
            zip_code = services.resolve_zip_code(request.query_params)
        except InvalidLocation as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            groups = services.search_products(query, zip_code)
        except Exception:
            return Response(
                {"detail": "Marktguru ist derzeit nicht erreichbar."}, status=502
            )

        return Response({"query": query, "zip_code": zip_code, "results": groups})


class CartComparisonView(APIView):
    """POST /api/compare/ {"items": [{"name", "brand"?, "quantity"?}], "zip_code"|"lat"+"lon"}

    For a full shopping list, returns (a) the cheapest single store that
    covers everything, (b) the full multi-store per-product-minimum split,
    and (c) the stepped ladder between them — see search.comparison for the
    actual calculation (Ticket 11). A signed-in caller's comparison also
    counts toward their weekly streak (Ticket 13, see streaks.tracking); a
    stale token is treated as a guest rather than rejected.
    """

    authentication_classes = [OptionalTokenAuthentication]

    def post(self, request):
        try:
            items = services.parse_compare_items(request.data.get("items"))
        except ValueError as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            zip_code = services.resolve_zip_code(request.data)
        except InvalidLocation as exc:
            return Response({"detail": str(exc)}, status=400)

        try:
            comparison = services.compare_items(items, zip_code)
        except Exception:
            return Response(
                {"detail": "Marktguru ist derzeit nicht erreichbar."}, status=502
            )

        if request.user.is_authenticated:
            try:
                record_comparison(request.user, comparison)  # counts toward the weekly streak
            except Exception:
                # The comparison itself succeeded; losing a streak tick must not cost the user it.
                logger.exception("Could not record comparison for the streak")

        return Response({"zip_code": zip_code, **comparison})
