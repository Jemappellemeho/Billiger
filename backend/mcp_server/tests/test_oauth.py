from django.conf import settings
from django.test import override_settings
from oauth2_provider.models import Application

from mcp_server.tests.helpers import (
    CHATGPT_CLIENT_ID,
    CLAUDE_CLIENT_ID,
    McpTestCase,
    code_from,
    pkce_pair,
    query_of,
)


class RegisteredClientsTests(McpTestCase):
    def test_claude_has_one_fixed_client_with_its_fixed_redirect_uri(self):
        claude = Application.objects.get(client_id=CLAUDE_CLIENT_ID)
        self.assertEqual(claude.redirect_uris, "https://claude.ai/api/mcp/auth_callback")
        self.assertEqual(claude.authorization_grant_type, Application.GRANT_AUTHORIZATION_CODE)

    def test_chatgpt_client_only_exists_once_its_redirect_uri_is_configured(self):
        self.assertFalse(Application.objects.filter(client_id=CHATGPT_CLIENT_ID).exists())

    def test_a_redirect_uri_other_than_the_registered_one_is_refused(self):
        response = self.authorize(redirect_uri="https://evil.example/callback")
        self.assertEqual(response.status_code, 400)

    def test_there_is_no_dynamic_client_registration(self):
        response = self.client.post("/register/", {"redirect_uris": ["https://evil.example/cb"]}, format="json")
        self.assertEqual(response.status_code, 404)
        self.assertNotIn("registration_endpoint", self.client.get("/.well-known/oauth-authorization-server").json())

    def test_the_stock_application_and_token_management_screens_are_not_exposed(self):
        self.client.force_login(self.user)
        for path in ("/oauth/applications/", "/oauth/applications/register/", "/oauth/authorized_tokens/"):
            self.assertEqual(self.client.get(path).status_code, 404, path)


class AuthorizationCodeFlowTests(McpTestCase):
    def test_the_full_flow_issues_a_token_bound_to_the_mcp_resource(self):
        token = self.token_via_oauth(scope="billiger:read billiger:write")

        self.assertEqual(token["token_type"], "Bearer")
        self.assertEqual(set(token["scope"].split()), {"billiger:read", "billiger:write"})
        self.assertIn("refresh_token", token)

    def test_the_consent_screen_needs_a_signed_in_account(self):
        _, challenge = pkce_pair()
        response = self.client.get(
            "/oauth/authorize/",
            {
                "response_type": "code",
                "client_id": CLAUDE_CLIENT_ID,
                "redirect_uri": settings.MCP_CLAUDE_REDIRECT_URI,
                "code_challenge": challenge,
                "code_challenge_method": "S256",
            },
        )
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].startswith("/accounts/login/"))

    def test_denying_the_consent_screen_issues_no_code(self):
        response = self.authorize(approve=False)
        self.assertEqual(response.status_code, 302)
        self.assertEqual(query_of(response)["error"], "access_denied")
        self.assertNotIn("code", query_of(response))


class PkceTests(McpTestCase):
    def test_an_authorization_request_without_a_code_challenge_is_refused(self):
        response = self.authorize(challenge=None)
        self.assertEqual(query_of(response)["error"], "invalid_request")
        self.assertNotIn("code", query_of(response))

    def test_the_plain_challenge_method_is_refused(self):
        response = self.authorize(challenge="a-plain-challenge-that-is-long-enough-to-pass-length-checks", method="plain")
        self.assertEqual(query_of(response)["error"], "invalid_request")
        self.assertNotIn("code", query_of(response))

    def test_the_code_cannot_be_redeemed_without_the_verifier(self):
        _, challenge = pkce_pair()
        code = code_from(self.authorize(challenge=challenge))

        response = self.exchange(code, None)

        self.assertEqual(response.status_code, 400)
        self.assertNotIn("access_token", response.json())

    def test_the_code_cannot_be_redeemed_with_a_wrong_verifier(self):
        _, challenge = pkce_pair()
        code = code_from(self.authorize(challenge=challenge))
        other_verifier, _ = pkce_pair()

        response = self.exchange(code, other_verifier)

        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"], "invalid_grant")

    def test_the_provider_advertises_s256_only(self):
        metadata = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertEqual(metadata["code_challenge_methods_supported"], ["S256"])


