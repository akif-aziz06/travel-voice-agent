# 🌍 Atlas — AI Travel Planning & Booking Agent

> A real-time, voice-first AI travel concierge powered by LiveKit, Groq Llama-3, Deepgram, and ElevenLabs. Atlas eliminates booking friction by delivering a single curated travel recommendation in under 2.5 seconds — no scrolling, no decision paralysis, just the perfect trip.

[![Next.js](https://img.shields.io/badge/Next.js-16.2.9-black?logo=next.js)](https://nextjs.org)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115+-green?logo=fastapi)](https://fastapi.tiangolo.com)
[![LiveKit](https://img.shields.io/badge/LiveKit-Agents_SDK-purple?logo=livekit)](https://livekit.io)
[![License](https://img.shields.io/badge/License-MIT-blue)](LICENSE)

---

## Table of Contents

- [Overview](#overview)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Project Structure](#project-structure)
- [Local Setup](#local-setup)
  - [1. Clone & Configure Environment](#1-clone--configure-environment)
  - [2. Server Setup (FastAPI + LiveKit Agent)](#2-server-setup-fastapi--livekit-agent)
  - [3. Client Setup (Next.js)](#3-client-setup-nextjs)
  - [4. Start the LiveKit Development Server](#4-start-the-livekit-development-server)
  - [5. Run the Full Stack](#5-run-the-full-stack)
- [Environment Variables Reference](#environment-variables-reference)
- [Testing Mock Tools](#testing-mock-tools)
- [LLM Backends](#llm-backends)
- [Troubleshooting](#troubleshooting)

---

## Overview

Atlas is the voice-first interface for travel planning. Instead of presenting hundreds of search results, it gathers your **budget tier** and **travel vibe** through a natural 2-turn voice conversation, then instantly returns one curated flight + hotel bundle via function calling — all spoken aloud in a premium, concise voice.

**Core pipeline:** Browser Mic → LiveKit WebRTC → Deepgram STT → Groq Llama-3 LLM → (Tool Calls) → ElevenLabs TTS → Browser Speaker

---

## Architecture

```
┌─────────────────────┐     WebRTC      ┌──────────────────────┐
│   Next.js Browser   │ ◄──────────────► │   LiveKit Cloud SFU  │
│   (localhost:3000)  │                  │   (Free Tier)        │
└─────────────────────┘                  └──────────┬───────────┘
                                                     │
                                                     │ Audio Frames
                                                     ▼
                                         ┌──────────────────────┐
                                         │  FastAPI Agent Server │
                                         │   (localhost:8000)   │
                                         │                      │
                                         │ ┌──────────────────┐ │
                                         │ │  Deepgram STT    │ │
                                         │ │  Groq Llama-3    │ │
                                         │ │  ElevenLabs TTS  │ │
                                         │ │  Tool Executor   │ │
                                         │ └──────────────────┘ │
                                         └──────────────────────┘
```

For the full architecture diagram with Mermaid, see [arch.md](./arch.md).

---

## Prerequisites

Ensure the following are installed and available in your `PATH` before proceeding:

| Tool | Version | Install |
|---|---|---|
| **Node.js** | ≥ 20.x | [nodejs.org](https://nodejs.org) |
| **npm** | ≥ 10.x | Bundled with Node.js |
| **Python** | ≥ 3.11 | [python.org](https://python.org) |
| **pip** | ≥ 24.x | Bundled with Python |
| **LiveKit CLI (`lk`)** | latest | See below |
| **Git** | any | [git-scm.com](https://git-scm.com) |
| **Ollama** *(optional)* | latest | [ollama.com](https://ollama.com) |

### Install LiveKit CLI

```bash
# macOS (Homebrew)
brew install livekit-cli

# Linux (curl)
curl -sSL https://get.livekit.io/cli | bash

# Verify installation
lk --version
```

### API Keys Required (All Free Tier)

| Service | Sign Up | Free Tier |
|---|---|---|
| **LiveKit Cloud** | [cloud.livekit.io](https://cloud.livekit.io) | Free sandbox |
| **Groq** | [console.groq.com](https://console.groq.com) | 14,400 req/day |
| **Deepgram** | [console.deepgram.com](https://console.deepgram.com) | $200 credit |
| **ElevenLabs** | [elevenlabs.io](https://elevenlabs.io) | 10,000 chars/month |

---

## Project Structure

```
travel-voice-agent/
├── .env                          # ← YOUR SECRETS (never commit this)
├── .env.example                  # Template for .env
├── README.md                     # This file
├── PRD.md                        # Product Requirements Document
├── arch.md                       # Architecture Document
│
├── client/
│   └── travel-agent/             # Next.js 16 App Router frontend
│       ├── app/
│       │   ├── layout.tsx        # Root layout
│       │   ├── page.tsx          # Main voice UI
│       │   └── globals.css       # Tailwind base styles
│       ├── package.json
│       └── next.config.ts
│
└── server/
    ├── main.py                   # FastAPI entrypoint + token endpoint
    ├── agent.py                  # LiveKit Agent worker definition
    ├── tools.py                  # Function call implementations
    └── data/
        └── destinations.json     # Mock travel bundle dataset
```

---

## Local Setup

### 1. Clone & Configure Environment

```bash
# Clone the repository
git clone <your-repo-url> travel-voice-agent
cd travel-voice-agent

# Copy the environment template
cp .env.example .env
```

Now open `.env` in your editor and fill in every value. See [Environment Variables Reference](#environment-variables-reference) below for the full list.

```bash
# Quick check — all required keys should be non-empty
grep -E "^[A-Z_]+=.+" .env | wc -l
# Should output 7 or more
```

---

### 2. Server Setup (FastAPI + LiveKit Agent)

The server uses a Python virtual environment to isolate dependencies.

```bash
# Navigate to project root (where .env lives)
cd /path/to/travel-voice-agent

# Create and activate the virtual environment
python -m venv .venv
source .venv/bin/activate        # Linux / macOS
# .venv\Scripts\activate         # Windows

# Confirm you're using the venv Python
which python
# Should print: .../travel-voice-agent/.venv/bin/python

# Install server dependencies
pip install \
  "livekit-agents[deepgram,elevenlabs,openai,silero]>=0.8" \
  fastapi \
  "uvicorn[standard]" \
  python-dotenv \
  httpx

# Verify installation
python -c "import livekit.agents; print('LiveKit agents SDK ready')"
```

> **Note on Silero VAD:** The `silero` extra installs the Voice Activity Detection model. First run will download a ~5MB ONNX model file. This is normal.

---

### 3. Client Setup (Next.js)

```bash
# Navigate to the Next.js app directory
cd client/travel-agent

# Install Node.js dependencies
npm install

# Install LiveKit React components
npm install @livekit/components-react @livekit/client

# Verify Next.js is available
npx next --version
# Should print: 16.x.x

# Return to project root
cd ../..
```

---

### 4. Start the LiveKit Development Server

The `lk` CLI provides a local development token server that proxies to LiveKit Cloud. You need your LiveKit API credentials from `.env` for this step.

```bash
# Load env variables into your shell (bash/zsh)
export $(grep -v '^#' .env | xargs)

# Start the LiveKit dev server
# This creates a local HTTPS tunnel and prints a dev server URL
lk server start \
  --api-key $LIVEKIT_API_KEY \
  --api-secret $LIVEKIT_API_SECRET \
  --dev

# Expected output:
# LiveKit development server running
# Connect URL: wss://your-project.livekit.cloud
# API Key: your_api_key
# API Secret: [hidden]
```

> **Keep this terminal open.** The LiveKit server must remain running for the duration of your development session.

---

### 5. Run the Full Stack

Open **three separate terminal windows/tabs** from the project root:

#### Terminal 1 — FastAPI Agent Server

```bash
cd /path/to/travel-voice-agent
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Start FastAPI (HTTP server for token endpoint)
uvicorn server.main:app --reload --port 8000

# Expected output:
# INFO:     Uvicorn running on http://127.0.0.1:8000
# INFO:     Application startup complete.
```

#### Terminal 2 — LiveKit Agent Worker

```bash
cd /path/to/travel-voice-agent
source .venv/bin/activate
export $(grep -v '^#' .env | xargs)

# Start the Atlas agent worker
# This connects to LiveKit Cloud and waits for room assignments
python server/agent.py dev

# Expected output:
# INFO: Starting agent worker...
# INFO: Connected to LiveKit server
# INFO: Waiting for job dispatch...
```

#### Terminal 3 — Next.js Frontend

```bash
cd /path/to/travel-voice-agent/client/travel-agent

# Start the development server
npm run dev

# Expected output:
# ▲ Next.js 16.2.9
# - Local:   http://localhost:3000
# - Ready in 1.2s
```

**Open your browser at [http://localhost:3000](http://localhost:3000)** and click the microphone button to start a session with Atlas.

---

## Environment Variables Reference

Copy `.env.example` to `.env` and populate every field:

```bash
# ─── LiveKit Configuration ──────────────────────────────────────
# Get these from: https://cloud.livekit.io → Your Project → Settings
LIVEKIT_URL=wss://your-project-name.livekit.cloud
LIVEKIT_API_KEY=APIxxxxxxxxxxxxxxxx
LIVEKIT_API_SECRET=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ─── LLM Configuration ─────────────────────────────────────────
# Get from: https://console.groq.com/keys
GROQ_API_KEY=gsk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Optional: Use local Ollama instead of Groq
# OLLAMA_BASE_URL=http://localhost:11434

# ─── Speech-to-Text ────────────────────────────────────────────
# Get from: https://console.deepgram.com → API Keys
DEEPGRAM_API_KEY=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ─── Text-to-Speech ────────────────────────────────────────────
# Get from: https://elevenlabs.io → Profile → API Key
ELEVEN_API_KEY=sk_xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# ─── Frontend Configuration ────────────────────────────────────
# URL of your FastAPI server (for token requests)
NEXT_PUBLIC_LK_TOKEN_ENDPOINT=http://localhost:8000/api/token
```

> ⚠️ **Security:** The `.env` file is listed in `.gitignore`. Never commit it. Never expose `LIVEKIT_API_SECRET` or `ELEVEN_API_KEY` to the browser.

---

## Testing Mock Tools

Both custom tools can be triggered directly via the voice interface or tested in isolation:

### Testing `search_curated_destinations` via Voice

Say any of the following to Atlas to trigger a tool call:

```
# Trigger with explicit budget + vibe:
"I want a beach vacation with a mid-range budget."
"Looking for a luxury wellness retreat."
"Adventure trip, budget-friendly, what have you got?"

# After these, Atlas will call search_curated_destinations automatically
# and return exactly one flight + hotel bundle.
```

### Testing `calculate_trip_budget` via Voice

After Atlas gives a recommendation, say:

```
"Can you calculate the full cost for 7 days and 2 people?"
"What's the total budget for this trip?"
"Give me a cost breakdown for the whole week."
```

### Testing Tools in Isolation (CLI)

With the virtual environment activated, you can run tools directly:

```bash
cd /path/to/travel-voice-agent
source .venv/bin/activate

# Test search_curated_destinations
python -c "
from server.tools import search_curated_destinations
import asyncio, json
result = asyncio.run(search_curated_destinations(budget='mid', vibe='beach'))
print(json.dumps(json.loads(result), indent=2))
"

# Test calculate_trip_budget
python -c "
from server.tools import calculate_trip_budget
import asyncio, json
result = asyncio.run(calculate_trip_budget(destination='Hvar, Croatia', days=7, travelers=2))
print(json.dumps(json.loads(result), indent=2))
"
```

### Inspecting the Mock Dataset

The raw travel bundles are stored in `server/data/destinations.json`. To add new destinations or modify existing ones:

```bash
# View all available budget/vibe combinations
python -c "
import json
with open('server/data/destinations.json') as f:
    data = json.load(f)
for d in data:
    print(f'{d[\"budget\"]:10} | {d[\"vibe\"]:12} | {d[\"destination\"]}')
"
```

---

## LLM Backends

Atlas supports two LLM backends. Switch between them via environment variables:

### Option A: Groq API (Recommended — Fast, Free Tier)

```bash
# In .env:
GROQ_API_KEY=gsk_your_key_here

# The agent uses Groq's OpenAI-compatible endpoint automatically
# Model: llama3-8b-8192 (fastest, best for voice latency)
```

### Option B: Local Ollama (Offline / No API Key)

```bash
# 1. Install and start Ollama
ollama serve

# 2. Pull the Llama-3 model (one-time, ~4.7GB)
ollama pull llama3:8b

# 3. In .env, comment out GROQ_API_KEY and set:
# GROQ_API_KEY=           ← leave blank
OLLAMA_BASE_URL=http://localhost:11434

# 4. The agent will automatically fall back to Ollama
```

> **Note:** Ollama runs locally with no internet dependency but is ~2–3x slower than Groq for LLM inference on consumer hardware (without GPU acceleration).

---

## Troubleshooting

| Symptom | Likely Cause | Fix |
|---|---|---|
| `Connection refused` on port 8000 | FastAPI not running | Start `uvicorn server.main:app --reload --port 8000` |
| `Connection refused` on port 3000 | Next.js not running | Start `npm run dev` in `client/travel-agent/` |
| Agent not responding in room | Worker not started | Run `python server/agent.py dev` |
| "No microphone access" in browser | Browser permission denied | Allow microphone in browser site settings |
| Deepgram auth error | Invalid API key | Check `DEEPGRAM_API_KEY` in `.env` |
| ElevenLabs 401 error | Invalid API key | Check `ELEVEN_API_KEY` in `.env` |
| Groq rate limit exceeded | Free tier limit hit | Switch to Ollama: set `OLLAMA_BASE_URL` |
| LiveKit room not connecting | Wrong credentials | Verify `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` |
| `ModuleNotFoundError: livekit` | venv not activated | Run `source .venv/bin/activate` |
| Silero VAD download hangs | Slow network | Wait; the model (~5MB) downloads only once |

---

## Capstone Context

This project was built as a Capstone demonstrating:

1. **Full-stack real-time AI pipelines** using production-grade SDKs
2. **Voice-first UX design** with deliberate latency optimization
3. **LLM function calling** with local mock data (zero external API dependency for tools)
4. **$0 infrastructure cost** using exclusively free-tier services
5. **Modular agent architecture** separating transport, intelligence, and tool layers

---

*Built with ❤️ for the Capstone Program · Atlas v1.0*