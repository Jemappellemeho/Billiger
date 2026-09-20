import copy
import json
from contextlib import contextmanager
from unittest.mock import patch

from assistant.llm import LLMTurn, ToolCall
from search.tests.test_cart_comparison_view import _fake_session_get

CHAT_URL = "/api/assistant/chat/"


class ScriptedLLM:
    """Stands in for the LLM at the boundary: replays canned turns and records every request.

    The tests care about what the agent layer hands the model (tool results,
    history) and what it returns to the client — never about the model itself.
    """

    def __init__(self, *turns):
        self.turns = list(turns)
        self.requests = []

    def complete(self, system, messages, tools):
        self.requests.append({"system": system, "messages": copy.deepcopy(messages), "tools": tools})
        return self.turns.pop(0)

    def tool_results(self, request_index):
        """The parsed tool_result payloads sent to the model in request `request_index`."""
        last_message = self.requests[request_index]["messages"][-1]
        return [
            {**block, "content": json.loads(block["content"])}
            for block in last_message["content"]
            if block["type"] == "tool_result"
        ]


def say(text):
    return LLMTurn(text=text, tool_calls=[], assistant_content=[{"type": "text", "text": text}])


def call_tool(name, tool_input=None, call_id="toolu_1"):
    call = ToolCall(id=call_id, name=name, input=tool_input or {})
    block = {"type": "tool_use", "id": call_id, "name": name, "input": call.input}
    return LLMTurn(text="", tool_calls=[call], assistant_content=[block])


@contextmanager
def assistant_llm(*turns, marktguru=_fake_session_get):
    """Swaps the real LLM for a ScriptedLLM (Marktguru is stubbed too, like the other API tests)."""
    llm = ScriptedLLM(*turns)
    with patch("assistant.views.llm_from_django_settings", return_value=llm), patch(
        "requests.Session.get", side_effect=marktguru
    ):
        yield llm


def chat(client, token, message="Hallo", **extra):
    return client.post(
        CHAT_URL, {"message": message, **extra}, format="json", HTTP_AUTHORIZATION=f"Token {token}"
    )
