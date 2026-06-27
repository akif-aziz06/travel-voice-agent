"""Atlas — premium voice travel concierge (LiveKit Agent worker).

This is the production agent runner. It assembles the real-time
STT -> LLM -> TTS pipeline using the LiveKit Agents v1.x API
(AgentSession + Agent class with @function_tool).

Pipeline
--------
Deepgram STT (Nova-2) -> Anthropic Claude (or Groq Llama / local Ollama)
-> ElevenLabs TTS, orchestrated by LiveKit's ``AgentSession``.

Run (from the repository root, so the `server` package resolves)
---
    python -m server.main dev      # connect to LiveKit and wait for dispatch
    python -m server.main start    # production worker mode

Environment variables (loaded from the project-root ``.env``):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET   (required)
    DEEPGRAM_API_KEY                                   (required, STT)
    ELEVEN_API_KEY                                     (required, TTS)
    ANTHROPIC_API_KEY                                  (LLM; preferred)
    GROQ_API_KEY                                       (LLM fallback)
    OLLAMA_BASE_URL                                    (optional LLM fallback)
"""

from __future__ import annotations

import json
import logging
import os
import textwrap
from typing import Any

from dotenv import find_dotenv, load_dotenv

# Load the project-root .env before anything reads os.environ.
load_dotenv(find_dotenv(usecwd=True))

from livekit import rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import anthropic, deepgram, elevenlabs, openai

# Import the pure tool logic from tools.py
from server.tools import (
    calculate_trip_budget,
    fetch_accommodations,
    fetch_weather,
    format_visa,
    format_weather,
    get_visa_requirement,
    search_curated_destinations,
)

logger = logging.getLogger("atlas.agent")

# Data-channel topic the frontend subscribes to for rich tool-result cards.
TOOL_TOPIC = "atlas.tool"

# ---------------------------------------------------------------------------
# Atlas persona — system prompt (hardcoded per PRD §4 / arch.md §5.1)
# ---------------------------------------------------------------------------
ATLAS_INSTRUCTIONS = textwrap.dedent("""\
    You are Atlas, a premium AI travel concierge. Your personality is warm,
    confident, and decisive — like a trusted friend who happens to have
    encyclopedic knowledge of global travel.

    RULES YOU MUST FOLLOW WITHOUT EXCEPTION:
    1. Keep ALL responses to a maximum of 3 sentences. Never exceed this.
    2. Never use bullet points, numbered lists, or markdown formatting.
       Your output is spoken aloud — write for the ear, not the eye.
    3. Ask a maximum of 2 clarifying questions across the entire session
       before invoking search_curated_destinations. Do not over-qualify.
    4. When you have the user's budget tier and travel vibe, immediately
       call search_curated_destinations — do not ask more questions.
    5. Present the tool result as your own confident recommendation.
       Never say "the tool returned" or expose internal mechanics.
    6. Never invent flight numbers, real hotel booking URLs, or actual
       availability. All recommendations come from your tool calls.
    7. End every recommendation with an implicit next-step question,
       such as "Want me to calculate the full trip cost for you?"
    8. NEVER speak or write tool names, function-call syntax, XML tags, or JSON.
       To use a tool, invoke it through the function interface — your spoken
       words must always be natural, human conversation and nothing else.

    EXTRA CAPABILITIES — when the user asks about any of these, you MUST call the
    matching tool and answer ONLY from its result; never answer from your own
    knowledge, even when the answer seems obvious:
    - check_weather: ALWAYS call for any weather, climate, or what-to-pack question.
    - check_visa_requirements: ALWAYS call for any visa or entry question,
      including domestic trips where the origin and destination country are the
      same.
    - search_accommodations: ALWAYS call for any hotel or where-to-stay question.
    After giving a recommendation you may proactively offer one (for example,
    "Want me to check the weather or visa rules?") — never recite them as a list.

    BUDGET TIERS: "budget" (< $1,000/person), "mid" ($1,000-$3,000),
                  "luxury" (> $3,000)
    VIBE OPTIONS: "beach", "culture", "adventure", "city", "wellness"

    BEGIN: Greet the user warmly and ask where their next adventure is
    taking them. Keep it to one sentence.
""")


