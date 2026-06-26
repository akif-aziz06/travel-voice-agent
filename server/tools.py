"""Atlas concierge tool layer.

This module is intentionally decoupled from the LiveKit agent runner
(``main.py``). It owns:

* Loading of the mock travel datasets (``data/destinations.json`` and
  ``data/rates.json``).
* The pure business logic for the two concierge tools.

The LiveKit function-calling bindings (``@function_tool``) live in
``main.py`` inside the ``AtlasAgent`` class. They delegate to the pure
async tool functions exported here.

Design notes
------------
This module has zero dependency on LiveKit — it is pure Python. This
makes the tool logic unit-testable and importable in a bare environment,
exactly matching the isolation test documented in the README.
"""

from __future__ import annotations

import json
import logging
import os
from datetime import date, datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import httpx

logger = logging.getLogger("atlas.tools")

# ---------------------------------------------------------------------------
# Dataset loading (cached, with structured error handling)
# ---------------------------------------------------------------------------
DATA_DIR = Path(__file__).resolve().parent / "data"
DESTINATIONS_PATH = DATA_DIR / "destinations.json"
RATES_PATH = DATA_DIR / "rates.json"
VISA_PATH = DATA_DIR / "visa.json"

# Shared async HTTP timeout for all outbound calls (keeps the voice loop snappy).
_HTTP_TIMEOUT = httpx.Timeout(8.0, connect=4.0)

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


@lru_cache(maxsize=1)
def load_visa() -> dict[str, dict[str, dict[str, str]]]:
    """Return the origin→destination visa matrix (cached after first read)."""
    data = _load_json(VISA_PATH)
    requirements = data.get("requirements") if isinstance(data, dict) else None
    if not isinstance(requirements, dict) or not requirements:
        raise RuntimeError("visa.json must contain a non-empty 'requirements' object.")
    return requirements


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


# ===========================================================================
# Tool 3: Live weather — Open-Meteo (free, no API key)
# ===========================================================================
# WMO weather interpretation codes (subset covering all Open-Meteo values).
_WMO_CODES: dict[int, tuple[str, str]] = {
    0: ("clear sky", "☀️"),
    1: ("mainly clear", "🌤️"),
    2: ("partly cloudy", "⛅"),
    3: ("overcast", "☁️"),
    45: ("foggy", "🌫️"),
    48: ("rime fog", "🌫️"),
    51: ("light drizzle", "🌦️"),
    53: ("drizzle", "🌦️"),
    55: ("heavy drizzle", "🌧️"),
    56: ("freezing drizzle", "🌧️"),
    57: ("freezing drizzle", "🌧️"),
    61: ("light rain", "🌦️"),
    63: ("rain", "🌧️"),
    65: ("heavy rain", "🌧️"),
    66: ("freezing rain", "🌧️"),
    67: ("freezing rain", "🌧️"),
    71: ("light snow", "🌨️"),
    73: ("snow", "🌨️"),
    75: ("heavy snow", "❄️"),
    77: ("snow grains", "🌨️"),
    80: ("rain showers", "🌦️"),
    81: ("rain showers", "🌧️"),
    82: ("violent rain showers", "⛈️"),
    85: ("snow showers", "🌨️"),
    86: ("heavy snow showers", "❄️"),
    95: ("thunderstorm", "⛈️"),
    96: ("thunderstorm with hail", "⛈️"),
    99: ("thunderstorm with hail", "⛈️"),
}

OPEN_METEO_URL = "https://api.open-meteo.com/v1/forecast"


def _describe_weather_code(code: int) -> tuple[str, str]:
    """Map a WMO weather code to (description, emoji), defaulting gracefully."""
    return _WMO_CODES.get(int(code), ("unsettled weather", "🌍"))


async def fetch_weather(latitude: float, longitude: float) -> dict[str, Any]:
    """Fetch current conditions from Open-Meteo. Never raises — returns a dict
    with ``available=False`` on any failure so the agent degrades gracefully.
    """
    params = {
        "latitude": latitude,
        "longitude": longitude,
        "current": "temperature_2m,weather_code",
    }
    try:
        async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
            resp = await client.get(OPEN_METEO_URL, params=params)
            resp.raise_for_status()
            payload = resp.json()
        current = payload.get("current", {})
        units = payload.get("current_units", {})
        code = int(current.get("weather_code", -1))
        description, emoji = _describe_weather_code(code)
        return {
            "available": True,
            "latitude": latitude,
            "longitude": longitude,
            "temperature": current.get("temperature_2m"),
            "temperature_unit": units.get("temperature_2m", "°C"),
            "weather_code": code,
            "description": description,
            "emoji": emoji,
        }
    except (httpx.HTTPError, ValueError, KeyError) as exc:
        logger.warning("Open-Meteo lookup failed for (%s, %s): %s", latitude, longitude, exc)
        return {
            "available": False,
            "latitude": latitude,
            "longitude": longitude,
            "description": "weather data is temporarily unavailable",
            "emoji": "🌍",
        }


