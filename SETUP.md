# Atlas — Setup & Run Guide

Everything you need to install, configure, and run the **Atlas** voice travel
concierge locally. This covers the "database", the requirements, the API keys,
and the exact commands to start every process.

---

## 1. What "database" does Atlas use?

**There is no SQL / external database.** Atlas is fully zero-cost, so its data
layer is three local **JSON mock files** in `server/data/`. They are read (and
cached) by `server/tools.py`:

| File | Role | Used by tool |
|---|---|---|
| `server/data/destinations.json` | 15 curated flight + hotel bundles (one per budget × vibe) | `search_curated_destinations`, mock hotel fallback |
| `server/data/rates.json` | Per-diem rate table (hotel/food/activities/flight) keyed by destination, with a `__default__` row | `calculate_trip_budget` |
| `server/data/visa.json` | Origin → destination tourist-visa matrix (Pakistan / US / UK / India → 9 destinations) | `check_visa_requirements` |

> The live tools (`check_weather` via Open-Meteo, `search_accommodations` via
> Booking.com/RapidAPI) call external APIs but **always fall back to these JSON
> files / graceful messages** if the network or a key is unavailable. So the
> demo runs even with zero external keys.

To edit the data, just change the JSON — no migrations, no schema, no DB server.

---

## 2. Prerequisites

| Tool | Version | Notes |
|---|---|---|
| **Python** | 3.11 – 3.14 | A virtual environment lives at `./.venv` |
| **Node.js** | ≥ 20.x | For the Next.js 16 client |
| **npm** | ≥ 10.x | Bundled with Node |
| **Git** | any | |

Check what's installed:

```bash
python3 --version
node --version
npm --version
```

---

## 3. Requirements (Python + Node)

### Python (backend)

Dependencies are pinned in **`server/requirements.txt`** (and an identical copy
at the repo-root `requirements.txt`). The core voice stack is **LiveKit Agents
v1.x**:

```
livekit-agents[deepgram,elevenlabs,groq,silero]   # STT + LLM + TTS + VAD
livekit-api                                        # token minting
fastapi + uvicorn                                  # token endpoint
httpx                                              # weather + hotel HTTP calls
python-dotenv                                      # loads .env
```

A `.venv` is already present. To (re)create and install:

```bash
# From the repository root
python3 -m venv .venv
source .venv/bin/activate          # Windows: .venv\Scripts\activate
pip install -r server/requirements.txt
```

Verify:

```bash
python -c "import livekit.agents as a; print('livekit-agents', a.__version__)"
```

### Node (frontend)

```bash
cd client/travel-agent
npm install
cd ../..
```

This installs Next.js 16, React 19, and the LiveKit client SDK
(`@livekit/components-react`, `@livekit/components-styles`, `livekit-client`).

---

## 4. Configure environment variables

All secrets live in a single **`.env` at the repository root** (it is loaded by
both the agent and the token service via `find_dotenv`). Copy the template and
fill it in:

```bash
cp .env.example .env
```

| Variable | Required? | Where to get it |
|---|---|---|
| `LIVEKIT_URL` | ✅ | LiveKit Cloud → project → Settings (e.g. `wss://xxx.livekit.cloud`) |
| `LIVEKIT_API_KEY` | ✅ | LiveKit Cloud → API Keys |
| `LIVEKIT_API_SECRET` | ✅ | LiveKit Cloud → API Keys |
| `GROQ_API_KEY` | ✅ (or Ollama) | https://console.groq.com/keys |
| `DEEPGRAM_API_KEY` | ✅ | https://console.deepgram.com → API Keys |
| `ELEVEN_API_KEY` | ✅ | https://elevenlabs.io → Profile → API Key |
| `RAPIDAPI_KEY` | ⛳ optional | https://rapidapi.com → subscribe to **booking-com15** (free). Without it, hotels use mock data. |
| `OLLAMA_BASE_URL` | optional | e.g. `http://localhost:11434` — used only if `GROQ_API_KEY` is blank |
| `NEXT_PUBLIC_LK_TOKEN_ENDPOINT` | ✅ | Leave as `http://localhost:8000/api/token` for local dev |

> **Free-tier keys are enough.** LiveKit Cloud, Groq, Deepgram, ElevenLabs and
> RapidAPI all have free tiers. Never commit `.env` (it is gitignored).

---

## 5. Run the stack (3 terminals)

Run all commands **from the repository root** with the venv activated
(`source .venv/bin/activate`). LiveKit **Cloud** is the transport — you do *not*
need to run a local LiveKit server.

### Terminal 1 — Token service (FastAPI, port 8000)

Mints short-lived LiveKit room tokens for the browser.

