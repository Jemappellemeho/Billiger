import json
from unittest.mock import patch

from django.contrib.auth import get_user_model
from rest_framework.authtoken.models import Token

from accounts import shopping_list
from accounts.tests.helpers import item
from accounts.tests.helpers import shopping_list as list_document
from assistant.models import Proposal
from mcp_server.tests.helpers import McpTestCase
from mcp_server.tools import READ_SCOPE, WRITE_SCOPE
from search.tests.test_cart_comparison_view import _fake_session_get

READ_TOOLS = {"get_shopping_list", "search_product_prices", "compare_shopping_list", "get_savings_streak"}
WRITE_TOOLS = {"propose_shopping_list_change", "propose_preferences_change", "propose_location_change"}


class McpApiTestCase(McpTestCase):
    """A signed-in account with a list, an MCP token for it, and the REST API to compare the tools against."""

    def setUp(self):
        super().setUp()
        self.rest_token = Token.objects.create(user=self.user).key
        self.stored_list(item("Milch", quantity=2), item("Nutella"))
        self.access_token = self.issue_token()

    def stored_list(self, *items):
        shopping_list.save(self.user, list_document(items))

    def rest(self, method, path, body=None, **params):
        """What the app itself would get from the REST API (signed in with the account's own token)."""
        with patch("requests.Session.get", side_effect=_fake_session_get):
            return getattr(self.client, method)(
                path, body, format="json", HTTP_AUTHORIZATION=f"Token {self.rest_token}", **params
            )

    def tool(self, name, arguments=None, access_token=None):
        with patch("requests.Session.get", side_effect=_fake_session_get):
            return self.call_tool(access_token or self.access_token, name, arguments)


class ProtocolTests(McpApiTestCase):
    def test_initialize_negotiates_the_protocol_version_and_offers_tools(self):
        response = self.rpc(
            "initialize",
            {"protocolVersion": "2025-06-18", "capabilities": {}, "clientInfo": {"name": "claude", "version": "1"}},
            access_token=self.access_token,
        )

        result = response.json()["result"]
        self.assertEqual(result["protocolVersion"], "2025-06-18")
        self.assertIn("tools", result["capabilities"])
        self.assertEqual(result["serverInfo"]["name"], "billiger")

    def test_initialize_answers_an_unknown_version_with_one_it_speaks(self):
        response = self.rpc("initialize", {"protocolVersion": "1999-01-01"}, access_token=self.access_token)
        self.assertIn(response.json()["result"]["protocolVersion"], ("2025-11-25", "2025-06-18", "2025-03-26"))

    def test_a_notification_is_acknowledged_without_a_body(self):
        response = self.rpc("notifications/initialized", request_id=None, access_token=self.access_token)
        self.assertEqual(response.status_code, 202)
        self.assertEqual(response.content, b"")

    def test_an_unknown_method_is_a_json_rpc_error(self):
        response = self.rpc("resources/list", access_token=self.access_token)
        self.assertEqual(response.json()["error"]["code"], -32601)
        self.assertEqual(response.json()["id"], 1)

    def test_a_body_that_is_not_json_is_a_parse_error(self):
        response = self.client.post(
            "/mcp/", "{nope", content_type="application/json", **self.bearer(self.access_token)
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32700)

    def test_batched_requests_are_refused(self):
        response = self.client.post(
            "/mcp/",
            json.dumps([{"jsonrpc": "2.0", "id": 1, "method": "ping"}]),
            content_type="application/json",
            **self.bearer(self.access_token),
        )
        self.assertEqual(response.status_code, 400)
        self.assertEqual(response.json()["error"]["code"], -32600)

    def test_only_post_is_supported(self):
        response = self.client.get("/mcp/", **self.bearer(self.access_token))
        self.assertEqual(response.status_code, 405)

    def test_a_browser_origin_that_is_not_allowed_is_refused(self):
        response = self.rpc("ping", access_token=self.access_token, HTTP_ORIGIN="https://evil.example")
        self.assertEqual(response.status_code, 403)

    def test_an_allowed_origin_may_call(self):
        response = self.rpc("ping", access_token=self.access_token, HTTP_ORIGIN="https://claude.ai")
        self.assertEqual(response.status_code, 200)


