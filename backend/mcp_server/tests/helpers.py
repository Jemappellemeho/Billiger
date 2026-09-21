import base64
import hashlib
import json
import secrets
from urllib.parse import parse_qs, urlparse

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.cache import cache
from oauth2_provider.models import AccessToken
from rest_framework.test import APITestCase

from mcp_server.clients import CHATGPT_CLIENT_ID, CLAUDE_CLIENT_ID  # noqa: F401  (re-exported for the tests)

AUTHORIZE_URL = "/oauth/authorize/"
TOKEN_URL = "/oauth/token/"
MCP_URL = "/mcp/"
PASSWORD = "correct-horse-battery"


class McpTestCase(APITestCase):
    """A signed-in account, cleared throttle counters and the helpers to walk the OAuth flow."""

    def setUp(self):
        super().setUp()
        cache.clear()
        self.user = get_user_model().objects.create_user(
            username="anna@example.com", email="anna@example.com", password=PASSWORD
        )

    @property
    def resource(self):
        return settings.MCP_RESOURCE_URL

    def authorize(self, *, client_id=CLAUDE_CLIENT_ID, approve=True, challenge="use-pkce-pair", method="S256", **params):
        """The user's side of the flow: open the consent screen, then allow (or deny) it.

        Returns the final response: normally the redirect back to the client with a `code`.
        """
        query = {
            "response_type": "code",
            "client_id": client_id,
            "redirect_uri": settings.MCP_CLAUDE_REDIRECT_URI,
            "scope": "billiger:read",
            "state": "abc123",
            "resource": self.resource,
            **params,
        }
        if challenge == "use-pkce-pair":
            _, challenge = pkce_pair()
        if challenge is not None:
            query.update(code_challenge=challenge, code_challenge_method=method)
        query = {key: value for key, value in query.items() if value is not None}

        self.client.force_login(self.user)
        consent = self.client.get(AUTHORIZE_URL, query)
        if consent.status_code != 200:
            return consent
        return self.client.post(AUTHORIZE_URL, {**query, **({"allow": "Authorize"} if approve else {})})

    def exchange(self, code, verifier, *, client_id=CLAUDE_CLIENT_ID, **params):
        data = {
            "grant_type": "authorization_code",
            "code": code,
            "code_verifier": verifier,
            "client_id": client_id,
            "redirect_uri": settings.MCP_CLAUDE_REDIRECT_URI,
            "resource": self.resource,
            **params,
        }
        return self.client.post(TOKEN_URL, {k: v for k, v in data.items() if v is not None})

    def token_via_oauth(self, *, scope="billiger:read", authorize_resource="use-default", token_resource="use-default"):
        """The whole flow (PKCE included); returns the token endpoint's JSON."""
        verifier, challenge = pkce_pair()
        resource = self.resource if authorize_resource == "use-default" else authorize_resource
        redirect = self.authorize(scope=scope, resource=resource, challenge=challenge)
        assert redirect.status_code == 302, redirect.content
        response = self.exchange(
            code_from(redirect),
            verifier,
            resource=self.resource if token_resource == "use-default" else token_resource,
        )
        assert response.status_code == 200, response.content
        return response.json()

    def bearer(self, access_token):
        return {"HTTP_AUTHORIZATION": f"Bearer {access_token}"}

    def rpc(self, method, params=None, *, access_token=None, request_id=1, **extra):
        """One JSON-RPC message to the MCP endpoint (a notification when `request_id` is None)."""
        message = {"jsonrpc": "2.0", "method": method}
        if params is not None:
            message["params"] = params
        if request_id is not None:
            message["id"] = request_id
        headers = self.bearer(access_token) if access_token else {}
        return self.client.post(MCP_URL, json.dumps(message), content_type="application/json", **headers, **extra)

    def issue_token(self, *, scope="billiger:read billiger:write", resource="use-default", user=None, application=None):
        """An access token straight in the database (skips the flow when a test is about the MCP endpoint)."""
        from datetime import timedelta

        from django.utils import timezone

        return AccessToken.objects.create(
            user=user or self.user,
            application=application,
            token=secrets.token_urlsafe(32),
            scope=scope,
            expires=timezone.now() + timedelta(hours=1),
            resource=[self.resource] if resource == "use-default" else ([resource] if resource else []),
        ).token

    def call_tool(self, access_token, name, arguments=None):
        response = self.rpc("tools/call", {"name": name, "arguments": arguments or {}}, access_token=access_token)
        assert response.status_code == 200, response.content
        return response.json()["result"]


def pkce_pair():
    verifier = secrets.token_urlsafe(48)
    digest = hashlib.sha256(verifier.encode("ascii")).digest()
    return verifier, base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")


def code_from(redirect):
    return parse_qs(urlparse(redirect["Location"]).query)["code"][0]


def query_of(redirect):
    return {key: values[0] for key, values in parse_qs(urlparse(redirect["Location"]).query).items()}
