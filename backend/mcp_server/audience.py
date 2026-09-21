from django.conf import settings
from oauth2_provider.oauth2_validators import validate_resource_as_url_prefix


def validate_mcp_audience(request_uri, audiences):
    """django-oauth-toolkit's RFC 8707 hook (`RESOURCE_SERVER_TOKEN_RESOURCE_VALIDATOR`).

    The stock check compares a token's audiences with the URL the request happened to arrive
    on, which behind a proxy is not the public MCP URL. Here the token must name the configured
    `MCP_RESOURCE_URL` itself (or a URL prefix of it, like the whole origin), whatever host the
    request came in under.
    """
    return validate_resource_as_url_prefix(settings.MCP_RESOURCE_URL, audiences)
