"""The assistant's agent layer: one chat turn = the model plus its tools, looped until it answers."""
import json
from dataclasses import dataclass, field

from assistant.prompt import SYSTEM_PROMPT
from assistant.tools import TOOL_DEFINITIONS, ToolError, run_tool

# Tool rounds per chat turn; a model that keeps calling tools without answering is cut off.
MAX_TOOL_ROUNDS = 6

GAVE_UP_REPLY = "Dazu brauche ich gerade zu lange. Magst du die Frage etwas einfacher stellen?"
REFUSED_REPLY = "Dabei kann ich dir leider nicht helfen."


@dataclass
class AssistantReply:
    text: str
    actions: list[dict] = field(default_factory=list)


def run_assistant(llm, history, message, tool_context):
    """Answers `message` (the new user turn after `history`), running whatever tools the model asks for."""
    messages = [*history, {"role": "user", "content": message}]
    actions = []

    for _ in range(MAX_TOOL_ROUNDS + 1):
        turn = llm.complete(SYSTEM_PROMPT, messages, TOOL_DEFINITIONS)
        if turn.refused:
            return AssistantReply(REFUSED_REPLY, actions)
        if not turn.tool_calls:
            return AssistantReply(turn.text, actions)

        results = []
        for call in turn.tool_calls:
            try:
                result, is_error = run_tool(call.name, call.input, tool_context), False
            except ToolError as exc:
                result, is_error = {"error": str(exc)}, True
            actions.append({"tool": call.name, "input": call.input, "result": result})
            results.append(_tool_result_block(call.id, result, is_error))

        messages.append({"role": "assistant", "content": turn.assistant_content})
        messages.append({"role": "user", "content": results})

    return AssistantReply(GAVE_UP_REPLY, actions)


def _tool_result_block(tool_use_id, result, is_error):
    block = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, ensure_ascii=False),
    }
    if is_error:
        block["is_error"] = True
    return block