class ToolListTests(McpApiTestCase):
    def names(self, access_token):
        response = self.rpc("tools/list", access_token=access_token)
        return {tool["name"] for tool in response.json()["result"]["tools"]}

    def test_a_full_token_is_offered_the_four_read_and_three_propose_actions(self):
        self.assertEqual(self.names(self.access_token), READ_TOOLS | WRITE_TOOLS)

    def test_a_read_only_token_is_only_offered_the_read_actions(self):
        self.assertEqual(self.names(self.issue_token(scope=READ_SCOPE)), READ_TOOLS)

    def test_no_tool_can_accept_a_proposal_or_touch_the_account(self):
        forbidden = ("accept", "reject", "decide", "confirm", "password", "email", "delete", "payment", "account")
        for name in self.names(self.access_token):
            self.assertFalse(any(word in name for word in forbidden), name)

    def test_every_tool_describes_its_input(self):
        tools = self.rpc("tools/list", access_token=self.access_token).json()["result"]["tools"]
        for tool in tools:
            self.assertTrue(tool["description"], tool["name"])
            self.assertEqual(tool["inputSchema"]["type"], "object", tool["name"])
            self.assertEqual(tool["annotations"]["readOnlyHint"], tool["name"] in READ_TOOLS, tool["name"])

    def test_the_price_tools_ask_the_client_for_a_postal_code(self):
        tools = {
            tool["name"]: tool
            for tool in self.rpc("tools/list", access_token=self.access_token).json()["result"]["tools"]
        }
        self.assertEqual(tools["search_product_prices"]["inputSchema"]["required"], ["query", "zip_code"])
        self.assertEqual(tools["compare_shopping_list"]["inputSchema"]["required"], ["zip_code"])


class ReadToolMappingTests(McpApiTestCase):
    """Each read tool returns what the REST endpoint behind it serves the same account."""

    def test_get_shopping_list_is_the_shopping_list_endpoint(self):
        result = self.tool("get_shopping_list")

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], self.rest("get", "/api/shopping-list/").json())
        self.assertEqual(json.loads(result["content"][0]["text"]), result["structuredContent"])
        self.assertEqual([row["name"] for row in result["structuredContent"]["items"]], ["Milch", "Nutella"])

    def test_search_product_prices_is_the_search_endpoint(self):
        result = self.tool("search_product_prices", {"query": "Milch", "zip_code": "1010"})

        self.assertFalse(result["isError"])
        expected = self.rest("get", "/api/search/?q=Milch&zip_code=1010").json()
        self.assertEqual(result["structuredContent"], expected)
        self.assertTrue(expected["results"])

    def test_compare_shopping_list_is_the_compare_endpoint_run_on_the_saved_list(self):
        result = self.tool("compare_shopping_list", {"zip_code": "1010"})

        self.assertFalse(result["isError"])
        items = self.rest("get", "/api/shopping-list/").json()["items"]
        expected = self.rest("post", "/api/compare/", {"items": items, "zip_code": "1010"}).json()
        self.assertEqual(result["structuredContent"], expected)
        self.assertIn("full_split", expected)

    def test_compare_shopping_list_counts_toward_the_streak_like_the_app(self):
        self.assertEqual(self.rest("get", "/api/streak/").json()["history"], [])

        self.tool("compare_shopping_list", {"zip_code": "1010"})

        self.assertEqual(len(self.rest("get", "/api/streak/").json()["history"]), 1)

    def test_get_savings_streak_is_the_streak_endpoint(self):
        result = self.tool("get_savings_streak")

        self.assertFalse(result["isError"])
        self.assertEqual(result["structuredContent"], self.rest("get", "/api/streak/").json())

    def test_a_tool_only_ever_sees_the_token_owners_data(self):
        other = get_user_model().objects.create_user(username="ben@example.com", email="ben@example.com")
        shopping_list.save(other, list_document([item("Bier")]))

        result = self.tool("get_shopping_list", access_token=self.issue_token(user=other))

        self.assertEqual([row["name"] for row in result["structuredContent"]["items"]], ["Bier"])

    def test_a_rest_error_becomes_a_tool_error_carrying_its_message(self):
        result = self.tool("search_product_prices", {"query": "Milch"})  # no zip_code

        self.assertTrue(result["isError"])
        self.assertTrue(result["content"][0]["text"])
        self.assertNotIn("structuredContent", result)

    def test_comparing_an_empty_list_is_a_tool_error(self):
        self.stored_list()

        result = self.tool("compare_shopping_list", {"zip_code": "1010"})

        self.assertTrue(result["isError"])

    def test_a_failing_endpoint_is_a_tool_error_not_a_server_error(self):
        with patch("mcp_server.tools.call_rest", side_effect=RuntimeError("boom")), self.assertLogs(
            "mcp_server.protocol", level="ERROR"
        ):
            result = self.call_tool(self.access_token, "get_shopping_list")

        self.assertTrue(result["isError"])
        self.assertNotIn("boom", result["content"][0]["text"])