class ResourceAudienceTests(McpTestCase):
    """RFC 8707: the MCP endpoint only takes tokens issued specifically for it."""

    def test_a_token_issued_for_the_mcp_resource_is_accepted(self):
        token = self.token_via_oauth()
        response = self.rpc("ping", access_token=token["access_token"])
        self.assertEqual(response.status_code, 200)

    def test_a_token_issued_for_another_resource_is_rejected(self):
        token = self.token_via_oauth(authorize_resource="https://other-api.example/mcp", token_resource=None)
        response = self.rpc("ping", access_token=token["access_token"])
        self.assertEqual(response.status_code, 401)
        self.assertIn("invalid_token", response["WWW-Authenticate"])

    def test_a_token_without_any_resource_is_rejected_instead_of_treated_as_unrestricted(self):
        token = self.token_via_oauth(authorize_resource=None, token_resource=None)
        response = self.rpc("ping", access_token=token["access_token"])
        self.assertEqual(response.status_code, 401)
        self.assertIn("invalid_token", response["WWW-Authenticate"])

    def test_a_token_for_the_whole_origin_covers_the_mcp_path(self):
        origin = settings.MCP_RESOURCE_URL.rsplit("/", 1)[0]
        access_token = self.issue_token(resource=origin)
        self.assertEqual(self.rpc("ping", access_token=access_token).status_code, 200)

    def test_a_token_for_a_lookalike_host_is_rejected(self):
        access_token = self.issue_token(resource="https://evil.example/mcp")
        self.assertEqual(self.rpc("ping", access_token=access_token).status_code, 401)

    def test_an_expired_token_is_rejected(self):
        from datetime import timedelta

        from django.utils import timezone
        from oauth2_provider.models import AccessToken

        access_token = self.issue_token()
        AccessToken.objects.update(expires=timezone.now() - timedelta(minutes=1))
        self.assertEqual(self.rpc("ping", access_token=access_token).status_code, 401)


class DiscoveryTests(McpTestCase):
    def test_an_unauthenticated_call_points_the_client_at_the_resource_metadata(self):
        response = self.rpc("ping")

        self.assertEqual(response.status_code, 401)
        challenge = response["WWW-Authenticate"]
        self.assertTrue(challenge.startswith("Bearer"))
        self.assertIn("resource_metadata=", challenge)
        self.assertIn("/.well-known/oauth-protected-resource", challenge)

    def test_the_protected_resource_metadata_names_the_mcp_resource_and_its_scopes(self):
        for path in ("/.well-known/oauth-protected-resource", "/.well-known/oauth-protected-resource/mcp"):
            metadata = self.client.get(path).json()
            self.assertEqual(metadata["resource"], settings.MCP_RESOURCE_URL, path)
            self.assertEqual(set(metadata["scopes_supported"]), {"billiger:read", "billiger:write"}, path)
            self.assertTrue(metadata["authorization_servers"], path)

    def test_the_authorization_server_metadata_lists_the_endpoints(self):
        metadata = self.client.get("/.well-known/oauth-authorization-server").json()
        self.assertTrue(metadata["authorization_endpoint"].endswith("/oauth/authorize/"))
        self.assertTrue(metadata["token_endpoint"].endswith("/oauth/token/"))
        self.assertEqual(metadata["response_types_supported"], ["code"])


class ChatGptClientTests(McpTestCase):
    def test_the_chatgpt_client_is_registered_once_its_redirect_uri_is_configured(self):
        from mcp_server.clients import ensure_clients

        with override_settings(MCP_CHATGPT_REDIRECT_URI="https://chatgpt.com/connector/oauth/xyz"):
            ensure_clients()
            ensure_clients()  # idempotent

        chatgpt = Application.objects.get(client_id=CHATGPT_CLIENT_ID)
        self.assertEqual(chatgpt.redirect_uris, "https://chatgpt.com/connector/oauth/xyz")
        self.assertEqual(Application.objects.filter(client_id=CHATGPT_CLIENT_ID).count(), 1)
