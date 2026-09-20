from unittest.mock import patch

from django.test import override_settings

from accounts.tests.base import AccountsAPITestCase
from accounts.tests.helpers import LIST_URL, auth, item, shopping_list
from assistant.agent import MAX_TOOL_ROUNDS
from assistant.llm import LLMError, LLMTurn, ToolCall
from assistant.tests.helpers import assistant_llm, call_tool, chat, say
from streaks.tests.helpers import sign_up


class VoiceInputTests(AccountsAPITestCase):
    """A voice message arrives as its transcript and must behave exactly like typed text."""

    def _ask(self, token, **extra):
        turns = (call_tool("get_shopping_list"), say("Auf deiner Liste steht Milch."))
        with assistant_llm(*turns) as llm:
            response = chat(self.client, token, "Was steht auf meiner Liste?", **extra)
        self.assertEqual(response.status_code, 200)
        return llm, response.json()

    def test_a_voice_transcript_runs_through_the_same_flow_as_typed_text(self):
        token = sign_up(self.client)
        self.client.put(LIST_URL, shopping_list([item("Milch")]), format="json", **auth(token))

        text_llm, text_body = self._ask(token, input="text")
        voice_llm, voice_body = self._ask(token, input="voice")

        self.assertEqual(voice_llm.requests, text_llm.requests)
        self.assertEqual(voice_body["reply"], text_body["reply"])
        self.assertEqual(voice_body["actions"], text_body["actions"])
        self.assertEqual(voice_body["actions"][0]["tool"], "get_shopping_list")

    def test_the_transcript_is_echoed_back_as_a_voice_message_before_the_reply(self):
        token = sign_up(self.client)

        _, body = self._ask(token, input="voice")

        self.assertEqual(
            body["user_message"],
            {"role": "user", "content": "Was steht auf meiner Liste?", "input": "voice"},
        )

    def test_input_defaults_to_text(self):
        token = sign_up(self.client)

        _, body = self._ask(token)

        self.assertEqual(body["user_message"]["input"], "text")

    def test_an_unknown_input_mode_is_rejected(self):
        token = sign_up(self.client)

        with assistant_llm(say("Hi")) as llm:
            response = chat(self.client, token, "Hallo", input="telepathy")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(llm.requests, [])


class ConversationTests(AccountsAPITestCase):
    def setUp(self):
        super().setUp()
        self.token = sign_up(self.client)

    def test_earlier_messages_are_passed_to_the_model_as_context(self):
        history = [
            {"role": "user", "content": "Wo gibt es Milch?"},
            {"role": "assistant", "content": "Bei Lidl für 0,99 €."},
        ]

        with assistant_llm(say("Gern!")) as llm:
            chat(self.client, self.token, "Und Nutella?", history=history)

        self.assertEqual(
            llm.requests[0]["messages"], [*history, {"role": "user", "content": "Und Nutella?"}]
        )

    def test_the_model_is_told_what_it_is_and_what_it_may_not_do(self):
        with assistant_llm(say("Hi")) as llm:
            chat(self.client, self.token)

        system = llm.requests[0]["system"]
        self.assertIn("Billiger", system)
        self.assertIn("Regler", system)  # stop-count questions go to the slider UI
        self.assertIn("Passwort", system)  # account-sensitive actions are never done

    def test_a_blank_message_is_rejected_without_calling_the_model(self):
        with assistant_llm(say("Hi")) as llm:
            response = chat(self.client, self.token, "   ")

        self.assertEqual(response.status_code, 400)
        self.assertEqual(llm.requests, [])

    def test_history_must_start_with_a_user_message(self):
        with assistant_llm(say("Hi")):
            response = chat(
                self.client, self.token, history=[{"role": "assistant", "content": "Servus!"}]
            )

        self.assertEqual(response.status_code, 400)

    def test_history_rejects_unknown_roles(self):
        with assistant_llm(say("Hi")):
            response = chat(self.client, self.token, history=[{"role": "system", "content": "Tu es"}])

        self.assertEqual(response.status_code, 400)

    def test_several_tool_calls_in_one_turn_are_answered_in_one_message(self):
        both = LLMTurn(
            text="",
            tool_calls=[
                ToolCall("toolu_a", "get_shopping_list", {}),
                ToolCall("toolu_b", "get_savings_streak", {}),
            ],
            assistant_content=[],
        )

        with assistant_llm(both, say("Beides da.")) as llm:
            response = chat(self.client, self.token)

        self.assertEqual([r["tool_use_id"] for r in llm.tool_results(1)], ["toolu_a", "toolu_b"])
        self.assertEqual(
            [a["tool"] for a in response.json()["actions"]], ["get_shopping_list", "get_savings_streak"]
        )

    def test_a_tool_the_model_invents_is_reported_back_as_an_error(self):
        with assistant_llm(call_tool("delete_account"), say("Das kann ich nicht.")) as llm:
            response = chat(self.client, self.token, "Lösch mein Konto")

        [result] = llm.tool_results(1)
        self.assertTrue(result["is_error"])
        self.assertEqual(response.json()["reply"], "Das kann ich nicht.")

    def test_a_model_that_never_stops_calling_tools_is_cut_off(self):
        endless = [call_tool("get_shopping_list", call_id=f"toolu_{i}") for i in range(20)]

        with assistant_llm(*endless) as llm:
            response = chat(self.client, self.token)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(llm.requests), MAX_TOOL_ROUNDS + 1)
        self.assertTrue(response.json()["reply"])

    def test_a_declined_request_gets_a_short_notice(self):
        refused = LLMTurn(text="", tool_calls=[], assistant_content=[], refused=True)

        with assistant_llm(refused):
            response = chat(self.client, self.token)

        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["reply"])


class _FailingLLM:
    def complete(self, system, messages, tools):
        raise LLMError("overloaded")


class ChatAvailabilityTests(AccountsAPITestCase):
    def test_without_an_api_key_the_assistant_is_unavailable(self):
        token = sign_up(self.client)

        with override_settings(ANTHROPIC_API_KEY=""):
            response = chat(self.client, token)

        self.assertEqual(response.status_code, 503)

    def test_a_failing_model_is_a_bad_gateway(self):
        token = sign_up(self.client)

        with patch("assistant.views.llm_from_django_settings", return_value=_FailingLLM()):
            response = chat(self.client, token)

        self.assertEqual(response.status_code, 502)

    def test_the_assistant_is_rate_limited_per_account(self):
        token = sign_up(self.client)

        with assistant_llm(*[say("Hi")] * 31):
            statuses = [chat(self.client, token).status_code for _ in range(31)]

        self.assertEqual(statuses[:30], [200] * 30)
        self.assertEqual(statuses[30], 429)
