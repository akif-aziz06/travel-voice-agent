"""Atlas concierge tool layer.

This module is intentionally decoupled from the LiveKit agent runner
(``main.py``). It owns:

* Loading of the mock travel datasets (``data/destinations.json`` and
  ``data/rates.json``).
* The pure business logic for the two concierge tools.
* The LiveKit function-calling bindings (:class:`AtlasFunctions`) that the
  agent registers as ``fnc_ctx``.

Design notes
------------
LiveKit Agents (and its plugins) are heavy, optional dependencies. To keep the
tool logic unit-testable and importable in a bare environment — exactly the
isolation test documented in the README — this module degrades gracefully when
``livekit`` is not installed: the ``@ai_callable`` decorator and ``TypeInfo``
annotations become no-ops, while the plain ``async`` tool functions remain
fully functional.
"""

from __future__ import annotations

import json
import logging
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Any

logger = logging.getLogger("atlas.tools")

# ---------------------------------------------------------------------------
# Optional LiveKit binding layer
# ---------------------------------------------------------------------------
# When LiveKit is installed we register real function-calling metadata. When it
# is not, we fall back to inert shims so the rest of the module still imports
# and runs (pure-Python tool logic + offline tests).
try:
    from livekit.agents import llm  # type: ignore

    _FunctionContext = llm.FunctionContext
    _ai_callable = llm.ai_callable
    _TypeInfo = llm.TypeInfo
    LIVEKIT_AVAILABLE = True
except Exception as exc:  # pragma: no cover - exercised only without livekit
    logger.warning(
        "livekit.agents not importable (%s); tools will run in standalone "
        "mode without function-calling registration.",
        exc,
    )
    LIVEKIT_AVAILABLE = False

    class _FunctionContext:  # type: ignore
        """Inert stand-in for ``llm.FunctionContext``."""

    def _ai_callable(*_args: Any, **_kwargs: Any):  # type: ignore
        """No-op replacement for ``llm.ai_callable``; returns the function."""

        def _decorator(func):
            return func

        return _decorator

    class _TypeInfo:  # type: ignore
        """Inert stand-in for ``llm.TypeInfo`` usable inside ``Annotated``."""

        def __init__(self, *_args: Any, **_kwargs: Any) -> None:
            self.args = _args
            self.kwargs = _kwargs


# ---------------------------------------------------------------------------
# Dataset loading (cached, with structured error handling)
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
DESTINATIONS_PATH = DATA_DIR / "destinations.json"
RATES_PATH = DATA_DIR / "rates.json"

VALID_BUDGETS = ("budget", "mid", "luxury")
VALID_VIBES = ("beach", "culture", "adventure", "city", "wellness")


