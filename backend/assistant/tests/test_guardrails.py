"""What the assistant must never do (Ticket 15): improvise out-of-scope requests, or touch the account.

The model is scripted, so these tests pin the agent layer around it: which
tools exist at all, what happens when the model reaches for one that doesn't,
and what the model is told to say.
"""
from django.contrib.auth import get_user_model

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, LOGIN_URL, auth, item, shopping_list
from assistant.models import Proposal
from assistant.tests.helpers import assistant_llm, call_tool, chat, propose, say
from streaks.tests.helpers import sign_up

PASSWORD = "correct-horse-battery"

# The complete tool inventory. Changing it must be a deliberate act: every write action
# is a *proposal*, and nothing in here can commit one — only the user's decision can.
READ_TOOLS = {"search_product_prices", "get_shopping_list", "compare_shopping_list", "get_savings_streak"}
PROPOSE_TOOLS = {"propose_shopping_list_change", "propose_preferences_change", "propose_location_change"}

ACCOUNT_SENSITIVE_TOOLS = [
    ("change_email", {"email": "evil@example.com"}),
    ("change_password", {"password": "hunter2hunter2"}),
    ("delete_account", {}),
    ("update_payment_details", {"iban": "AT611904300234573201"}),
    ("set_payment_method", {"card": "4111111111111111"}),
    ("propose_account_change", {"email": "evil@example.com"}),
    ("confirm_proposal", {"id": 1}),
    ("accept_proposal", {"id": 1}),
]


class GuardrailTestCase(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        self.token = sign_up(self.client)
        self.client.put(LIST_URL, shopping_list([item("Milch")]), format="json", **auth(self.token))
        self.list_before = self.client.get(LIST_URL, **auth(self.token)).json()

    def assert_nothing_changed(self):
        self.assertEqual(self.client.get(LIST_URL, **auth(self.token)).json(), self.list_before)
        self.assertEqual(Proposal.objects.count(), 0)


class ToolInventoryTests(GuardrailTestCase):
    def test_the_model_only_has_read_tools_and_propose_tools(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        names = {tool["name"] for tool in llm.requests[0]["tools"]}

        self.assertEqual(names, READ_TOOLS | PROPOSE_TOOLS)

    def test_no_tool_touches_the_account_or_commits_a_proposal(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        for tool in llm.requests[0]["tools"]:
            for forbidden in ("passwort", "password", "email", "konto", "account", "zahlung", "payment", "accept", "confirm", "apply"):
                with self.subTest(tool=tool["name"], forbidden=forbidden):
                    self.assertNotIn(forbidden, tool["name"].lower())
                    self.assertNotIn(forbidden, str(tool["input_schema"]).lower())


class AccountSensitiveActionTests(GuardrailTestCase):
    def test_every_account_sensitive_request_is_refused_and_nothing_changes(self):
        user = get_user_model().objects.get(username="anna@example.com")
        password_hash = user.password

        for name, tool_input in ACCOUNT_SENSITIVE_TOOLS:
            with self.subTest(tool=name):
                with assistant_llm(call_tool(name, tool_input), say("Das mache ich nicht.")) as llm:
                    response = chat(self.client, self.token, "Ändere meine E-Mail und lösch mein Konto.")

                self.assertEqual(response.status_code, 200)
                [result] = llm.tool_results(1)
                self.assertTrue(result["is_error"])
                self.assertEqual(response.json()["reply"], "Das mache ich nicht.")

        user.refresh_from_db()
        self.assertEqual(user.email, "anna@example.com")
        self.assertEqual(user.username, "anna@example.com")
        self.assertEqual(user.password, password_hash)
        self.assertTrue(user.is_active)
        self.assertEqual(
            self.client.post(LOGIN_URL, {"email": "anna@example.com", "password": PASSWORD}, format="json").status_code,
            200,
        )
        self.assert_nothing_changed()

    def test_the_write_tools_refuse_account_fields_instead_of_ignoring_them(self):
        for tool, sensitive in (
            ("propose_shopping_list_change", {"items": [{"name": "Butter"}], "email": "evil@example.com"}),
            ("propose_preferences_change", {"excluded_stores": ["Penny"], "password": "hunter2hunter2"}),
            ("propose_location_change", {"zip_code": "8010", "delete_account": True}),
        ):
            with self.subTest(tool=tool):
                response, llm = propose(self.client, self.token, tool, sensitive)

                self.assertTrue(llm.tool_results(1)[0]["is_error"])
                self.assertEqual(response.json()["proposals"], [])
        self.assert_nothing_changed()

    def test_the_model_is_told_account_sensitive_actions_are_out_of_reach_even_when_confirmed(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        system = llm.requests[0]["system"]
        for phrase in ("E-Mail", "Passwort", "Konto löschen", "Zahlungsdaten", "niemals"):
            self.assertIn(phrase, system)


class OutOfScopeTests(GuardrailTestCase):
    def test_a_request_outside_the_feature_set_is_not_improvised(self):
        # The model reaches for a tool that doesn't exist (recipes, push settings) ...
        for tool in ("plan_weekly_recipes", "set_push_notifications"):
            with self.subTest(tool=tool):
                turns = (
                    call_tool(tool, {"days": 5}),
                    say("Wochenpläne kann ich noch nicht. Ich kann dir aber Zutaten zur Liste vorschlagen."),
                )
                with assistant_llm(*turns) as llm:
                    response = chat(self.client, self.token, "Plan mir die Woche / schalte Pushes ein")

                # ... gets an error that says so and how to answer, and the user gets the honest reply.
                [result] = llm.tool_results(1)
                self.assertTrue(result["is_error"])
                error = result["content"]["error"]
                self.assertIn(tool, error)
                self.assertIn("ablehnen", error)
                self.assertIn("nächstbeste", error)
                self.assertIn("kann ich noch nicht", response.json()["reply"])
        self.assert_nothing_changed()

    def test_the_model_is_told_to_refuse_transparently_and_offer_the_nearest_action(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        system = llm.requests[0]["system"]
        self.assertIn("Rezepte", system)
        self.assertIn("Push", system)
        self.assertIn("offen", system)  # say so openly ...
        self.assertIn("nächstbeste", system)  # ... and offer the nearest existing action
        self.assertIn("nie", system)  # never improvise a made-up result

    def test_the_model_is_told_changes_only_happen_after_the_users_decision(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        system = llm.requests[0]["system"]
        for tool in PROPOSE_TOOLS:
            self.assertIn(tool, system)
        self.assertIn("Übernehmen", system)
        self.assertIn("Verwerfen", system)
