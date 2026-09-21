"""The assistant's agent layer: one chat turn = the model plus its tools, looped until it answers."""
import json
import logging
from dataclasses import dataclass, field

from assistant.prompt import SYSTEM_PROMPT
from assistant.tools import PROPOSAL_KEY, TOOL_DEFINITIONS, ToolError, run_tool

logger = logging.getLogger(__name__)

# Tool rounds per chat turn; a model that keeps calling tools without answering is cut off.
MAX_TOOL_ROUNDS = 6

GAVE_UP_REPLY = "Dazu brauche ich gerade zu lange. Magst du die Frage etwas einfacher stellen?"
REFUSED_REPLY = "Dabei kann ich dir leider nicht helfen."
NO_ANSWER_REPLY = "Dazu habe ich gerade keine Antwort."
TOOL_FAILED = "Das Werkzeug ist gerade ausgefallen."


@dataclass
class AssistantReply:
    text: str
    actions: list[dict] = field(default_factory=list)
    # Changes the assistant proposed this turn; the user still has to decide on each.
    proposals: list[dict] = field(default_factory=list)


def run_assistant(llm, history, message, tool_context):
    """Answers `message` (the new user turn after `history`), running whatever tools the model asks for."""
    messages = [*history, {"role": "user", "content": message}]
    actions = []
    proposed = []

    for _ in range(MAX_TOOL_ROUNDS + 1):
        turn = llm.complete(SYSTEM_PROMPT, messages, TOOL_DEFINITIONS)
        if turn.refused:
            return AssistantReply(REFUSED_REPLY, actions, proposed)
        if not turn.tool_calls:
            return AssistantReply(turn.text.strip() or NO_ANSWER_REPLY, actions, proposed)

        results = []
        for call in turn.tool_calls:
            try:
                result, is_error = run_tool(call.name, call.input, tool_context), False
            except ToolError as exc:
                result, is_error = {"error": str(exc)}, True
            except Exception:
                # A bug in a tool must not turn the whole chat turn into a 500.
                logger.exception("Assistant tool %s failed", call.name)
                result, is_error = {"error": TOOL_FAILED}, True
            actions.append({"tool": call.name, "input": call.input, "result": result})
            if not is_error and PROPOSAL_KEY in result:
                proposed.append(result[PROPOSAL_KEY])
            results.append(_tool_result_block(call.id, result, is_error))

        messages.append({"role": "assistant", "content": turn.assistant_content})
        messages.append({"role": "user", "content": results})

    return AssistantReply(GAVE_UP_REPLY, actions, proposed)


def _tool_result_block(tool_use_id, result, is_error):
    block = {
        "type": "tool_result",
        "tool_use_id": tool_use_id,
        "content": json.dumps(result, ensure_ascii=False),
    }
    if is_error:
        block["is_error"] = True
    return block
