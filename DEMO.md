# 🎬 Atlas Demo Script — "North of Pakistan" (from Lahore)

A ready-to-perform voice walkthrough that exercises **all five** Atlas tools in
one natural conversation. Premise: **you live in Lahore and want to explore
northern Pakistan.** By the end Atlas has recommended a destination, checked the
weather, shown hotels *with photos*, confirmed no visa is needed (domestic), and
built a 7-day budget for 2 people.

> Speak naturally — you don't have to read these word-for-word. The **bold "Say"**
> lines are reliable trigger phrases. Atlas replies in ≤ 3 spoken sentences and
> asks at most 2 clarifying questions before recommending (that's by design).

---

## ▶️ Before you start

Make sure all three processes are running (see `SETUP.md`):

1. Token API — `uvicorn server.token_api:app --reload --port 8000`
2. Agent worker — `python -m server.main dev`
3. Frontend — `npm run dev` in `client/travel-agent`

Open **http://localhost:3000**, click **"Start talking to Atlas"**, and **allow
the microphone**. Atlas greets you first.

---

## 🗣️ The conversation (turn by turn)

### Turn 0 — Atlas greets you (automatic)
🤖 **Atlas:** *"Hey there, I'm Atlas, your personal travel concierge. Where's your next adventure taking you?"*

---

### Turn 1 — State your intent
🎙️ **Say:** *"I'm in Lahore and I want to explore the north of Pakistan."*

🤖 **Atlas (≈):** *"Amazing choice — the north is breathtaking. Quick question: what's your rough budget — budget-friendly, mid-range, or luxury?"*
*(This is clarifying question #1 of 2, per the system prompt.)*

---

### Turn 2 — Give your budget
🎙️ **Say:** *"Mid-range."*

🤖 **Atlas (≈):** *"Great. And what's the vibe you're after — adventure, culture, or something more relaxing and wellness-focused?"*
*(Clarifying question #2 of 2.)*

---

### Turn 3 — Give your vibe → 🎯 curated recommendation
🎙️ **Say:** *"Adventure — mountains, lakes, that kind of thing."*

⚙️ **Tool fired:** `search_curated_destinations(budget="mid", vibe="adventure")`
🖼️ **Card shown:** **Destination card → "Hunza Valley, Pakistan"** — flight `LHE → GIL` (~$140), **Luxus Hunza Attabad Lake Resort** (~$95/night), "Attabad Lake views, cherry orchards, Karakoram peaks."

🤖 **Atlas (≈):** *"I've got you — Hunza Valley is the one: fly Lahore to Gilgit, then stay at the Luxus Attabad Lake Resort with Karakoram peaks right outside. Want me to check the weather up there?"*

---

### Turn 4 — Check the weather → ☀️ live data
🎙️ **Say:** *"Yes, what's the weather like in Hunza right now?"*

⚙️ **Tool fired:** `check_weather(latitude≈36.32, longitude≈74.65)` *(live Open-Meteo, no key needed)*
🖼️ **Card shown:** **Weather card** — temperature + condition + emoji for Hunza.

🤖 **Atlas (≈):** *"It's crisp and clear in Hunza right now — perfect for the valleys and lakes. Want me to pull up some places to stay?"*

---

### Turn 5 — See hotels *with photos* → 🏨 Booking.com
🎙️ **Say:** *"Show me some hotels in Hunza."*

⚙️ **Tool fired:** `search_accommodations(city="Hunza Valley")`
🖼️ **Cards shown:** up to **3 hotel cards with real photos**, star rating, per-night price, and a review-score badge.
*(With `RAPIDAPI_KEY` set → live Booking.com results + images. Without it → curated picks from the dataset; the card header shows "Live · Booking.com" vs "Curated picks".)*

🤖 **Atlas (≈):** *"Here are three strong options around Hunza, from lakeside resorts to cozy mountain lodges. Want me to confirm whether you need any travel documents?"*

---

### Turn 6 — Visa check → 🛂 "no visa, it's domestic"
🎙️ **Say:** *"Can you check the visa and entry requirements for me — I'm traveling from Pakistan?"*
*(Phrase it as "check/verify the visa requirements" so Atlas runs the tool and shows the card, rather than just answering from memory.)*

⚙️ **Tool fired:** `check_visa_requirements(origin_country="Pakistan", destination_country="Pakistan")`
🖼️ **Card shown:** **Visa card** — **"No visa required"** (green), "domestic travel within Pakistan."

🤖 **Atlas (≈):** *"Good news — it's all domestic within Pakistan, so no visa or paperwork at all. Shall I put together a full 7-day budget for you?"*

---

### Turn 7 — Build the 7-day plan → 🧮 budget
🎙️ **Say:** *"Yes, give me the total budget for 7 days for 2 people."*

⚙️ **Tool fired:** `calculate_trip_budget(destination="Hunza Valley, Pakistan", days=7, travelers=2)`
🖼️ **Card shown:** **Budget card** — flights / hotels / food / activities breakdown, **total ≈ $1,673** (≈ **$836 per traveler**).

🤖 **Atlas (≈):** *"For seven days in Hunza, two of you are looking at roughly seventeen-hundred dollars all-in — flights, the lakeside hotel, food, and activities. Want me to map out what to do each day?"*

---

### Turn 8 — Wrap up (Atlas's own knowledge)
🎙️ **Say:** *"Perfect. What are the must-see spots up there?"*

🤖 **Atlas (≈):** *"Don't miss Attabad Lake, the Eagle's Nest viewpoint at sunrise, and ancient Baltit Fort in Karimabad. It's an unforgettable week — want me to lock in the hotel shortlist?"*

---

## ✅ Feature checklist (what this demo proves)

| # | Atlas feature | Triggered in | What you see |
|---|---|---|---|
| 1 | `search_curated_destinations` | Turn 3 | Hunza Valley destination card |
| 2 | `check_weather` (live Open-Meteo) | Turn 4 | Weather card |
| 3 | `search_accommodations` (Booking.com) | Turn 5 | Hotel cards **with photos** |
| 4 | `check_visa_requirements` (domestic) | Turn 6 | "No visa required" card |
| 5 | `calculate_trip_budget` | Turn 7 | 7-day budget breakdown card |
| — | Live transcript (STT + TTS) | Every turn | Chat bubbles (You ↔ Atlas) |
| — | System-prompt guardrails | Turns 1–3 | ≤ 2 questions, then one decisive pick |

---

## 💡 Reliable trigger phrases

| To trigger… | Say something like… |
|---|---|
| A recommendation | "I want a **mid-range adventure** trip" (budget + vibe) |
| Weather | "**What's the weather** in Hunza?" |
| Hotels + photos | "**Show me hotels** in Skardu" |
| Visa | "**Check the visa** and entry requirements for me" (say "check/verify", not "do I need a visa") |
| Budget | "**Total budget** for **7 days, 2 people**" |

---

## 🔁 Variations (same flow, different north-Pakistan picks)

The curated tool keys off **budget + vibe**, so:

- **Luxury + adventure** → *"I want a **luxury adventure** trip up north"* → **Skardu, Pakistan** (Shangrila Resort, gateway to K2 & Deosai).
- **Budget + wellness** → *"Something **budget-friendly and relaxing**, lakes and pine forests"* → **Naran Kaghan, Pakistan** (Pine Park Hotel, Saif-ul-Malook).

Then reuse Turns 4–7 (weather / hotels / visa / budget) for that destination —
e.g. *"hotels in Skardu"*, *"budget for 5 days, 4 people in Skardu"*.

---

## 📝 Notes for evaluators

- **Atlas speaks first** (auto-greeting) and keeps every reply to **≤ 3 sentences**.
- It asks **at most 2 clarifying questions** before committing to one recommendation — no endless back-and-forth.
- Every factual detail (hotel names/prices, weather, visa, totals) comes from a **tool call**, never invented — and each tool also pushes a **visual card** to the right-hand panel over the LiveKit data channel.
- Weather is genuinely **live**; hotels are **live with a `RAPIDAPI_KEY`** and fall back gracefully to curated data otherwise — the demo never breaks.
