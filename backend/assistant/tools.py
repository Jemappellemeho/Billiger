"""The assistant's tools: the read actions that need no confirmation (Ticket 14) and the
propose actions for changes (Ticket 15).

Each read tool is a thin adapter over the operation behind the matching REST
endpoint (`accounts.shopping_list`, `search.services`, `streaks.tracking`),
so the assistant can't see anything the API wouldn't show that account. The
only side effect is the one `POST /api/compare/` has too: a comparison
counts toward the weekly streak.

The write tools only *propose*: they store a pending proposal (`assistant.proposals`)
and hand the model its diff. Nothing is applied until the user accepts it in the
app, and no tool exists that could do that on their behalf — nor one for anything
account-sensitive (email, password, deletion, payment).
"""
import logging
from dataclasses import dataclass
from typing import Callable

from accounts import shopping_list
from assistant import proposals
from assistant.changes import ProposalInvalid
from search import services
from search.location import InvalidLocation
from streaks import tracking
from streaks.tracking import record_comparison

logger = logging.getLogger(__name__)


class ToolError(Exception):
    """A failure the model should hear about (and relay) rather than a crash."""


@dataclass
class ToolContext:
    user: object
    # The PLZ prices are looked up for: `zip_code(named)` prefers a PLZ the user named in the chat
    # (`named`), else the caller's location (explicit or reverse-geocoded from GPS). Raises ToolError.
    zip_code: Callable[[object], str]


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


def _resolve(source):
    try:
        return services.resolve_zip_code(source)
    except InvalidLocation as exc:
        if not any(source.get(key) for key in ("zip_code", "lat", "lon")):
            raise ToolError(
                "Der Standort des Nutzers ist unbekannt. Frage nach seiner Postleitzahl "
                "und übergib sie als zip_code."
            ) from exc
        raise ToolError(f"Der Standort ist ungültig: {exc}") from exc
    except Exception as exc:
        raise ToolError("Der Standort konnte nicht ermittelt werden.") from exc


def zip_code_resolver(source):
    """A `ToolContext.zip_code` reading the caller's location (zip_code | lat+lon) from `source`.

    Resolved lazily and at most once per chat turn (success or failure): a GPS fix costs a
    reverse-geocoding call, wasted on turns that need no prices.
    """
    outcome = []

    def resolve(named=None):
        if named:
            return _resolve({"zip_code": named})
        if not outcome:
            try:
                outcome.append(_resolve(source))
            except ToolError as exc:
                outcome.append(exc)
        if isinstance(outcome[0], ToolError):
            raise outcome[0]
        return outcome[0]

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

ZIP_CODE_PROPERTY = {
    "type": "string",
    "description": (
        "Optional: vierstellige PLZ, nur wenn der Nutzer in seiner Nachricht einen Ort nennt "
        "(oder wenn sein Standort unbekannt ist und er die PLZ genannt hat). Sonst weglassen."
    ),
}


def _search_product_prices(context, tool_input):
    query = tool_input.get("query")
    if not isinstance(query, str) or not query.strip():
        raise ToolError("Für die Preisabfrage fehlt der Produktname (query).")

    zip_code = context.zip_code(tool_input.get("zip_code"))
    try:
        groups = services.search_products(query.strip(), zip_code)
    except Exception as exc:
        raise ToolError(services.MARKTGURU_UNAVAILABLE) from exc
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

    compare_input = services.parse_compare_items(items)
    zip_code = context.zip_code(tool_input.get("zip_code"))
    try:
        comparison = services.compare_items(compare_input, zip_code)
    except Exception as exc:
        raise ToolError(services.MARKTGURU_UNAVAILABLE) from exc

    try:
        record_comparison(context.user, comparison)  # counts toward the weekly streak, like the app's
    except Exception:
        # The comparison itself succeeded; losing a streak tick must not cost the user it.
        logger.exception("Could not record the assistant's comparison for the streak")

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
        "hint": COMPARISON_HINT,
    }


# The key under which a propose tool hands its proposal to the agent layer (and the client).
PROPOSAL_KEY = "proposal"

PROPOSAL_NEXT_STEP = (
    "Der Vorschlag ist noch NICHT übernommen. Der Nutzer sieht jetzt den vollständigen Diff und kann "
    "ihn übernehmen, ändern oder verwerfen. Fasse die Änderung in ein, zwei Sätzen zusammen, sag, dass "
    "sie erst nach seiner Bestätigung gilt, und behaupte nie, etwas sei schon geändert."
)


def _propose(kind):
    def run(context, tool_input):
        try:
            proposal = proposals.create(
                context.user, kind, tool_input, current_zip_code=lambda: context.zip_code(None)
            )
        except ProposalInvalid as exc:
            raise ToolError(str(exc)) from exc
        return {PROPOSAL_KEY: proposals.serialize(proposal), "next_step": PROPOSAL_NEXT_STEP}

    return run


