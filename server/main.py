"""Atlas — premium voice travel concierge (LiveKit Agent worker).

This is the production agent runner. It assembles the real-time
STT -> LLM -> TTS pipeline and binds the decoupled concierge tools from
``server.tools``.

Pipeline
--------
Silero VAD -> Deepgram STT (Nova-2) -> Groq Llama-3 (or local Ollama)
-> ElevenLabs TTS, orchestrated by LiveKit's ``VoiceAssistant``.

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

import logging
import re
from typing import AsyncIterable

from dotenv import find_dotenv, load_dotenv

# Load the project-root .env before anything reads os.environ.
load_dotenv(find_dotenv(usecwd=True))

import os

from livekit.agents import (
    AutoSubscribe,
    JobContext,
    WorkerOptions,
    cli,
    llm,
)
from livekit.agents.voice_assistant import VoiceAssistant
from livekit.plugins import deepgram, elevenlabs, openai, silero

from server.tools import AtlasFunctions

logger = logging.getLogger("atlas.agent")

# ---------------------------------------------------------------------------
# Atlas persona — system prompt (hardcoded per PRD §4 / arch.md §5.1)
# ---------------------------------------------------------------------------
ATLAS_SYSTEM_PROMPT = """\
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
"""

GREETING = (
    "Hey there, I'm Atlas, your personal travel concierge. "
    "Where's your next adventure taking you?"
)

MAX_SENTENCES = 3


# ---------------------------------------------------------------------------
# Guardrail: hard-cap spoken replies at 3 sentences (PRD §6.2 truncation)
# ---------------------------------------------------------------------------
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+")


def _truncate_to_sentences(text: str, limit: int = MAX_SENTENCES) -> str:
    """Trim a reply to at most ``limit`` sentences without cutting mid-word."""
    sentences = [s for s in _SENTENCE_SPLIT.split(text.strip()) if s]
    if len(sentences) <= limit:
        return text.strip()
    trimmed = " ".join(sentences[:limit])
    logger.info("Truncated assistant reply from %d to %d sentences.", len(sentences), limit)
    return trimmed


async def _before_tts(
    _assistant: VoiceAssistant,
    source: str | AsyncIterable[str],
) -> str | AsyncIterable[str]:
    """LiveKit ``before_tts_cb`` hook enforcing the 3-sentence cap.

    Handles both the buffered-string and streamed-token forms LiveKit may pass.
    """
    if isinstance(source, str):
        return _truncate_to_sentences(source)

    async def _buffer_then_truncate() -> AsyncIterable[str]:
        collected = "".join([chunk async for chunk in source])
        yield _truncate_to_sentences(collected)

    return _buffer_then_truncate()


# ---------------------------------------------------------------------------
# LLM backend selection — Groq (preferred) with local Ollama fallback
# ---------------------------------------------------------------------------
def _build_llm() -> llm.LLM:
    """Return a configured LLM, preferring Groq and falling back to Ollama."""
    groq_key = os.getenv("GROQ_API_KEY", "").strip()
    ollama_base = os.getenv("OLLAMA_BASE_URL", "").strip()

    if groq_key and not groq_key.startswith("gsk_xxx"):
        logger.info("LLM backend: Groq (llama3-8b-8192).")
        return openai.LLM.with_groq(model="llama3-8b-8192", api_key=groq_key)

    if ollama_base:
        logger.info("LLM backend: local Ollama at %s (llama3).", ollama_base)
        base_url = ollama_base.rstrip("/")
        if not base_url.endswith("/v1"):
            base_url = f"{base_url}/v1"
        return openai.LLM.with_ollama(model="llama3", base_url=base_url)

    raise RuntimeError(
        "No LLM backend configured. Set GROQ_API_KEY or OLLAMA_BASE_URL in .env."
    )


# ---------------------------------------------------------------------------
# Worker entrypoint
# ---------------------------------------------------------------------------
async def entrypoint(ctx: JobContext) -> None:
    """Handle a dispatched LiveKit job: connect, assemble Atlas, and greet."""
    logger.info("Atlas worker received job for room %s.", ctx.room.name)

    try:
        await ctx.connect(auto_subscribe=AutoSubscribe.AUDIO_ONLY)
    except Exception:
        logger.exception("Failed to connect to LiveKit room %s.", ctx.room.name)
        raise

    initial_ctx = llm.ChatContext().append(
        role="system",
        text=ATLAS_SYSTEM_PROMPT,
    )

    try:
        assistant = VoiceAssistant(
            vad=silero.VAD.load(),
            stt=deepgram.STT(model="nova-2", language="en"),
            llm=_build_llm(),
            tts=elevenlabs.TTS(),
            fnc_ctx=AtlasFunctions(),
            chat_ctx=initial_ctx,
            before_tts_cb=_before_tts,
        )
    except Exception:
        logger.exception("Failed to assemble the Atlas voice pipeline.")
        raise

    _register_event_hooks(assistant)

    assistant.start(ctx.room)

    # Atlas speaks first — autoplayed greeting (PRD §6.1).
    try:
        await assistant.say(GREETING, allow_interruptions=True)
    except Exception:
        logger.exception("Failed to deliver the Atlas greeting.")

    logger.info("Atlas is live in room %s.", ctx.room.name)


def _register_event_hooks(assistant: VoiceAssistant) -> None:
    """Attach async-safe observability hooks to the assistant lifecycle."""

    @assistant.on("user_speech_committed")
    def _on_user_speech(msg: llm.ChatMessage) -> None:
        logger.info("User: %s", getattr(msg, "content", msg))

    @assistant.on("agent_speech_committed")
    def _on_agent_speech(msg: llm.ChatMessage) -> None:
        logger.info("Atlas: %s", getattr(msg, "content", msg))

    @assistant.on("function_calls_collected")
    def _on_function_calls(calls: list) -> None:
        names = [getattr(c, "function_info", c) for c in calls]
        logger.info("Atlas invoking tools: %s", names)


def _prewarm(_proc) -> None:
    """Load the Silero VAD model once per worker process before jobs arrive."""
    silero.VAD.load()


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    cli.run_app(
        WorkerOptions(
            entrypoint_fnc=entrypoint,
            prewarm_fnc=_prewarm,
        )
    )