# ---------------------------------------------------------------------------
# LLM backend selection — Anthropic (preferred), then Groq, then Ollama
# ---------------------------------------------------------------------------
# Claude model for the voice pipeline. Haiku 4.5 is the fastest + cheapest
# Claude tier ($1/$5 per 1M tokens) — the right tradeoff for real-time voice
# where per-turn latency is spoken aloud. Swap to "claude-sonnet-4-6" or
# "claude-opus-4-8" if you want more capability at higher latency/cost.
ANTHROPIC_MODEL = "claude-haiku-4-5"


def _build_llm():
    """Return a configured LLM, preferring Anthropic Claude.

    Anthropic is pay-as-you-go (no free daily-token wall like Groq's free tier)
    and its tool calling is native and reliable, so — unlike the Groq/Llama path
    below — it needs no ``_strict_tool_schema=False`` workaround. Groq and Ollama
    remain as fallbacks if no Anthropic key is set.
    """
    anthropic_key = os.getenv("ANTHROPIC_API_KEY", "").strip()
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip()

    if anthropic_key and not anthropic_key.startswith("sk-ant-xxx"):
        logger.info("LLM backend: Anthropic (%s).", ANTHROPIC_MODEL)
        return anthropic.LLM(model=ANTHROPIC_MODEL, api_key=anthropic_key)

    # Groq uses the OpenAI-compatible plugin (not the dedicated ``groq`` plugin) so
    # we can set ``_strict_tool_schema=False``. Groq's Llama models do NOT support
    # OpenAI strict-mode tool schemas: with strict enabled the model intermittently
    # returns tool calls as literal ``<function=...>{...}</function>`` TEXT instead
    # of structured tool_calls — which then gets spoken by TTS and silently breaks
    # function calling (no tool cards). Disabling strict makes tool calls reliable.
    if groq_key and not groq_key.startswith("gsk_xxx"):
        logger.info("LLM backend: Groq (llama-3.3-70b-versatile), strict tools disabled.")
        return openai.LLM(
            model="llama-3.3-70b-versatile",
            base_url="https://api.groq.com/openai/v1",
            api_key=groq_key,
            _strict_tool_schema=False,
        )

    if ollama_base:
        logger.info("LLM backend: local Ollama at %s (llama3).", ollama_base)
        base_url = ollama_base.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return openai.LLM(model="llama3", base_url=base_url, _strict_tool_schema=False)

    raise RuntimeError(
        "No LLM backend configured. Set ANTHROPIC_API_KEY (preferred), "
        "GROQ_API_KEY, or OLLAMA_BASE_URL in .env."
    )


