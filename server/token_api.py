"""FastAPI token service for the Atlas frontend bridge.

Mints short-lived LiveKit room-access JWTs so the browser client never sees the
API secret. Decoupled from the agent worker (``main.py``) on purpose: the
secret-bearing HTTP surface and the real-time worker have different lifecycles.

Run:
    uvicorn server.token_api:app --reload --port 8000
"""

from __future__ import annotations

import logging
import os
import uuid
from datetime import timedelta

from dotenv import find_dotenv, load_dotenv

load_dotenv(find_dotenv(usecwd=True))

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from livekit import api

logger = logging.getLogger("atlas.token")

# Token lifetime is intentionally short (arch.md §7.2: ~10-minute TTL).
TOKEN_TTL_SECONDS = 10 * 60

app = FastAPI(title="Atlas Token Service", version="1.0")

# The browser client (localhost:3000) calls this service cross-origin.
_ALLOWED_ORIGINS = os.getenv(
    "ATLAS_ALLOWED_ORIGINS",
    "http://localhost:3000,http://127.0.0.1:3000",
).split(",")

app.add_middleware(
    CORSMiddleware,
    allow_origins=[o.strip() for o in _ALLOWED_ORIGINS if o.strip()],
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["*"],
)


def _require_env(name: str) -> str:
    value = os.getenv(name, "").strip()
    if not value or value.startswith(("APIxxx", "wss://your-project")):
        logger.error("Missing or placeholder environment variable: %s", name)
        raise HTTPException(
            status_code=500,
            detail=f"Server misconfigured: {name} is not set.",
        )
    return value


@app.get("/health")
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "service": "atlas-token"}


@app.get("/api/token")
async def issue_token(room: str | None = None, identity: str | None = None) -> dict[str, str]:
    """Issue a LiveKit access token for a browser participant.

    Query params are optional; sensible per-session defaults are generated so
    the frontend can call this with no arguments.
    """
    api_key = _require_env("LIVEKIT_API_KEY")
    api_secret = _require_env("LIVEKIT_API_SECRET")
    livekit_url = _require_env("LIVEKIT_URL")

    room_name = room or f"atlas-{uuid.uuid4().hex[:8]}"
    user_identity = identity or f"traveler-{uuid.uuid4().hex[:6]}"

    try:
        token = (
            api.AccessToken(api_key, api_secret)
            .with_identity(user_identity)
            .with_name(user_identity)
            .with_ttl(timedelta(seconds=TOKEN_TTL_SECONDS))
            .with_grants(
                api.VideoGrants(
                    room_join=True,
                    room=room_name,
                    can_publish=True,
                    can_subscribe=True,
                )
            )
            .to_jwt()
        )
    except Exception as exc:
        logger.exception("Failed to mint LiveKit token.")
        raise HTTPException(status_code=500, detail="Token generation failed.") from exc

    logger.info("Issued token for identity=%s room=%s.", user_identity, room_name)
    return {
        "token": token,
        "serverUrl": livekit_url,
        "room": room_name,
        "identity": user_identity,
    }
