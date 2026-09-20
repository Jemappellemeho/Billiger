"""The boundary to the language model.

Everything the assistant needs from the model fits in `LLMClient.complete`;
tests replace it with a scripted stand-in, production uses `AnthropicLLM`.
"""
from dataclasses import dataclass, field

import anthropic
from django.conf import settings


class LLMNotConfigured(Exception):
    pass


class LLMError(Exception):
    pass


@dataclass(frozen=True)
class ToolCall:
    id: str
    name: str
    input: dict


@dataclass(frozen=True)
class LLMTurn:
    """One model response, reduced to what the agent loop needs.

    `assistant_content` is opaque: it is echoed back to the model verbatim
    when the loop continues after tool calls (thinking blocks included).
    """

    text: str
    tool_calls: list[ToolCall] = field(default_factory=list)
    assistant_content: list = field(default_factory=list)
    refused: bool = False


class AnthropicLLM:
    FALLBACKS_BETA = "server-side-fallback-2026-07-01"

    def __init__(self, client, model, use_fallbacks=True, max_tokens=4096):
        self.client = client
        self.model = model
        self.use_fallbacks = use_fallbacks
        self.max_tokens = max_tokens

    def complete(self, system, messages, tools):
        request = {
            "model": self.model,
            "max_tokens": self.max_tokens,
            "system": system,
            "messages": messages,
            "tools": tools,
        }
        try:
            if self.use_fallbacks:
                # A safety-classifier decline is re-run on a fallback model inside the same call.
                response = self.client.beta.messages.create(
                    betas=[self.FALLBACKS_BETA], fallbacks="default", **request
                )
            else:
                response = self.client.messages.create(**request)
        except anthropic.APIError as exc:
            raise LLMError(str(exc)) from exc

        return LLMTurn(
            text="".join(block.text for block in response.content if block.type == "text"),
            tool_calls=[
                ToolCall(id=block.id, name=block.name, input=block.input)
                for block in response.content
                if block.type == "tool_use"
            ],
            assistant_content=response.content,
            refused=response.stop_reason == "refusal",
        )


def llm_from_django_settings():
    if not settings.ANTHROPIC_API_KEY:
        raise LLMNotConfigured("ANTHROPIC_API_KEY is not set.")
    return AnthropicLLM(
        anthropic.Anthropic(api_key=settings.ANTHROPIC_API_KEY),
        model=settings.ASSISTANT_MODEL,
        use_fallbacks=settings.ASSISTANT_LLM_FALLBACKS,
    )