def format_weather(data: dict[str, Any]) -> str:
    """Render a weather dict as a single clean spoken sentence."""
    if not data.get("available"):
        return "I couldn't pull live weather right now, but I can still plan around it."
    temp = data.get("temperature")
    unit = data.get("temperature_unit", "°C")
    desc = data.get("description", "mild conditions")
    if temp is None:
        return f"It's currently {desc} there."
    return f"It's about {round(float(temp))}{unit} with {desc} there right now."


async def check_weather(latitude: float, longitude: float) -> str:
    """Return a clean, summarized string of the current weather at a coordinate."""
    data = await fetch_weather(latitude, longitude)
    summary = format_weather(data)
    logger.info("check_weather(%s, %s) -> %s", latitude, longitude, summary)
    return summary


# ===========================================================================
# Tool 4: Visa requirements — local matrix (no external API)
# ===========================================================================
_COUNTRY_SYNONYMS = {
    "pakistan": "Pakistan",
    "pk": "Pakistan",
    "usa": "United States",
    "us": "United States",
    "u.s.": "United States",
    "u.s.a.": "United States",
    "america": "United States",
    "united states": "United States",
    "united states of america": "United States",
    "uk": "United Kingdom",
    "u.k.": "United Kingdom",
    "britain": "United Kingdom",
    "great britain": "United Kingdom",
    "england": "United Kingdom",
    "united kingdom": "United Kingdom",
    "india": "India",
    "in": "India",
    "uae": "United Arab Emirates",
    "u.a.e.": "United Arab Emirates",
    "emirates": "United Arab Emirates",
    "dubai": "United Arab Emirates",
    "united arab emirates": "United Arab Emirates",
    "croatia": "Croatia",
    "turkey": "Turkey",
    "turkiye": "Turkey",
    "türkiye": "Turkey",
    "thailand": "Thailand",
    "japan": "Japan",
    "indonesia": "Indonesia",
    "bali": "Indonesia",
    "mexico": "Mexico",
    "singapore": "Singapore",
    "switzerland": "Switzerland",
}


def _canonical_country(name: str) -> str:
    """Best-effort mapping of a free-form country/place name to a canonical key."""
    key = (name or "").strip().lower()
    if key in _COUNTRY_SYNONYMS:
        return _COUNTRY_SYNONYMS[key]
    for term, canonical in _COUNTRY_SYNONYMS.items():
        if term in key:
            return canonical
    # Title-case fallback keeps unknown countries readable in the response.
    return (name or "").strip().title()


def get_visa_requirement(origin_country: str, destination_country: str) -> dict[str, str]:
    """Return structured visa guidance for an origin → destination pair."""
    origin = _canonical_country(origin_country)
    destination = _canonical_country(destination_country)

    # Same-country trips are domestic — no visa or border control applies.
    if origin and origin == destination:
        return {
            "origin": origin,
            "destination": destination,
            "requirement": "No visa required",
            "details": (
                f"This is domestic travel within {origin} — no visa or border "
                "crossing is involved."
            ),
            "max_stay": "",
            "known": True,
            "domestic": True,
        }

    matrix = load_visa()

    entry = matrix.get(origin, {}).get(destination)
    if entry:
        return {
            "origin": origin,
            "destination": destination,
            "requirement": entry.get("requirement", "Check with consulate"),
            "details": entry.get("details", ""),
            "max_stay": entry.get("max_stay", ""),
            "known": True,
        }

    logger.info("No visa entry for %s -> %s; returning advisory default.", origin, destination)
    return {
        "origin": origin,
        "destination": destination,
        "requirement": "Check official sources",
        "details": (
            f"I don't have {origin}-to-{destination} rules on hand; "
            "confirm with the destination's official consulate before booking."
        ),
        "max_stay": "",
        "known": False,
    }


def format_visa(data: dict[str, str]) -> str:
    """Render visa guidance as a concise spoken sentence."""
    if data.get("domestic"):
        return (
            f"Good news — traveling within {data.get('destination', 'the country')} "
            "is domestic, so you won't need a visa at all."
        )
    requirement = data.get("requirement", "")
    origin = data.get("origin", "")
    destination = data.get("destination", "")
    max_stay = data.get("max_stay", "")
    stay = f" for up to {max_stay}" if max_stay else ""
    return (
        f"For {origin} passport holders, {destination} is "
        f"{requirement.lower()}{stay}."
    )


