# Product Requirements Document (PRD)
## Travel Planning & Booking Agent — *Atlas*

> **Document Version:** 1.0  
> **Status:** Draft  
> **Last Updated:** 2026-06-19  
> **Owner:** Capstone Engineering Team

---

## Table of Contents

1. [Executive Summary](#1-executive-summary)
2. [Target Audience](#2-target-audience)
3. [Problem Statement](#3-problem-statement)
4. [Solution Overview — The Atlas Persona](#4-solution-overview--the-atlas-persona)
5. [Scope](#5-scope)
6. [User Flow](#6-user-flow)
7. [Functional Requirements](#7-functional-requirements)
8. [Non-Functional Requirements](#8-non-functional-requirements)
9. [Success Metrics](#9-success-metrics)
10. [Risks & Mitigations](#10-risks--mitigations)

---

## 1. Executive Summary

**Atlas** is a real-time, voice-first AI travel concierge designed to eliminate booking friction for modern travelers. Built as a Capstone project, Atlas demonstrates a full-stack, zero-cost AI pipeline: a **LiveKit WebRTC transport layer** streams audio from a **Next.js** browser client to a **FastAPI** backend, where **Deepgram STT** transcribes speech, a **Groq-hosted Llama-3 LLM** (or local Ollama) reasons over the query and invokes custom Python tools, and **ElevenLabs TTS** synthesizes a natural spoken response returned in real time.

The product's core thesis is that **speed of confident recommendation beats breadth of options**. Rather than presenting a user with 200 search results, Atlas gathers minimal context through voice interaction and returns **exactly one curated travel bundle** (flight + hotel) within seconds.

---

## 2. Target Audience

| Segment | Description | Pain Point |
|---|---|---|
| **Busy Professionals** | 25–45, high disposable income, time-poor | No patience for multi-tab research; need concierge-grade speed |
| **Spontaneous Travelers** | Any age, decision-averse, thrill-seeking | Paralyzed by options; need a decisive external voice |
| **First-Time International Travelers** | 18–30, unfamiliar with booking logistics | Overwhelmed by price differences, visa requirements, and layover math |
| **Mobile-First Users** | Commuters, hands-free users | Prefer voice interaction over typing-intensive search UIs |

**Primary Persona:** *Mia, 32, Product Manager* — books 4–6 trips per year, has 15 minutes on her lunch break to plan a weekend getaway, and would rather be told what to do than choose among 400 options.

---

## 3. Problem Statement

### 3.1 The Decision Paralysis Crisis

The modern travel booking landscape is characterized by **information overload**. Platforms like Google Flights, Expedia, and Booking.com surface hundreds of options simultaneously, relying on the user to self-filter by price, dates, layover count, hotel star ratings, neighborhood, and cancellation policy.

This creates a documented behavioral pattern:

- **~70% of online travel research sessions end without a booking** (industry estimate).
- The average user visits **3–5 different platforms** before committing, or abandoning entirely.
- Voice-first interfaces are statistically proven to **reduce cognitive load** by narrowing input channels to a single conversational stream.

### 3.2 The Missing Layer

Existing travel tools are **search engines, not advisors**. They surface data but do not synthesize it. There is no product in the zero-cost AI space that:

1. Accepts natural language voice input (not just text chat).
2. Responds in a conversational, sub-3-sentence cadence suited for voice playback.
3. Uses minimal clarifying questions (≤ 2) to infer user intent and deliver a single confident recommendation.

Atlas fills this gap as a **proof-of-concept for the AI-native travel concierge** vertical.

---

## 4. Solution Overview — The Atlas Persona

### 4.1 Agent Identity

| Attribute | Value |
|---|---|
| **Name** | Atlas |
| **Role** | Premium, decisive travel concierge |
| **Voice** | ElevenLabs — warm, confident, neutral accent |
| **Personality** | Calm authority — like a trusted friend who happens to be a travel expert |
| **Response Length** | Strictly ≤ 3 sentences per turn for natural TTS cadence |
| **Clarification Policy** | Maximum 2 targeted questions before delivering a recommendation |

### 4.2 Interaction Philosophy

Atlas operates on the principle of **radical curation over exhaustive listing**. It does not present multiple options. When sufficient context is gathered (`budget` + `vibe`), it invokes `search_curated_destinations` and returns **one definitive bundle** as if it were an expert recommendation — because for the user, it is.

### 4.3 Tool Arsenal

| Tool | Type | Trigger Condition | Output |
|---|---|---|---|
| `search_curated_destinations` | Function Call → Mock Dataset | User has stated `budget` + `vibe` | Exactly 1 flight/hotel bundle |
| `calculate_trip_budget` | Function Call → Pure Python | User asks for cost estimate | Estimated total trip cost (USD) |

### 4.4 LLM Strategy

The system prompt engineers Atlas to:
- Never ask more than 2 questions before invoking a tool.
- Never respond with bullet lists (voice-incompatible format).
- Always end a recommendation turn with an implicit call-to-action ("Shall I lock this in for you?").
- Never fabricate flight numbers or hotel room availability.

---

## 5. Scope

### 5.1 In-Scope (v1.0)

- ✅ Real-time voice input via browser microphone (WebRTC / LiveKit)
- ✅ STT using Deepgram Nova-2 model
- ✅ LLM inference via Groq API (Llama-3-8b-8192) or local Ollama fallback
- ✅ TTS response synthesis via ElevenLabs API
- ✅ Function calling: `search_curated_destinations` (mock dataset)
- ✅ Function calling: `calculate_trip_budget` (pure Python logic)
- ✅ Next.js 16 / React 19 frontend client with LiveKit browser SDK
- ✅ FastAPI backend orchestrating the LiveKit Agents pipeline
- ✅ Single-city, single-leg trip recommendations (origin → destination)
- ✅ Budget parameter: three tiers — Budget, Mid-Range, Luxury
- ✅ Vibe parameter: curated tags (e.g., Beach, Culture, Adventure, City Break, Wellness)

### 5.2 Out-of-Scope (v1.0)

- ❌ Live airline/GDS API integration (Amadeus, Skyscanner, Sabre)
- ❌ Real-time hotel inventory from OTA APIs (Expedia, Booking.com)
- ❌ Multi-city or open-jaw routing
- ❌ Payment processing or actual booking confirmation
- ❌ User accounts, authentication, or trip history persistence
- ❌ Multi-language support (English only)
- ❌ Mobile native app (iOS/Android) — web browser only
- ❌ Calendar integration or real-time availability checks
- ❌ Visa and entry requirement lookups

---

## 6. User Flow

### 6.1 Primary Interaction Flow — Voice Booking Session

```
┌─────────────────────────────────────────────────────────────┐
│                      USER OPENS APP                         │
│              (Next.js client at localhost:3000)             │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              ATLAS GREETING (TTS Autoplay)                  │
│  "Hey there, I'm Atlas — your personal travel concierge.   │
│   Where's your next adventure taking you?"                  │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              USER SPEAKS (Microphone Active)                │
│  e.g., "I want to go somewhere warm for about a week."     │
└──────────────────────────┬──────────────────────────────────┘
                           │  LiveKit WebRTC → Deepgram STT
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         ATLAS CLARIFYING QUESTION #1 (≤ 1 of 2)           │
│  "Great taste! What's your rough budget per person —        │
│   budget-friendly, mid-range, or luxury?"                   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│                    USER RESPONDS                            │
│  "Mid-range. I want a beach vibe, not too touristy."       │
└──────────────────────────┬──────────────────────────────────┘
                           │  Budget + Vibe extracted
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         ATLAS INVOKES TOOL (Internal — No User Delay)      │
│  search_curated_destinations(budget="mid", vibe="beach")   │
│  → Returns: { destination: "Hvar, Croatia",                │
│               flight: "JFK → DBV, $480 RT",                │
│               hotel: "Villa Nora Boutique, $120/night" }   │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│               ATLAS RECOMMENDATION (TTS)                   │
│  "I've got you — fly into Dubrovnik and ferry to Hvar,     │
│   Croatia: flights run about $480 round-trip and Villa     │
│   Nora will set you back $120 a night — gorgeous and       │
│   under-the-radar. Want me to run the full trip budget?"   │
└──────────────────────────┬──────────────────────────────────┘
                           │  (Optional: User asks for budget)
                           ▼
┌─────────────────────────────────────────────────────────────┐
│         ATLAS INVOKES calculate_trip_budget TOOL           │
│  calculate_trip_budget(days=7, travelers=2,                │
│                        destination="Hvar, Croatia")        │
│  → Returns: { total_estimate: "$2,340", breakdown: {...} } │
└──────────────────────────┬──────────────────────────────────┘
                           │
                           ▼
┌─────────────────────────────────────────────────────────────┐
│              SESSION ENDS / USER SATISFIED                 │
└─────────────────────────────────────────────────────────────┘
```

### 6.2 Error / Fallback Flow

| Scenario | Atlas Response |
|---|---|
| STT returns low-confidence transcript | Re-prompts once: "Sorry, I didn't quite catch that — could you repeat?" |
| No destination matches budget+vibe | Gracefully broadens: "Slightly adjusting the vibe — here's the closest match I have." |
| LLM response exceeds 3 sentences | System prompt enforcement + post-processing truncation |
| User provides only 1 clarifying input | Atlas asks at most 1 more question, then commits to a recommendation |

---

## 7. Functional Requirements

### 7.1 Voice Interface

| ID | Requirement | Priority |
|---|---|---|
| FR-01 | System shall capture microphone audio via WebRTC in-browser | P0 |
| FR-02 | System shall stream audio to LiveKit room in real time | P0 |
| FR-03 | System shall transcribe speech using Deepgram STT with < 500ms latency | P0 |
| FR-04 | System shall synthesize spoken responses using ElevenLabs TTS | P0 |
| FR-05 | System shall playback TTS audio in the browser without manual trigger | P1 |

### 7.2 Agent Intelligence

| ID | Requirement | Priority |
|---|---|---|
| FR-06 | LLM shall not ask more than 2 clarifying questions per session | P0 |
| FR-07 | LLM shall invoke `search_curated_destinations` when budget + vibe are known | P0 |
| FR-08 | LLM shall invoke `calculate_trip_budget` when user requests cost breakdown | P1 |
| FR-09 | All LLM responses shall be ≤ 3 sentences | P0 |
| FR-10 | LLM shall never produce bullet-pointed lists in responses | P0 |

### 7.3 Tool Execution

| ID | Requirement | Priority |
|---|---|---|
| FR-11 | `search_curated_destinations` shall return exactly 1 flight+hotel bundle | P0 |
| FR-12 | Mock dataset shall contain ≥ 10 destination entries across all budget/vibe combos | P1 |
| FR-13 | `calculate_trip_budget` shall accept `days`, `travelers`, `destination` as inputs | P0 |
| FR-14 | Tool execution shall complete within 200ms | P1 |

---

## 8. Non-Functional Requirements

| ID | Requirement | Target |
|---|---|---|
| NFR-01 | End-to-end voice round-trip latency | < 2.5 seconds (P95) |
| NFR-02 | STT accuracy on clear speech | > 95% WER |
| NFR-03 | System cost at scale (per session) | $0 (free tier / local models) |
| NFR-04 | Frontend first contentful paint | < 1.5s on broadband |
| NFR-05 | Backend availability | Best-effort (dev environment) |
| NFR-06 | Audio codec | Opus via WebRTC (LiveKit default) |

---

## 9. Success Metrics

### 9.1 Technical KPIs

| Metric | Target | Measurement Method |
|---|---|---|
| STT-to-LLM latency | < 300ms | Server-side timing logs |
| LLM-to-TTS latency | < 800ms | Server-side timing logs |
| Full round-trip voice latency | < 2.5s | Browser performance.now() |
| Tool invocation accuracy | 100% when intent is clear | Manual test suite |
| LLM 3-sentence compliance rate | > 95% | Output token count audit |

### 9.2 Product KPIs (Demo / Capstone Evaluation)

| Metric | Target | Notes |
|---|---|---|
| Recommendation delivered in ≤ 2 questions | 100% of test sessions | Core persona constraint |
| Evaluator "would use again" rating | ≥ 4/5 | Post-demo survey |
| Zero hallucinated flight numbers | 100% compliance | Tool-gated output policy |
| Demo session completion rate | > 90% | Sessions reaching recommendation |

---

## 10. Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|---|---|---|---|
| Groq API rate limiting during demo | Medium | High | Pre-configure Ollama local fallback |
| ElevenLabs free tier character cap | Medium | Medium | Cache common TTS responses; set character budget alerts |
| Deepgram STT noise sensitivity | Low | High | Use quality microphone; add browser noise suppression |
| LiveKit room connection failures | Low | High | Implement exponential backoff reconnection logic |
| LLM breaks 3-sentence rule | High | Low | Enforce in system prompt + add post-processing validation |
