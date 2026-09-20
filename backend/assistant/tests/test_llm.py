from types import SimpleNamespace
from unittest.mock import MagicMock

import anthropic
from django.test import SimpleTestCase, override_settings

from assistant.llm import AnthropicLLM, LLMError, LLMNotConfigured, ToolCall, llm_from_django_settings

TOOLS = [{"name": "get_shopping_list", "description": "…", "input_schema": {"type": "object"}}]
MESSAGES = [{"role": "user", "content": "Hallo"}]


def _response(*blocks, stop_reason="end_turn"):
    return SimpleNamespace(content=list(blocks), stop_reason=stop_reason)


def _text(text):
    return SimpleNamespace(type="text", text=text)


def _tool_use(call_id, name, tool_input):
    return SimpleNamespace(type="tool_use", id=call_id, name=name, input=tool_input)


class AnthropicLLMTests(SimpleTestCase):
    def test_sends_the_request_with_refusal_fallbacks_and_reads_text_and_tool_calls(self):
        client = MagicMock()
        blocks = [_text("Ich schaue nach."), _tool_use("toolu_1", "get_shopping_list", {})]
        client.beta.messages.create.return_value = _response(*blocks)

        turn = AnthropicLLM(client, model="claude-opus-5").complete("System", MESSAGES, TOOLS)

        client.beta.messages.create.assert_called_once_with(
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            model="claude-opus-5",
            max_tokens=4096,
            system="System",
            messages=MESSAGES,
            tools=TOOLS,
        )
        self.assertEqual(turn.text, "Ich schaue nach.")
        self.assertEqual(turn.tool_calls, [ToolCall("toolu_1", "get_shopping_list", {})])
        # Echoed back verbatim (thinking blocks included) when the loop continues.
        self.assertEqual(turn.assistant_content, blocks)
        self.assertFalse(turn.refused)

    def test_fallbacks_can_be_switched_off(self):
        client = MagicMock()
        client.messages.create.return_value = _response(_text("Hi"))

        AnthropicLLM(client, model="claude-sonnet-5", use_fallbacks=False).complete("S", MESSAGES, TOOLS)

        client.messages.create.assert_called_once()
        client.beta.messages.create.assert_not_called()

    def test_a_refusal_is_reported_as_such(self):
        client = MagicMock()
        client.beta.messages.create.return_value = _response(stop_reason="refusal")

        turn = AnthropicLLM(client, model="claude-opus-5").complete("S", MESSAGES, TOOLS)

        self.assertTrue(turn.refused)

    def test_api_failures_become_llm_errors(self):
        client = MagicMock()
        client.beta.messages.create.side_effect = anthropic.APIConnectionError(request=MagicMock())

        with self.assertRaises(LLMError):
            AnthropicLLM(client, model="claude-opus-5").complete("S", MESSAGES, TOOLS)


class LLMFromSettingsTests(SimpleTestCase):
    @override_settings(ANTHROPIC_API_KEY="")
    def test_no_api_key_means_not_configured(self):
        with self.assertRaises(LLMNotConfigured):
            llm_from_django_settings()

    @override_settings(ANTHROPIC_API_KEY="sk-ant-test", ASSISTANT_MODEL="claude-sonnet-5", ASSISTANT_LLM_FALLBACKS=False)
    def test_model_and_fallbacks_come_from_settings(self):
        llm = llm_from_django_settings()

        self.assertEqual(llm.model, "claude-sonnet-5")
        self.assertFalse(llm.use_fallbacks)
