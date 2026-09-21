from collections import OrderedDict
from urllib.parse import urlparse

from django.conf import settings
from django.urls import reverse
from oauth2_provider.contrib.rest_framework import OAuth2ProtectedResourceAuthentication


class McpAuthentication(OAuth2ProtectedResourceAuthentication):
    """Bearer tokens issued by Billiger's own OAuth server, and only ones meant for the MCP endpoint.

    django-oauth-toolkit treats a token without any resource as valid for every resource server.
    That is the backwards-compatible default; here it would let a token that was never bound to
    Billiger's MCP endpoint through, so a token has to name it (RFC 8707). Whether the named
    resource is the right one is `mcp_server.audience`. A `401` carries the RFC 9728
    `resource_metadata` pointer that lets the client discover the authorization server.
    """

    www_authenticate_realm = "billiger-mcp"

    def get_resource_metadata_url(self, request):
        resource_path = urlparse(settings.MCP_RESOURCE_URL).path.strip("/")
        if resource_path:
            path = reverse("oauth2_provider:oauth-resource-metadata-path", kwargs={"resource_path": resource_path})
        else:
            path = reverse("oauth2_provider:oauth-resource-metadata")
        return request.build_absolute_uri(path)

    def authenticate(self, request):
        result = super().authenticate(request)
        if result is None:
            return None
        _, access_token = result
        if not access_token.resource:
            request.oauth2_error = OrderedDict(
                error="invalid_token",
                error_description="The access token was not issued for this resource.",
            )
            return None
        return result