async def check_visa_requirements(origin_country: str, destination_country: str) -> str:
    """Return the visa requirement string for an origin → destination pair."""
    data = get_visa_requirement(origin_country, destination_country)
    summary = format_visa(data)
    logger.info(
        "check_visa_requirements(%s -> %s) -> %s",
        data["origin"],
        data["destination"],
        data["requirement"],
    )
    return summary


# ===========================================================================
# Tool 5: Hotel search — Booking.com via RapidAPI with mock fallback
# ===========================================================================
# Uses the booking-com15 RapidAPI (simple header auth, no OAuth). Two-step flow:
#   1. searchDestination(query=city) -> dest_id + search_type
#   2. searchHotels(dest_id, ...)    -> hotel list
RAPIDAPI_HOST = "booking-com15.p.rapidapi.com"
BOOKING_SEARCH_DEST_URL = f"https://{RAPIDAPI_HOST}/api/v1/hotels/searchDestination"
BOOKING_SEARCH_HOTELS_URL = f"https://{RAPIDAPI_HOST}/api/v1/hotels/searchHotels"

# How far out to default the check-in when the caller doesn't give a date.
_DEFAULT_LEAD_DAYS = 30


def _rapidapi_key() -> str | None:
    key = os.getenv("RAPIDAPI_KEY", "").strip()
    if not key or key.lower().startswith(("your", "rapidapi_xxx", "xxx")):
        return None
    return key


def _booking_headers(key: str) -> dict[str, str]:
    return {"x-rapidapi-key": key, "x-rapidapi-host": RAPIDAPI_HOST}


def _resolve_stay_dates(check_in_date: str | None, nights: int) -> tuple[str, str, int]:
    """Return (arrival_iso, departure_iso, nights), defaulting sensibly."""
    nights = max(1, int(nights))
    if check_in_date:
        try:
            arrival = datetime.strptime(check_in_date.strip(), "%Y-%m-%d").date()
        except ValueError:
            logger.info("Unparseable check_in_date %r; defaulting.", check_in_date)
            arrival = date.today() + timedelta(days=_DEFAULT_LEAD_DAYS)
    else:
        arrival = date.today() + timedelta(days=_DEFAULT_LEAD_DAYS)
    departure = arrival + timedelta(days=nights)
    return arrival.isoformat(), departure.isoformat(), nights


def _upscale_photo(url: str | None) -> str | None:
    """Swap Booking's tiny square60 thumbnail for a crisper square240."""
    if not url:
        return None
    return url.replace("/square60/", "/square240/")


async def _booking_search_destination(
    client: httpx.AsyncClient, key: str, city: str
) -> tuple[str, str] | None:
    """Resolve a city name to (dest_id, search_type) via searchDestination."""
    resp = await client.get(
        BOOKING_SEARCH_DEST_URL,
        params={"query": city},
        headers=_booking_headers(key),
    )
    resp.raise_for_status()
    results = resp.json().get("data") or []
    if not results:
        return None
    # Prefer an actual city; otherwise take the first (most relevant) result.
    best = next((r for r in results if r.get("dest_type") == "city"), results[0])
    dest_id = best.get("dest_id")
    search_type = (best.get("search_type") or best.get("dest_type") or "city").upper()
    if not dest_id:
        return None
    return str(dest_id), search_type


async def _booking_search_hotels(
    client: httpx.AsyncClient,
    key: str,
    dest_id: str,
    search_type: str,
    arrival: str,
    departure: str,
    adults: int,
    nights: int,
) -> list[dict[str, Any]]:
    """Fetch and normalise the top 3 hotels for a resolved destination."""
    resp = await client.get(
        BOOKING_SEARCH_HOTELS_URL,
        params={
            "dest_id": dest_id,
            "search_type": search_type,
            "arrival_date": arrival,
            "departure_date": departure,
            "adults": max(1, int(adults)),
            "room_qty": 1,
            "units": "metric",
            "languagecode": "en-us",
            "currency_code": "USD",
        },
        headers=_booking_headers(key),
    )
    resp.raise_for_status()
    raw = (resp.json().get("data") or {}).get("hotels") or []
    return _normalize_booking_hotels(raw, nights)


