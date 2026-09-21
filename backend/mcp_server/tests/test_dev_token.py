from io import StringIO

from django.core.management import CommandError, call_command
from django.test import override_settings

from mcp_server.tests.helpers import McpTestCase


def issue(*args):
    out = StringIO()
    call_command("issue_mcp_dev_token", *args, stdout=out)
    return out.getvalue().strip()


@override_settings(MCP_ALLOW_DEV_TOKENS=True)
class DevTokenTests(McpTestCase):
    def test_the_token_works_against_the_mcp_endpoint_as_that_account(self):
        token = issue("anna@example.com")

        response = self.rpc("tools/list", access_token=token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.json()["result"]["tools"]), 7)

    def test_the_scopes_can_be_narrowed(self):
        token = issue("anna@example.com", "--scope", "billiger:read")

        tools = self.rpc("tools/list", access_token=token).json()["result"]["tools"]

        self.assertEqual(len(tools), 4)

    def test_it_is_the_same_audience_validation_as_for_any_other_token(self):
        from oauth2_provider.models import AccessToken

        token = issue("anna@example.com")
        AccessToken.objects.filter(token=token).update(resource=["https://elsewhere.example/mcp"])

        self.assertEqual(self.rpc("ping", access_token=token).status_code, 401)

    def test_an_unknown_account_or_scope_is_refused(self):
        with self.assertRaises(CommandError):
            issue("nobody@example.com")
        with self.assertRaises(CommandError):
            issue("anna@example.com", "--scope", "billiger:admin")

    @override_settings(MCP_ALLOW_DEV_TOKENS=False, DEBUG=False)
    def test_it_refuses_to_run_outside_development(self):
        with self.assertRaises(CommandError):
            issue("anna@example.com")

    @override_settings(MCP_ALLOW_DEV_TOKENS=False, DEBUG=True)
    def test_it_runs_in_debug(self):
        self.assertTrue(issue("anna@example.com"))

    def test_there_is_no_http_endpoint_that_hands_out_tokens_to_users(self):
        self.client.force_login(self.user)
        for path in ("/api/mcp-token/", "/api/auth/mcp-token/", "/oauth/personal-token/", "/mcp/token/"):
            self.assertEqual(self.client.post(path).status_code, 404, path)