def _load_json(path: Path) -> Any:
    """Read and parse a JSON file with explicit, contextual error logging."""
    try:
        with path.open("r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError as exc:
        logger.error("Dataset missing at %s", path)
        raise RuntimeError(f"Required dataset not found: {path}") from exc
    except json.JSONDecodeError as exc:
        logger.error("Dataset at %s is not valid JSON: %s", path, exc)
        raise RuntimeError(f"Malformed dataset: {path}") from exc


@lru_cache(maxsize=1)
def load_destinations() -> list[dict[str, Any]]:
    """Return the curated destination bundles (cached after first read)."""
    data = _load_json(DESTINATIONS_PATH)
    if not isinstance(data, list) or not data:
        raise RuntimeError("destinations.json must be a non-empty JSON array.")
    logger.debug("Loaded %d curated destinations.", len(data))
    return data


@lru_cache(maxsize=1)
def load_rates() -> dict[str, dict[str, float]]:
    """Return the per-diem rate table (cached after first read)."""
    data = _load_json(RATES_PATH)
    if not isinstance(data, dict) or "__default__" not in data:
        raise RuntimeError("rates.json must be an object with a '__default__' key.")
    return data


# ---------------------------------------------------------------------------
# Input normalisation
# ---------------------------------------------------------------------------
_BUDGET_SYNONYMS = {
    "budget": "budget",
    "budget-friendly": "budget",
    "cheap": "budget",
    "affordable": "budget",
    "economy": "budget",
    "low": "budget",
    "mid": "mid",
    "mid-range": "mid",
    "midrange": "mid",
    "moderate": "mid",
    "medium": "mid",
    "standard": "mid",
    "luxury": "luxury",
    "premium": "luxury",
    "high-end": "luxury",
    "high": "luxury",
    "splurge": "luxury",
}

_VIBE_SYNONYMS = {
    "beach": "beach",
    "coastal": "beach",
    "island": "beach",
    "sea": "beach",
    "culture": "culture",
    "cultural": "culture",
    "history": "culture",
    "historic": "culture",
    "art": "culture",
    "adventure": "adventure",
    "adventurous": "adventure",
    "outdoor": "adventure",
    "thrill": "adventure",
    "hiking": "adventure",
    "city": "city",
    "urban": "city",
    "metropolitan": "city",
    "nightlife": "city",
    "wellness": "wellness",
    "spa": "wellness",
    "relax": "wellness",
    "retreat": "wellness",
    "yoga": "wellness",
}


def _normalize(value: str, synonyms: dict[str, str], valid: tuple[str, ...], label: str) -> str:
    """Map a free-form user term onto a canonical enum value.

    Falls back to the first valid value (rather than raising) so the concierge
    can always deliver a recommendation instead of an error.
    """
    key = (value or "").strip().lower()
    if key in synonyms:
        return synonyms[key]
    # Substring tolerance, e.g. "mid range budget" -> "mid".
    for term, canonical in synonyms.items():
        if term in key:
            return canonical
    logger.info("Unrecognized %s %r; defaulting to %r.", label, value, valid[0])
    return valid[0]


# ---------------------------------------------------------------------------
# Pure tool logic
# ---------------------------------------------------------------------------
def _select_bundle(budget: str, vibe: str) -> dict[str, Any]:
    """Return exactly one bundle, gracefully broadening the match if needed."""
    dataset = load_destinations()

    exact = next(
        (d for d in dataset if d.get("budget") == budget and d.get("vibe") == vibe),
        None,
    )
    if exact is not None:
        return exact

    # Graceful fallback chain (mirrors PRD §6.2 "broaden the vibe" behaviour).
    by_vibe = next((d for d in dataset if d.get("vibe") == vibe), None)
    if by_vibe is not None:
        logger.info("No %s/%s bundle; broadened to vibe-only match.", budget, vibe)
        return by_vibe

    by_budget = next((d for d in dataset if d.get("budget") == budget), None)
    if by_budget is not None:
        logger.info("No %s/%s bundle; broadened to budget-only match.", budget, vibe)
        return by_budget

    logger.info("No %s/%s bundle; returning first curated entry.", budget, vibe)
    return dataset[0]


def _per_diem_for(destination: str) -> dict[str, float]:
    """Look up the per-diem rates for a destination, defaulting if unknown."""
    rates = load_rates()
    if destination in rates:
        return rates[destination]
    # Case-insensitive secondary match before defaulting.
    lowered = destination.strip().lower()
    for name, table in rates.items():
        if name != "__default__" and name.lower() == lowered:
            return table
    logger.info("No rate table for %r; using __default__ rates.", destination)
    return rates["__default__"]


def _compute_budget(destination: str, days: int, travelers: int) -> dict[str, Any]:
    """Explicit local trip-cost estimation: baseline rates × days × party size."""
    days = max(1, int(days))
    travelers = max(1, int(travelers))
    rate = _per_diem_for(destination)

    flights = round(rate["avg_flight_usd"] * travelers)
    hotels = round(rate["hotel_per_night"] * days)  # one room shared by the party
    food = round(rate["food_per_day"] * days * travelers)
    activities = round(rate["activities_per_day"] * days * travelers)
    total = flights + hotels + food + activities

    return {
        "destination": destination,
        "days": days,
        "travelers": travelers,
        "breakdown": {
            "flights": flights,
            "hotels": hotels,
            "food": food,
            "activities": activities,
        },
        "total_estimate_usd": total,
        "per_traveler_usd": round(total / travelers),
    }


# ---------------------------------------------------------------------------
# Public async tools (directly callable — matches README isolation tests)
# ---------------------------------------------------------------------------
async def search_curated_destinations(budget: str, vibe: str) -> str:
    """Return exactly one curated flight + hotel bundle as a JSON string.

    Triggered once Atlas knows the traveler's budget tier and vibe. Returns a
    single highly tailored bundle to actively resolve decision paralysis.
    """
    norm_budget = _normalize(budget, _BUDGET_SYNONYMS, VALID_BUDGETS, "budget")
    norm_vibe = _normalize(vibe, _VIBE_SYNONYMS, VALID_VIBES, "vibe")
    bundle = _select_bundle(norm_budget, norm_vibe)
    logger.info(
        "search_curated_destinations(%s, %s) -> %s",
        norm_budget,
        norm_vibe,
        bundle.get("destination"),
    )
    return json.dumps(bundle)


async def calculate_trip_budget(destination: str, days: int, travelers: int) -> str:
    """Estimate the full trip cost as a JSON string (pure local computation)."""
    result = _compute_budget(destination, days, travelers)
    logger.info(
        "calculate_trip_budget(%s, days=%s, travelers=%s) -> $%s",
        destination,
        result["days"],
        result["travelers"],
        result["total_estimate_usd"],
    )
    return json.dumps(result)


# ---------------------------------------------------------------------------
# LiveKit function-calling context
# ---------------------------------------------------------------------------
class AtlasFunctions(_FunctionContext):
    """Function-calling context bound to the Atlas voice agent.

    Each method is registered with LiveKit via ``@ai_callable`` and delegates to
    the decoupled pure-logic tools above, keeping registration and logic
    cleanly separated.
    """

    @_ai_callable(
        description=(
            "Search for a single curated flight and hotel bundle matching the "
            "traveler's budget tier and travel vibe. Call this as soon as both "
            "the budget and the vibe are known."
        )
    )
    async def search_curated_destinations(
        self,
        budget: Annotated[
            str,
            _TypeInfo(description="Budget tier: 'budget', 'mid', or 'luxury'."),
        ],
        vibe: Annotated[
            str,
            _TypeInfo(
                description=(
                    "Travel vibe: 'beach', 'culture', 'adventure', 'city', or "
                    "'wellness'."
                )
            ),
        ],
    ) -> str:
        return await search_curated_destinations(budget=budget, vibe=vibe)

    @_ai_callable(
        description=(
            "Calculate an estimated total trip budget in USD from a "
            "destination, the number of days, and the number of travelers. Call "
            "this when the user asks how much a trip will cost."
        )
    )
    async def calculate_trip_budget(
        self,
        destination: Annotated[
            str,
            _TypeInfo(description="Destination city/country, e.g. 'Hvar, Croatia'."),
        ],
        days: Annotated[
            int,
            _TypeInfo(description="Number of trip days (whole number)."),
        ],
        travelers: Annotated[
            int,
            _TypeInfo(description="Number of travelers in the party."),
        ],
    ) -> str:
        return await calculate_trip_budget(
            destination=destination, days=days, travelers=travelers
        )


# ---------------------------------------------------------------------------
# Manual / offline smoke test
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    import asyncio

    logging.basicConfig(level=logging.INFO)

    async def _smoke() -> None:
        bundle = await search_curated_destinations(budget="mid", vibe="beach")
        print(json.dumps(json.loads(bundle), indent=2))
        estimate = await calculate_trip_budget(
            destination="Hvar, Croatia", days=7, travelers=2
        )
        print(json.dumps(json.loads(estimate), indent=2))

    asyncio.run(_smoke())