def _normalize_booking_hotels(raw: list[dict[str, Any]], nights: int) -> list[dict[str, Any]]:
    """Map Booking's `data.hotels[]` into the top-3 Atlas hotel-card shape.

    Pure function (no I/O) so it can be unit-tested against sample payloads.
    """
    nights = max(1, int(nights))
    hotels: list[dict[str, Any]] = []
    for item in raw[:3]:
        prop = item.get("property", {})
        gross = (prop.get("priceBreakdown") or {}).get("grossPrice") or {}
        total = gross.get("value")
        # grossPrice is the total for the stay; divide by nights for per-night.
        per_night = (
            round(float(total) / nights) if isinstance(total, (int, float)) else None
        )
        stars = prop.get("accuratePropertyClass") or prop.get("propertyClass")
        review = prop.get("reviewScore")
        hotels.append(
            {
                "name": prop.get("name", "Unnamed property"),
                "hotel_id": prop.get("id"),
                "rating": int(stars) if isinstance(stars, (int, float)) and stars else None,
                "price_per_night_usd": per_night,
                "currency": gross.get("currency", "USD"),
                "review_score": review if isinstance(review, (int, float)) and review else None,
                "review_word": prop.get("reviewScoreWord") or None,
                "photo_url": _upscale_photo((prop.get("photoUrls") or [None])[0]),
                "highlights": None,
            }
        )
    return hotels


def _mock_hotels(city: str) -> list[dict[str, Any]]:
    """Fallback hotels sourced from the curated destinations dataset."""
    dataset = load_destinations()
    lowered = (city or "").strip().lower()
    matches = [
        d for d in dataset
        if lowered and lowered in d.get("destination", "").lower()
    ]
    pool = matches or dataset[:3]
    hotels: list[dict[str, Any]] = []
    for entry in pool[:3]:
        hotel = entry.get("hotel", {})
        hotels.append(
            {
                "name": hotel.get("name", "Boutique Stay"),
                "hotel_id": entry.get("id"),
                "rating": hotel.get("stars"),
                "price_per_night_usd": hotel.get("price_per_night_usd"),
                "currency": "USD",
                "review_score": None,
                "review_word": None,
                "photo_url": None,
                "highlights": hotel.get("highlights"),
            }
        )
    return hotels


async def fetch_accommodations(
    city: str,
    check_in_date: str | None = None,
    nights: int = 2,
    adults: int = 2,
) -> dict[str, Any]:
    """Return up to 3 hotels for a city. Tries Booking.com (RapidAPI), then
    falls back to curated mock data on any failure or missing key — never raises.
    """
    key = _rapidapi_key()
    arrival, departure, nights = _resolve_stay_dates(check_in_date, nights)

    if key:
        try:
            async with httpx.AsyncClient(timeout=_HTTP_TIMEOUT) as client:
                resolved = await _booking_search_destination(client, key, city)
                if resolved:
                    dest_id, search_type = resolved
                    hotels = await _booking_search_hotels(
                        client, key, dest_id, search_type,
                        arrival, departure, adults, nights,
                    )
                    if hotels:
                        logger.info("Booking.com returned %d hotels for %s.", len(hotels), city)
                        return {
                            "city": city,
                            "source": "booking",
                            "check_in": arrival,
                            "check_out": departure,
                            "hotels": hotels,
                        }
                    logger.info("Booking.com returned no hotels for %s; using mock.", city)
                else:
                    logger.info("Booking.com had no destination for %r; using mock.", city)
        except Exception:  # noqa: BLE001 - fall back on ANY failure (network/auth/parse)
            logger.exception("Booking.com hotel search failed for %s; using mock.", city)
    else:
        logger.info("RAPIDAPI_KEY absent; using mock hotels for %s.", city)

    return {
        "city": city,
        "source": "mock",
        "check_in": arrival,
        "check_out": departure,
        "hotels": _mock_hotels(city),
    }


async def search_accommodations(
    city: str,
    check_in_date: str | None = None,
    nights: int = 2,
    adults: int = 2,
) -> str:
    """Return the top hotels for a city as a JSON string (Booking.com or mock)."""
    result = await fetch_accommodations(
        city, check_in_date=check_in_date, nights=nights, adults=adults
    )
    logger.info(
        "search_accommodations(%s) -> %d hotels via %s",
        city,
        len(result["hotels"]),
        result["source"],
    )
    return json.dumps(result)


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
        print(await check_visa_requirements("Pakistan", "Croatia"))
        print(await check_weather(43.17, 16.44))  # Hvar; falls back if offline
        hotels = await search_accommodations("Hvar")
        print(json.dumps(json.loads(hotels), indent=2))

    asyncio.run(_smoke())