ITEM_PROPERTIES = {
    "name": {"type": "string", "description": "Produktname, z. B. „Milch“."},
    "brand": {"type": ["string", "null"], "description": "Marke, falls genannt oder bereits so in der Liste."},
    "quantity": {"type": "integer", "minimum": 1, "description": "Menge (Standard 1)."},
    "category": {
        "type": ["string", "null"],
        "description": "Kategorie; weglassen, um die bestehende beizubehalten.",
    },
}

PREFERENCE_LIST_PROPERTY = {"type": "array", "items": {"type": "string"}}

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
            "query": {"type": "string", "description": "Produktname, ggf. mit Marke, z. B. „Nutella“."},
            "zip_code": ZIP_CODE_PROPERTY,
        },
        required=("query",),
    ),
    Tool(
        name="compare_shopping_list",
        description=(
            "Fasst den Warenkorb-Vergleich der aktuellen Einkaufsliste zusammen: günstigster einzelner "
            "Laden (single_store), volle Aufteilung auf mehrere Läden (full_split) und die Stufen "
            "1 → N Läden mit der Zusatzersparnis je Stopp (ladder). Zählt wie der Vergleich in der "
            "App für die Wochen-Streak."
        ),
        run=_compare_shopping_list,
        properties={"zip_code": ZIP_CODE_PROPERTY},
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
    Tool(
        name="propose_shopping_list_change",
        description=(
            "Schlägt eine Änderung der Einkaufsliste vor (Artikel hinzufügen, entfernen, Menge ändern) — "
            "immer als EIN Vorschlag mit dem vollständigen neuen Listenstand, nie als einzelne Schritte. "
            "Hole vorher mit get_shopping_list den aktuellen Stand und schicke unter items die komplette "
            "neue Liste (unveränderte Artikel inklusive). Ändert nichts, bis der Nutzer übernimmt."
        ),
        run=_propose("shopping_list"),
        properties={
            "items": {
                "type": "array",
                "description": "Die vollständige neue Einkaufsliste.",
                "items": {"type": "object", "properties": ITEM_PROPERTIES, "required": ["name"]},
            }
        },
        required=("items",),
    ),
    Tool(
        name="propose_preferences_change",
        description=(
            "Schlägt eine Änderung der Präferenzen oder Favoriten vor (bevorzugte Marken, ausgeschlossene "
            "Zutaten oder Läden, Favoriten). Schicke nur die Teile, die sich ändern — jeweils als "
            "vollständigen neuen Stand dieses Teils (aktuellen Stand vorher mit get_shopping_list holen). "
            "Ändert nichts, bis der Nutzer übernimmt."
        ),
        run=_propose("preferences"),
        properties={
            "preferred_brands": {**PREFERENCE_LIST_PROPERTY, "description": "Bevorzugte Marken."},
            "excluded_ingredients": {**PREFERENCE_LIST_PROPERTY, "description": "Ausgeschlossene Zutaten."},
            "excluded_stores": {**PREFERENCE_LIST_PROPERTY, "description": "Ausgeschlossene Läden."},
            "favorite_items": {
                **PREFERENCE_LIST_PROPERTY,
                "description": (
                    "Artikel der Einkaufsliste (Name oder id), die Favoriten sein sollen — der vollständige "
                    "neue Stand aller Favoriten."
                ),
            },
        },
    ),
    Tool(
        name="propose_location_change",
        description=(
            "Schlägt vor, den Standort des Nutzers auf eine andere Postleitzahl zu ändern (z. B. „ich bin "
            "gerade in Graz“). Ändert nichts, bis der Nutzer übernimmt."
        ),
        run=_propose("location"),
        properties={
            "zip_code": {
                "type": "string",
                "description": "Vierstellige österreichische PLZ. Bei Unsicherheit beim Nutzer nachfragen.",
            }
        },
        required=("zip_code",),
    ),
]

_TOOLS_BY_NAME = {tool.name: tool for tool in TOOLS}

TOOL_DEFINITIONS = [tool.definition for tool in TOOLS]

NOT_SUPPORTED = (
    "Diese Fähigkeit hat der Assistent nicht. Du musst die Anfrage offen ablehnen, dem Nutzer sagen, "
    "dass es das (noch) nicht gibt, und wo sinnvoll die nächstbeste vorhandene Aktion anbieten. "
    "Improvisiere kein Ergebnis."
)


def run_tool(name, tool_input, context):
    tool = _TOOLS_BY_NAME.get(name)
    if tool is None:
        raise ToolError(f"Unbekanntes Werkzeug: {name}. {NOT_SUPPORTED}")
    return tool.run(context, tool_input)