```bash
uvicorn server.token_api:app --reload --port 8000
```

Check it: `curl http://localhost:8000/health` → `{"status":"ok",...}`

### Terminal 2 — Atlas agent worker

Connects to LiveKit Cloud and waits to be dispatched into rooms.
**Use the module form** (`-m`) — `python server/main.py` will fail with
`ModuleNotFoundError: No module named 'server'`.

```bash
python -m server.main dev
```

### Terminal 3 — Next.js frontend (port 3000)

```bash
cd client/travel-agent
npm run dev
```

Open **http://localhost:3000**, click **"Start talking to Atlas"**, allow the
microphone, and talk. Try: *"I want a mid-range beach trip."*

---

## 6. The Atlas tools (function calling)

| Tool | Trigger | Data source |
|---|---|---|
| `search_curated_destinations(budget, vibe)` | budget + vibe known | `destinations.json` |
| `calculate_trip_budget(destination, days, travelers)` | "how much / total cost" | `rates.json` |
| `check_weather(latitude, longitude)` | weather / climate question | Open-Meteo (free, no key) |
| `check_visa_requirements(origin_country, destination_country)` | "do I need a visa" | `visa.json` |
| `search_accommodations(city, check_in_date?, nights?, adults?)` | hotels / where to stay | Booking.com (RapidAPI) → mock fallback |

Each tool also streams a structured **UI card** to the browser over the LiveKit
data channel (topic `atlas.tool`), rendered in the right-hand panel.

---

## 7. Test the tools without voice (CLI)

With the venv active, from the repo root:

```bash
# Run all five tools end-to-end (weather is live; hotels use Booking if RAPIDAPI_KEY is set, else mock)
python -m server.tools
```

Or individually:

```bash
python -c "
import asyncio, json
from server.tools import search_curated_destinations, calculate_trip_budget, \
    check_weather, check_visa_requirements, search_accommodations
print(asyncio.run(check_visa_requirements('Pakistan', 'Croatia')))
print(asyncio.run(check_weather(43.17, 16.44)))
print(json.loads(asyncio.run(search_accommodations('Barcelona', nights=3, adults=2)))['source'])
"
```

Inspect the mock dataset:

```bash
python -c "
import json
for d in json.load(open('server/data/destinations.json')):
    print(f\"{d['budget']:7} | {d['vibe']:10} | {d['destination']}\")
"
```

---

## 8. LLM backend: Groq (default) or Ollama

- **Groq (recommended):** set `GROQ_API_KEY`. Model: `llama-3.3-70b-versatile`.
- **Ollama (offline):** leave `GROQ_API_KEY` blank, set `OLLAMA_BASE_URL=http://localhost:11434`, then:
  ```bash
  ollama serve
  ollama pull llama3
  ```

---

## 9. Troubleshooting

| Symptom | Fix |
|---|---|
| `ModuleNotFoundError: No module named 'server'` | Run the agent as `python -m server.main dev` from the **repo root**, not `python server/main.py`. |
| `Couldn't connect … port 8000` in the browser | Start Terminal 1 (`uvicorn server.token_api:app --port 8000`). |
| Agent never speaks / joins | Start Terminal 2 (`python -m server.main dev`); check `LIVEKIT_URL/KEY/SECRET`. |
| Hotels always say "Curated picks" | `RAPIDAPI_KEY` missing/invalid in `.env` → it's using the mock fallback (expected). |
| Deepgram / ElevenLabs 401 | Wrong `DEEPGRAM_API_KEY` / `ELEVEN_API_KEY`. |
| `No LLM backend configured` | Set `GROQ_API_KEY` (or `OLLAMA_BASE_URL`) in `.env`. |
| Browser mic blocked | Allow microphone for `localhost:3000` in site settings. |

---

## 10. Project layout (quick reference)

```
travel-voice-agent/
├── .env                      # your secrets (gitignored)
├── .env.example              # template
├── requirements.txt          # python deps (root copy)
├── SETUP.md                  # this file
├── server/
│   ├── main.py               # Atlas agent worker (run: python -m server.main dev)
│   ├── token_api.py          # FastAPI token endpoint (run: uvicorn server.token_api:app)
│   ├── tools.py              # 5 tools + dataset loaders (pure logic)
│   ├── requirements.txt      # python deps
│   └── data/                 # the "database": JSON mock files
│       ├── destinations.json
│       ├── rates.json
│       └── visa.json
└── client/travel-agent/      # Next.js 16 frontend
    └── app/
        ├── page.tsx          # connect screen + LiveKitRoom
        ├── components/       # AtlasRoom, Transcript, ToolCards
        └── lib/toolCards.ts  # tool-card types + decoder
```
