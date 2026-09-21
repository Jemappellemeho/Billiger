"""The OAuth clients Billiger pre-registers, one per external platform (no dynamic registration)."""
from django.conf import settings
from oauth2_provider.models import get_application_model

CLAUDE_CLIENT_ID = "billiger-claude"
CHATGPT_CLIENT_ID = "billiger-chatgpt"


def platform_clients():
    """The clients as configured: name, id and the one redirect URI each platform calls back to."""
    yield {"client_id": CLAUDE_CLIENT_ID, "name": "Claude", "redirect_uris": settings.MCP_CLAUDE_REDIRECT_URI}
    if settings.MCP_CHATGPT_REDIRECT_URI:
        yield {
            "client_id": CHATGPT_CLIENT_ID,
            "name": "ChatGPT",
            "redirect_uris": settings.MCP_CHATGPT_REDIRECT_URI,
        }


def ensure_clients(using="default", **_):
    """Creates the clients that are missing and re-syncs the others with the settings; returns their ids.

    Public clients: the platforms can't keep a secret, PKCE (required) is what binds a code to the
    client that asked for it.
    """
    Application = get_application_model()
    client_ids = []
    for client in platform_clients():
        Application.objects.using(using).update_or_create(
            client_id=client["client_id"],
            defaults={
                "name": client["name"],
                "redirect_uris": client["redirect_uris"],
                "client_type": Application.CLIENT_PUBLIC,
                "authorization_grant_type": Application.GRANT_AUTHORIZATION_CODE,
                "skip_authorization": False,
            },
        )
        client_ids.append(client["client_id"])
    return client_ids
