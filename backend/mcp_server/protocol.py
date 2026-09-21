"""The MCP wire protocol (Streamable HTTP, JSON responses only): JSON-RPC 2.0 messages in, results out.

Stateless on purpose: no sessions, no server-initiated messages. The server offers tools and
nothing else.
"""
import json
import logging

from mcp_server.tools import TOOLS, TOOLS_BY_NAME

logger = logging.getLogger(__name__)

# Newest first; a client asking for another version is answered with the newest one we speak.
SUPPORTED_PROTOCOL_VERSIONS = ("2025-11-25", "2025-06-18", "2025-03-26")

INSTRUCTIONS = (
    "Billiger vergleicht Supermarkt-Aktionen in Österreich. Lesende Werkzeuge liefern Preise, die "
    "Einkaufsliste, den Warenkorb-Vergleich und die Ersparnis. Die propose_*-Werkzeuge ändern nichts: "
    "sie legen einen Vorschlag an, den der Nutzer in Billiger selbst übernimmt, ändert oder verwirft."
)

PARSE_ERROR = -32700
INVALID_REQUEST = -32600
METHOD_NOT_FOUND = -32601
INVALID_PARAMS = -32602

TOOL_FAILED = "Das Werkzeug ist gerade ausgefallen."


def error(code, message, request_id=None):
    return {"jsonrpc": "2.0", "id": request_id, "error": {"code": code, "message": message}}


def parse(body):
    """The JSON-RPC message in `body`, or the error response to send instead: `(message, error_response)`."""
    try:
        message = json.loads(body)
    except ValueError:
        return None, error(PARSE_ERROR, "Die Anfrage ist kein gültiges JSON.")
    if isinstance(message, list):
        return None, error(INVALID_REQUEST, "Gebündelte Anfragen (Batching) werden nicht unterstützt.")
    if not isinstance(message, dict) or message.get("jsonrpc") != "2.0":
        return None, error(INVALID_REQUEST, "Keine gültige JSON-RPC-2.0-Nachricht.")
    return message, None


def handle(message, user, token_scopes):
    """The response to one message; `None` for notifications and client responses, which get no answer."""
    if "method" not in message or "id" not in message:
        return None

    request_id, method, params = message["id"], message["method"], message.get("params") or {}
    if not isinstance(method, str) or not isinstance(params, dict):
        return error(INVALID_REQUEST, "method muss ein String und params ein Objekt sein.", request_id)

    if method == "initialize":
        result = _initialize(params)
    elif method == "ping":
        result = {}
    elif method == "tools/list":
        result = {"tools": [tool.definition for tool in TOOLS if tool.scope in token_scopes]}
    elif method == "tools/call":
        result = _call_tool(params, user, token_scopes)
        if "error" in result:
            return error(result["error"]["code"], result["error"]["message"], request_id)
    else:
        return error(METHOD_NOT_FOUND, f"Unbekannte Methode: {method}", request_id)
    return {"jsonrpc": "2.0", "id": request_id, "result": result}


def _initialize(params):
    requested = params.get("protocolVersion")
    return {
        "protocolVersion": requested if requested in SUPPORTED_PROTOCOL_VERSIONS else SUPPORTED_PROTOCOL_VERSIONS[0],
        "capabilities": {"tools": {"listChanged": False}},
        "serverInfo": {"name": "billiger", "title": "Billiger", "version": "1.0.0"},
        "instructions": INSTRUCTIONS,
    }


def _call_tool(params, user, token_scopes):
    tool = TOOLS_BY_NAME.get(params.get("name"))
    arguments = params.get("arguments") or {}
    if tool is None:
        return {"error": {"code": INVALID_PARAMS, "message": f"Unbekanntes Werkzeug: {params.get('name')}"}}
    if not isinstance(arguments, dict):
        return {"error": {"code": INVALID_PARAMS, "message": "arguments muss ein Objekt sein."}}
    if tool.scope not in token_scopes:
        return _tool_error(
            f"Dafür fehlt die Berechtigung „{tool.scope}“. Der Nutzer muss Billiger neu verbinden und den Zugriff erlauben."
        )

    try:
        response = tool.call(user, arguments)
    except Exception:
        # A bug behind a tool must not turn the whole call into a 500.
        logger.exception("MCP tool %s failed", tool.name)
        return _tool_error(TOOL_FAILED)

    if not response.ok:
        detail = response.data.get("detail") if isinstance(response.data, dict) else None
        return _tool_error(detail or json.dumps(response.data, ensure_ascii=False))
    return {
        "content": [{"type": "text", "text": json.dumps(response.data, ensure_ascii=False)}],
        "structuredContent": response.data,
        "isError": False,
    }


def _tool_error(message):
    return {"content": [{"type": "text", "text": message}], "isError": True}