class ProposeToolMappingTests(McpApiTestCase):
    """The write tools create proposals through the REST endpoint; nothing is applied until the user decides."""

    def stored_names(self):
        return [row["name"] for row in shopping_list.load(self.user)["items"]]

    def test_propose_shopping_list_change_stores_a_pending_proposal_with_the_full_diff(self):
        result = self.tool(
            "propose_shopping_list_change",
            {"items": [{"name": "Milch", "quantity": 3}, {"name": "Nutella"}, {"name": "Butter"}]},
        )

        self.assertFalse(result["isError"])
        proposal = result["structuredContent"]["proposal"]
        self.assertEqual(proposal["status"], "pending")
        self.assertEqual(proposal["kind"], "shopping_list")
        self.assertEqual([row["name"] for row in proposal["diff"]["added"]], ["Butter"])
        self.assertEqual(proposal["diff"]["changed"][0]["changes"]["quantity"], {"before": 2, "after": 3})
        self.assertIn("NICHT übernommen", result["structuredContent"]["next_step"])
        self.assertEqual(Proposal.objects.get(pk=proposal["id"]).user, self.user)
        # ... and nothing changed yet.
        self.assertEqual(self.stored_names(), ["Milch", "Nutella"])

    def test_the_proposal_is_the_one_the_rest_endpoint_would_create(self):
        arguments = {"items": [{"name": "Milch", "quantity": 2}, {"name": "Butter"}]}

        via_mcp = self.tool("propose_shopping_list_change", arguments)["structuredContent"]["proposal"]
        via_rest = self.rest("post", "/api/assistant/proposals/", {"kind": "shopping_list", **arguments}).json()["proposal"]

        self.assertEqual({**via_mcp, "id": None}, {**via_rest, "id": None})

    def test_propose_preferences_change_is_a_preferences_proposal(self):
        result = self.tool("propose_preferences_change", {"preferred_brands": ["Ja! Natürlich"], "favorite_items": ["Milch"]})

        proposal = result["structuredContent"]["proposal"]
        self.assertFalse(result["isError"])
        self.assertEqual(proposal["kind"], "preferences")
        self.assertEqual(proposal["diff"]["preferred_brands"]["added"], ["Ja! Natürlich"])
        self.assertEqual(proposal["diff"]["favorites"]["added"][0]["name"], "Milch")

    def test_propose_location_change_is_a_location_proposal(self):
        result = self.tool("propose_location_change", {"zip_code": "8010"})

        proposal = result["structuredContent"]["proposal"]
        self.assertFalse(result["isError"])
        self.assertEqual(proposal["kind"], "location")
        self.assertEqual(proposal["diff"]["after"], {"zip_code": "8010"})

    def test_the_user_can_accept_what_was_proposed_over_the_rest_api(self):
        proposal_id = self.tool("propose_shopping_list_change", {"items": [{"name": "Butter"}]})["structuredContent"][
            "proposal"
        ]["id"]

        response = self.rest("post", f"/api/assistant/proposals/{proposal_id}/accept/")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.stored_names(), ["Butter"])

    def test_an_invalid_proposal_is_a_tool_error_and_stores_nothing(self):
        result = self.tool("propose_location_change", {"zip_code": "not-a-plz"})

        self.assertTrue(result["isError"])
        self.assertEqual(Proposal.objects.count(), 0)

    def test_a_field_the_action_does_not_have_is_refused(self):
        result = self.tool("propose_location_change", {"zip_code": "8010", "email": "eve@example.com"})

        self.assertTrue(result["isError"])
        self.assertEqual(Proposal.objects.count(), 0)

    def test_a_client_cannot_pick_the_kind_of_proposal_through_the_arguments(self):
        result = self.tool("propose_location_change", {"zip_code": "8010", "kind": "shopping_list"})

        self.assertEqual(result["structuredContent"]["proposal"]["kind"], "location")


class ScopeTests(McpApiTestCase):
    def test_a_read_only_token_cannot_propose(self):
        read_only = self.issue_token(scope=READ_SCOPE)

        result = self.tool("propose_shopping_list_change", {"items": [{"name": "Butter"}]}, access_token=read_only)

        self.assertTrue(result["isError"])
        self.assertIn("billiger:write", result["content"][0]["text"])
        self.assertEqual(Proposal.objects.count(), 0)

    def test_a_write_only_token_cannot_read(self):
        write_only = self.issue_token(scope=WRITE_SCOPE)

        result = self.tool("get_shopping_list", access_token=write_only)

        self.assertTrue(result["isError"])
        self.assertIn("billiger:read", result["content"][0]["text"])

    def test_an_unknown_tool_is_a_json_rpc_error(self):
        response = self.rpc("tools/call", {"name": "accept_proposal", "arguments": {}}, access_token=self.access_token)

        self.assertEqual(response.json()["error"]["code"], -32602)

    def test_a_token_from_the_oauth_flow_carries_exactly_the_scopes_the_user_allowed(self):
        token = self.token_via_oauth(scope=READ_SCOPE)["access_token"]

        names = {tool["name"] for tool in self.rpc("tools/list", access_token=token).json()["result"]["tools"]}

        self.assertEqual(names, READ_TOOLS)


class RestApiStaysSeparateTests(McpApiTestCase):
    def test_an_mcp_access_token_does_not_open_the_rest_api(self):
        response = self.client.get("/api/shopping-list/", HTTP_AUTHORIZATION=f"Bearer {self.access_token}")
        self.assertEqual(response.status_code, 401)