# ---------------------------------------------------------------------------
# Atlas Agent class (v1.x API with @function_tool)
# ---------------------------------------------------------------------------
class AtlasAgent(Agent):
    """Atlas voice travel concierge agent with function-calling tools."""

    def __init__(self) -> None:
        super().__init__(
            llm=_build_llm(),
            instructions=ATLAS_INSTRUCTIONS,
        )
        # Bound after the room connects so tools can stream rich UI cards.
        self._room: rtc.Room | None = None

    def bind_room(self, room: rtc.Room) -> None:
        """Attach the connected room so tool calls can publish UI cards."""
        self._room = room

    async def _publish_card(self, tool: str, data: dict[str, Any]) -> None:
        """Stream a structured tool result to the frontend over the data channel.

        Best-effort: a publish failure must never break the voice pipeline.
        """
        room = self._room
        if room is None:
            logger.debug("No room bound; skipping '%s' card publish.", tool)
            return
        try:
            payload = json.dumps({"type": "tool_result", "tool": tool, "data": data})
            await room.local_participant.publish_data(
                payload, topic=TOOL_TOPIC, reliable=True
            )
        except Exception:
            logger.exception("Failed to publish '%s' tool card.", tool)

    @function_tool()
    async def search_curated_destinations(
        self,
        context: RunContext,
        budget: str,
        vibe: str,
    ) -> str:
        """Search for a single curated flight and hotel bundle matching the
        traveler's budget tier and travel vibe. Call this as soon as both
        the budget and the vibe are known.

        Args:
            budget: Budget tier: 'budget', 'mid', or 'luxury'.
            vibe: Travel vibe: 'beach', 'culture', 'adventure', 'city', or 'wellness'.
        """
        logger.info("Tool called: search_curated_destinations(budget=%s, vibe=%s)", budget, vibe)
        result = await search_curated_destinations(budget=budget, vibe=vibe)
        try:
            await self._publish_card("destination", json.loads(result))
        except json.JSONDecodeError:
            logger.warning("Could not parse destination result for card publish.")
        return result

    @function_tool()
    async def calculate_trip_budget(
        self,
        context: RunContext,
        destination: str,
        days: int,
        travelers: int,
    ) -> str:
        """Calculate an estimated total trip budget in USD from a destination,
        the number of days, and the number of travelers. Call this when the
        user asks how much a trip will cost.

        Args:
            destination: Destination city/country, e.g. 'Hvar, Croatia'.
            days: Number of trip days (whole number).
            travelers: Number of travelers in the party.
        """
        logger.info("Tool called: calculate_trip_budget(dest=%s, days=%s, travelers=%s)", destination, days, travelers)
        result = await calculate_trip_budget(
            destination=destination, days=days, travelers=travelers
        )
        try:
            await self._publish_card("budget", json.loads(result))
        except json.JSONDecodeError:
            logger.warning("Could not parse budget result for card publish.")
        return result

    @function_tool()
    async def check_weather(
        self,
        context: RunContext,
        latitude: float,
        longitude: float,
    ) -> str:
        """Check the current weather at a destination using its coordinates.
        Call this when the user asks about weather, climate, or what to pack.

        Args:
            latitude: Destination latitude in decimal degrees (e.g. 43.17).
            longitude: Destination longitude in decimal degrees (e.g. 16.44).
        """
        logger.info("Tool called: check_weather(lat=%s, lon=%s)", latitude, longitude)
        data = await fetch_weather(latitude, longitude)
        await self._publish_card("weather", data)
        return format_weather(data)

    @function_tool()
    async def check_visa_requirements(
        self,
        context: RunContext,
        origin_country: str,
        destination_country: str,
    ) -> str:
        """Check tourist visa requirements between two countries. Call this when
        the user asks whether they need a visa to visit somewhere.

        Args:
            origin_country: The traveler's passport country, e.g. 'Pakistan'.
            destination_country: The country they want to visit, e.g. 'Croatia'.
        """
        logger.info(
            "Tool called: check_visa_requirements(%s -> %s)",
            origin_country,
            destination_country,
        )
        data = get_visa_requirement(origin_country, destination_country)
        await self._publish_card("visa", data)
        return format_visa(data)

    @function_tool()
    async def search_accommodations(
        self,
        context: RunContext,
        city: str,
        check_in_date: str | None = None,
        nights: int = 2,
        adults: int = 2,
    ) -> str:
        """Find the top hotels in a city via Booking.com. Call this when the user
        asks about where to stay, hotels, or accommodation.

        Args:
            city: Destination city name, e.g. 'Barcelona' or 'Hvar'.
            check_in_date: Optional check-in date as 'YYYY-MM-DD'. Defaults to
                about a month out if the user doesn't specify one.
            nights: Number of nights to stay (default 2).
            adults: Number of adult guests (default 2).
        """
        logger.info(
            "Tool called: search_accommodations(city=%s, check_in=%s, nights=%s, adults=%s)",
            city,
            check_in_date,
            nights,
            adults,
        )
        data = await fetch_accommodations(
            city, check_in_date=check_in_date, nights=nights, adults=adults
        )
        await self._publish_card("hotels", data)
        return json.dumps(data)


# ---------------------------------------------------------------------------
# Worker entrypoint
# ---------------------------------------------------------------------------
async def entrypoint(ctx: JobContext) -> None:
    """Handle a dispatched LiveKit job: connect, assemble Atlas, and greet."""
    logger.info("Atlas worker received job for room %s.", ctx.room.name)

    agent = AtlasAgent()
    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        tts=elevenlabs.TTS(),
    )

    await session.start(
        agent=agent,
        room=ctx.room,
    )

    # Connect to the room, then bind it so tool calls can stream UI cards.
    await ctx.connect()
    agent.bind_room(ctx.room)

    # Atlas speaks first — autoplayed greeting (PRD §6.1).
    await session.generate_reply(
        instructions="Greet the user warmly and ask where their next adventure is taking them. Keep it to one sentence."
    )

    logger.info("Atlas is live in room %s.", ctx.room.name)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
        )
    )
