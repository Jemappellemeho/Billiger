"""The MCP tools: the assistant's four read and three propose actions (Tickets 14 and 15).

Each tool is a thin wrapper over the REST endpoint(s) behind the matching action (`ENDPOINT` in
the docstrings). Names, descriptions and input schemas come from the built-in assistant's own
tools, so both channels offer the same actions and the same wording. The three write tools only
propose: a change waits for the user's decision in Billiger, and — as for the built-in assistant —
no tool exists to accept one, nor for anything account-sensitive (email, password, deletion,
payment).
"""
from dataclasses import dataclass
from typing import Callable

from assistant.tools import TOOLS as ASSISTANT_TOOLS
from mcp_server.rest import RestResponse, call_rest

READ_SCOPE = "billiger:read"
WRITE_SCOPE = "billiger:write"

_ASSISTANT_TOOLS = {tool.name: tool for tool in ASSISTANT_TOOLS}

# An external client has no GPS fix to fall back on: it has to ask the user.
ZIP_CODE_PROPERTY = {
    "type": "string",
    "description": "Vierstellige PLZ, für die die Preise gelten. Frage den Nutzer danach, falls du sie nicht kennst.",
}

# Not `assistant.tools.PROPOSAL_NEXT_STEP`: there the user sees the diff in the chat, here the client
# has to show it and send the user to Billiger to decide. The app lists open proposals in the assistant
# panel (the 💬 button, with a badge for the count) without the user having to write anything first.
PROPOSAL_NEXT_STEP = (
    "Der Vorschlag ist noch NICHT übernommen. Zeige dem Nutzer den vollständigen Diff (proposal.diff) "
    "und sag ihm, dass die Änderung erst gilt, wenn er sie in der Billiger-App übernimmt (oder ändert oder "
    "verwirft): Dort zeigt der Assistent-Button (💬) die offenen Vorschläge an; er muss dafür nichts "
    "schreiben. Behaupte nie, etwas sei schon geändert."
)


@dataclass(frozen=True)
class McpTool:
    name: str
    description: str
    scope: str
    call: Callable[[object, dict], RestResponse]
    read_only: bool
    properties: dict
    required: tuple = ()

    @property
    def definition(self):
        return {
            "name": self.name,
            "description": self.description,
            "inputSchema": {"type": "object", "properties": self.properties, "required": list(self.required)},
            "annotations": {"readOnlyHint": self.read_only, "destructiveHint": False, "openWorldHint": False},
        }


def _get_shopping_list(user, arguments):
    """GET /api/shopping-list/"""
    return call_rest(user, "GET", "shopping-list")


def _get_savings_streak(user, arguments):
    """GET /api/streak/"""
    return call_rest(user, "GET", "streak")


def _search_product_prices(user, arguments):
    """GET /api/search/?q=&zip_code="""
    params = {"q": arguments.get("query"), "zip_code": arguments.get("zip_code")}
    return call_rest(user, "GET", "product-search", params=params)


def _compare_shopping_list(user, arguments):
    """GET /api/shopping-list/, then POST /api/compare/ with its items (counts toward the streak, like in the app)"""
    current = call_rest(user, "GET", "shopping-list")
    if not current.ok:
        return current
    return call_rest(
        user,
        "POST",
        "cart-comparison",
        body={"items": current.data["items"], "zip_code": arguments.get("zip_code")},
    )


def _propose(kind):
    def call(user, arguments):
        """POST /api/assistant/proposals/"""
        response = call_rest(user, "POST", "assistant-proposal-collection", body={**arguments, "kind": kind})
        if response.ok:
            response.data = {**response.data, "next_step": PROPOSAL_NEXT_STEP}
        return response

    return call


def _tool(name, scope, call, *, read_only, properties=None, required=None):
    assistant_tool = _ASSISTANT_TOOLS[name]
    return McpTool(
        name=name,
        description=assistant_tool.description,
        scope=scope,
        call=call,
        read_only=read_only,
        properties=assistant_tool.properties if properties is None else properties,
        required=assistant_tool.required if required is None else required,
    )


TOOLS = [
    _tool("get_shopping_list", READ_SCOPE, _get_shopping_list, read_only=True),
    _tool(
        "search_product_prices",
        READ_SCOPE,
        _search_product_prices,
        read_only=True,
        properties={**_ASSISTANT_TOOLS["search_product_prices"].properties, "zip_code": ZIP_CODE_PROPERTY},
        required=("query", "zip_code"),
    ),
    _tool(
        "compare_shopping_list",
        READ_SCOPE,
        _compare_shopping_list,
        read_only=True,
        properties={"zip_code": ZIP_CODE_PROPERTY},
        required=("zip_code",),
    ),
    _tool("get_savings_streak", READ_SCOPE, _get_savings_streak, read_only=True),
    _tool("propose_shopping_list_change", WRITE_SCOPE, _propose("shopping_list"), read_only=False),
    _tool("propose_preferences_change", WRITE_SCOPE, _propose("preferences"), read_only=False),
    _tool("propose_location_change", WRITE_SCOPE, _propose("location"), read_only=False),
]

TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}
