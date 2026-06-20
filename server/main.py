"""Atlas — premium voice travel concierge (LiveKit Agent worker).

This is the production agent runner. It assembles the real-time
STT -> LLM -> TTS pipeline using the LiveKit Agents v1.x API
(AgentSession + Agent class with @function_tool).

Pipeline
--------
Deepgram STT (Nova-2) -> Groq Llama-3 (or local Ollama)
-> ElevenLabs TTS, orchestrated by LiveKit's ``AgentSession``.

Run
---
    python server/main.py dev      # connect to LiveKit and wait for dispatch
    python server/main.py start    # production worker mode

Environment variables (loaded from the project-root ``.env``):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET   (required)
    DEEPGRAM_API_KEY                                   (required, STT)
    ELEVEN_API_KEY                                     (required, TTS)
    GROQ_API_KEY                                       (LLM; or use Ollama)
    OLLAMA_BASE_URL                                    (optional LLM fallback)
"""

from __future__ import annotations

import json
import logging
import os
import re
import textwrap
from typing import Annotated

from dotenv import find_dotenv, load_dotenv

# Load the project-root .env before anything reads os.environ.
load_dotenv(find_dotenv(usecwd=True))

from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RunContext,
    WorkerOptions,
    cli,
    function_tool,
)
from livekit.plugins import deepgram, elevenlabs, groq

# Import the pure tool logic from tools.py
from server.tools import (
    search_curated_destinations,
    calculate_trip_budget,
)

logger = logging.getLogger("atlas.agent")

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

    BUDGET TIERS: "budget" (< $1,000/person), "mid" ($1,000-$3,000),
                  "luxury" (> $3,000)
    VIBE OPTIONS: "beach", "culture", "adventure", "city", "wellness"

    BEGIN: Greet the user warmly and ask where their next adventure is
    taking them. Keep it to one sentence.
""")


# ---------------------------------------------------------------------------
# LLM backend selection — Groq (preferred) with Ollama fallback
# ---------------------------------------------------------------------------
def _build_llm():
    """Return a configured LLM, preferring Groq and falling back to Ollama."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip()

    if groq_key and not groq_key.startswith("gsk_xxx"):
        logger.info("LLM backend: Groq (llama-3.3-70b-versatile).")
        return groq.LLM(model="llama-3.3-70b-versatile", api_key=groq_key)

    if ollama_base:
        logger.info("LLM backend: local Ollama at %s (llama3).", ollama_base)
        # For Ollama, use the openai-compatible plugin
        from livekit.plugins import openai
        base_url = ollama_base.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return openai.LLM(model="llama3", base_url=base_url)

    raise RuntimeError(
        "No LLM backend configured. Set GROQ_API_KEY or OLLAMA_BASE_URL in .env."
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
        return result


# ---------------------------------------------------------------------------
# Worker entrypoint
# ---------------------------------------------------------------------------
async def entrypoint(ctx: JobContext) -> None:
    """Handle a dispatched LiveKit job: connect, assemble Atlas, and greet."""
    logger.info("Atlas worker received job for room %s.", ctx.room.name)

    session = AgentSession(
        stt=deepgram.STT(model="nova-2", language="en"),
        tts=elevenlabs.TTS(),
    )

    await session.start(
        agent=AtlasAgent(),
        room=ctx.room,
    )

    # Connect to the room
    await ctx.connect()

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
