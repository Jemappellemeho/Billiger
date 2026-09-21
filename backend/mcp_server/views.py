from django.conf import settings
from django.http import HttpResponse, JsonResponse
from rest_framework.exceptions import PermissionDenied
from rest_framework.parsers import BaseParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.views import APIView

from mcp_server import protocol
from mcp_server.authentication import McpAuthentication


class RawBodyParser(BaseParser):
    """Hands the body over untouched: JSON-RPC answers a malformed body itself, with a JSON-RPC error."""

    media_type = "*/*"

    def parse(self, stream, media_type=None, parser_context=None):
        return stream.read()


class McpView(APIView):
    """POST /mcp/ — Billiger's MCP server (Streamable HTTP, JSON-RPC 2.0).

    Authenticated with an OAuth access token issued for this endpoint (`McpAuthentication`); the
    token's scopes decide which tools the client is offered. `tools/call` runs the REST endpoint
    behind the tool as the token's account (`mcp_server.tools`).
    """

    authentication_classes = [McpAuthentication]
    permission_classes = [IsAuthenticated]
    parser_classes = [RawBodyParser]

    def initial(self, request, *args, **kwargs):
        # The spec's DNS-rebinding guard: a browser page from an unknown origin may not talk to us.
        origin = request.headers.get("Origin")
        if origin and origin not in settings.MCP_ALLOWED_ORIGINS:
            raise PermissionDenied("Origin nicht erlaubt.")
        super().initial(request, *args, **kwargs)

    def post(self, request):
        message, failure = protocol.parse(request.data)
        if failure:
            return JsonResponse(failure, status=400)

        scopes = set(request.auth.scope.split())
        response = protocol.handle(message, request.user, scopes)
        if response is None:
            return HttpResponse(status=202)
        return JsonResponse(response, json_dumps_params={"ensure_ascii": False})
