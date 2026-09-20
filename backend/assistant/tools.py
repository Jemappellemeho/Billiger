"""The assistant's read-only tools (Ticket 14).

Each tool is a thin adapter over the operation behind the matching REST
endpoint (`accounts.shopping_list`, `search.services`, `streaks.tracking`),
so the assistant can't see anything the API wouldn't show that account.
Nothing here changes state.
"""
from dataclasses import dataclass
from typing import Callable

from accounts import shopping_list
from search import services
from search.location import InvalidLocation
from streaks import tracking


class ToolError(Exception):
    """A failure the model should hear about (and relay) rather than a crash."""


@dataclass
class ToolContext:
    user: object
    # The caller's PLZ (explicit or reverse-geocoded from GPS); raises ToolError if unknown.
    zip_code: Callable[[], str]


@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    run: Callable[[ToolContext, dict], dict]
    properties: dict
    required: tuple = ()

    @property
    def definition(self):
        return {
            "name": self.name,
            "description": self.description,
            "input_schema": {
                "type": "object",
                "properties": self.properties,
                "required": list(self.required),
            },
        }


def zip_code_resolver(source):
    """A memoised `ToolContext.zip_code` reading the caller's location (zip_code | lat+lon) from `source`.

    Resolved lazily: a GPS fix costs a reverse-geocoding call, wasted on turns that need no prices.
    """
    resolved = []

    def resolve():
        if not resolved:
            try:
                resolved.append(services.resolve_zip_code(source))
            except InvalidLocation as exc:
                if not any(source.get(key) for key in ("zip_code", "lat", "lon")):
                    raise ToolError(
                        "Der Standort des Nutzers ist unbekannt. Frage nach seiner Postleitzahl."
                    ) from exc
                raise ToolError(f"Der Standort ist ungültig: {exc}") from exc
            except Exception as exc:
                raise ToolError("Der Standort konnte nicht ermittelt werden.") from exc
        return resolved[0]

    return resolve


def _get_shopping_list(context, tool_input):
    return shopping_list.load(context.user)


# The weekly history grows without bound; the model gets the latest weeks and is told how many were left out.
STREAK_HISTORY_WEEKS = 12


def _get_savings_streak(context, tool_input):
    summary = tracking.summary(context.user)
    history = summary["history"]
    return {
        **summary,
        "history": history[-STREAK_HISTORY_WEEKS:],
        "history_omitted_weeks": max(len(history) - STREAK_HISTORY_WEEKS, 0),
    }


# Products handed to the model per price query (cheaper answers, and nobody wants a list of thirty).
MAX_SEARCH_RESULTS = 5

MARKTGURU_UNAVAILABLE = "Marktguru ist derzeit nicht erreichbar."


def _search_product_prices(context, tool_input):
    query = tool_input.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("Für die Preisabfrage fehlt der Produktname (query).")

    zip_code = context.zip_code()
    try:
        groups = services.search_products(query.strip(), zip_code)
    except Exception as exc:
        raise ToolError(MARKTGURU_UNAVAILABLE) from exc
    return {
        "query": query.strip(),
        "zip_code": zip_code,
        "results": groups[:MAX_SEARCH_RESULTS],
        "results_omitted": max(len(groups) - MAX_SEARCH_RESULTS, 0),
    }


COMPARISON_HINT = (
    "Fragen, wie viele Stopps sich lohnen oder wie die Aufteilung bei einer bestimmten Stopp-Anzahl "
    "aussieht, beantwortest du nicht selbst: Verweise auf den interaktiven Regler in der "
    "Warenkorb-Vergleich-Ansicht der App. Die Stufen unter „ladder“ sind nur der Überblick."
)


def _compare_shopping_list(context, tool_input):
    items = shopping_list.load(context.user)["items"]
    if not items:
        raise ToolError("Die Einkaufsliste ist leer, es gibt nichts zu vergleichen.")

    compare_input = services.parse_compare_items(
        [{"name": i["name"], "brand": i["brand"], "quantity": i["quantity"]} for i in items]
    )
    zip_code = context.zip_code()
    try:
        comparison = services.compare_items(compare_input, zip_code)
    except Exception as exc:
        raise ToolError(MARKTGURU_UNAVAILABLE) from exc

    # Only reads the comparison: unlike POST /api/compare/ this does not tick the weekly streak.
    return {
        "zip_code": zip_code,
        "unavailable_items": comparison["unavailable_items"],
        "store_totals": comparison["store_totals"],
        "single_store": comparison["single_store"],
        "full_split": comparison["full_split"],
        "ladder": [
            {key: rung[key] for key in ("stops", "stores", "total", "marginal_savings")}
            for rung in comparison["ladder"]
        ],
        "hinweis": COMPARISON_HINT,
    }


TOOLS = [
    Tool(
        name="get_shopping_list",
        description=(
            "Liefert die aktuelle Einkaufsliste des Nutzers (Artikel mit Menge, Marke, Kategorie, "
            "Favorit) samt Präferenzen (bevorzugte Marken, ausgeschlossene Zutaten und Läden)."
        ),
        run=_get_shopping_list,
        properties={},
    ),
    Tool(
        name="search_product_prices",
        description=(
            "Ad-hoc-Preisabfrage: wo ein einzelnes Produkt aktuell am günstigsten ist. Liefert passende "
            "Produkte mit Angeboten je Laden (Preis, regulärer Preis) und dem günstigsten Angebot. "
            "Verändert weder Einkaufsliste noch sonst etwas."
        ),
        run=_search_product_prices,
        properties={
            "query": {"type": "string", "description": "Produktname, ggf. mit Marke, z. B. „Nutella“."}
        },
        required=("query",),
    ),
    Tool(
        name="compare_shopping_list",
        description=(
            "Fasst den Warenkorb-Vergleich der aktuellen Einkaufsliste zusammen: günstigster einzelner "
            "Laden (single_store), volle Aufteilung auf mehrere Läden (full_split) und die Stufen "
            "1 → N Läden mit der Zusatzersparnis je Stopp (ladder). Nur lesend."
        ),
        run=_compare_shopping_list,
        properties={},
    ),
    Tool(
        name="get_savings_streak",
        description=(
            "Liefert Ersparnis und Streak des Nutzers: Streak-Status (none/active/pending/paused, "
            "Wochen, verpasste Wochen, zuletzt abgeschlossene Woche), Ersparnis dieser Woche mit "
            "Anteil je Laden/Produkt, Gesamtersparnis (gegenüber teuerstem und regulärem Preis) und "
            "die Wochen-Historie (jüngste Wochen; history_omitted_weeks nennt ältere, nicht gelieferte)."
        ),
        run=_get_savings_streak,
        properties={},
    ),
]

_TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

TOOL_DEFINITIONS = [tool.definition for tool in TOOLS]


def run_tool(name, tool_input, context):
    tool = _TOOLS_BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"Unbekanntes Werkzeug: {name}")
    return tool.run(context, tool_input)
