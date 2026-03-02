# LetsPlanIt

**An AI group-chat concierge that turns casual iMessage threads into confirmed dinner plans.**

LetsPlanIt lives inside your iMessage group chat. It listens silently to every message — picking up cuisine preferences, dietary needs, locations, budgets, and timing — so that when someone finally says `@Agent find us Italian places`, it already knows everything it needs to respond instantly with curated, constraint-checked results.

No forms. No apps. Just the chat you're already in.

---

## How It Works

LetsPlanIt runs two parallel loops on every message:

**Silent mode** — every message, even without `@Agent`, is processed by a lightweight LLM that extracts structured signals: what cuisines people want, dietary restrictions, where they're coming from, what time works, how much they want to spend on a ride. These accumulate into a shared session that updates as the conversation evolves.

**Active mode** — when someone tags `@Agent`, the full orchestration model kicks in. It reads the accumulated session state, calls the relevant tools (Yelp search → Google Maps distance validation → Uber estimate), and replies in the chat with ranked results. It tracks which members have confirmed and won't attempt a booking until everyone has explicitly agreed.

---

## Conversation Flow

```
Jyot:   lets go out for dinner tonight
Nidhi:  I want Italian
Juhi:   Italian sounds good to me             → [silent: cuisine_likes=italian]
Alisha: can we do Italian? I just had Indian  → [silent: dislikes=indian, likes=italian]
Jyot:   lets go at 8pm                        → [silent: time=8pm]
Juhi:   nothing more than 30 mins away please → [silent: location_constraint=30min]

Nidhi:  find us Italian places @Agent  ──────────────────────────────→ ACTIVE
  ← Planxiety: Here are the top spots for tonight —
     1. La Scarola · ⭐ 4.5 · $$ · 18 min from you
     2. Piccolo Sogno · ⭐ 4.4 · $$$ · 24 min
     3. Monteverde · ⭐ 4.7 · $$$ · 22 min
     ...

Jyot:   La Scarola works for me
Nidhi:  same
Alisha: I'm good with that

Jyot:   are we all good @Agent  ─────────────────────────────────────→ ACTIVE
  ← Planxiety: Almost — still waiting on Juhi ✋

Juhi:   How much is Uber from River North? @Agent ───────────────────→ ACTIVE
  ← Planxiety: ~$14–18 from River North to La Scarola (18 min, ~1.3 mi)

Juhi:   works for me
Jyot:   book it @Agent  ─────────────────────────────────────────────→ ACTIVE
  ← Planxiety: All four confirmed! Reservation request sent 🎉
```

---

## Architecture

```
┌──────────────────────────────────────────────────┐
│  iMessage group chat (macOS)                     │
│  Messages.db  →  Photon/BlueBubbles bridge       │
│  TypeScript watcher  →  HTTP POST /webhook       │
└────────────────────────┬─────────────────────────┘
                         │
┌────────────────────────▼─────────────────────────┐
│  FastAPI server                                  │
│                                                  │
│  /webhook                                        │
│    ├── Silent extraction  (llama-3.1-8b-instant) │
│    │     extracts: cuisine · dietary · location  │
│    │               timing · budget · confirmations│
│    │     updates:  in-memory GroupSession        │
│    │                                             │
│    └── Active agent  (llama-3.3-70b-versatile)  │
│          reads: full session XML + message history│
│          tools: find_venues                      │
│                 get_uber_estimate                │
│                 create_group_event               │
│                                                  │
│  Session store  (in-memory, per group_id)        │
└────────────────────────┬─────────────────────────┘
                         │
          ┌──────────────┼──────────────┐
          ▼              ▼              ▼
       Yelp Fusion   Google Maps   Groq API
       (candidates)  (geocode +    (LLM)
                      distance)
```

---

## Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend server |
| Node.js | 20+ | iMessage bridge |
| macOS | Any | iMessage access |
| BlueBubbles or Photon | Latest | iMessage relay |

### 1. Clone and install

```bash
git clone https://github.com/JyotBuch/VetoClub.AI
cd VetoClub.AI

# Python backend
pip install -r server/requirements.txt

# TypeScript bridge
cd imessage_watcher && npm install && cd ..
```

### 2. Configure environment

```bash
cp .env.example .env
```

```env
# Required
GROQ_API_KEY=gsk_...
YELP_API_KEY=...
GOOGLE_MAPS_API_KEY=...

# iMessage bridge — use whichever matches your setup
PHOTON_WATCHER_URL=http://localhost:3000
# IMESSAGE_BRIDGE_URL=http://localhost:3000
# BLUEBUBBLES_URL=http://localhost:3000

# Optional — override model IDs
THINKING_MODEL=llama-3.3-70b-versatile
SMALL_MODEL=llama-3.1-8b-instant
```

### 3. Run

```bash
# Backend
uvicorn server.main:app --reload --port 8000

# iMessage bridge (separate terminal)
cd imessage_watcher && npm run dev
```

### 4. Test without iMessage

```bash
python test.py
```

This runs a full seeded demo session (venue search → group confirmation → booking) entirely in your terminal, using real Yelp + Maps API calls.

---

## Tools

| Tool | APIs | What it does |
|------|------|--------------|
| `find_venues` | Yelp Fusion + Google Maps | Searches restaurants by cuisine and dietary filters, then validates each candidate against every member's travel-time constraint. Returns up to 5 ranked results. |
| `get_uber_estimate` | Google Maps | Geocodes a pickup address, calculates distance to the venue, and returns a fare range. Flags if the estimate exceeds the group's stated budget cap. |
| `create_group_event` | — | Stub. Wires into the booking confirmation flow; full calendar integration coming. |

---

## Session State

Every group chat gets its own `GroupSession`. State accumulates silently and is used as context on every active agent call.

| Field | Set by | Used for |
|-------|--------|---------|
| `members` | Silent extraction | Dietary, cuisine preferences, per-member confirmation |
| `cuisine` | Silent extraction (majority vote) | Yelp search query |
| `dietary_filters` | Silent extraction | Yelp attribute filters |
| `location_constraints` | Silent extraction | Per-member max travel time (Google Maps validation) |
| `time` | Silent extraction | Event time; passed to calendar tool |
| `venue_options` | `find_venues` tool | Numbered list shown to group |
| `selected_venue` | State resolver | Set when members refer to a venue by name or number |
| `state` | Orchestrator | `idle → awaiting_confirmation → booked` |

The agent **will not book** until `all_confirmed()` returns true — every member in `members` has `venue_confirmed=True`.

---

## State Flow

```
idle
 └─► (messages accumulate silently)
      └─► awaiting_confirmation   ← find_venues returns results
           └─► booked             ← all members confirmed + booking succeeds
```

---

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `GROQ_API_KEY` | Yes | Groq API key for both LLM models |
| `YELP_API_KEY` | Yes | Yelp Fusion API key |
| `GOOGLE_MAPS_API_KEY` | Yes | Google Maps Geocoding + Distance Matrix |
| `PHOTON_WATCHER_URL` | Yes* | URL of the iMessage bridge |
| `THINKING_MODEL` | No | Active agent model (default: `llama-3.3-70b-versatile`) |
| `SMALL_MODEL` | No | Extraction model (default: `llama-3.1-8b-instant`) |

*Or set `IMESSAGE_BRIDGE_URL` / `BLUEBUBBLES_URL` — all three are checked.

---

## Project Structure

```
VetoClub.AI/
├── server/
│   ├── main.py                  # FastAPI app — /webhook, /state endpoints
│   ├── config.py                # Model + env config
│   ├── agent/
│   │   ├── orchestrator.py      # Active agent, tool loop, system prompts
│   │   ├── context.py           # Silent extraction pipeline
│   │   ├── resolver.py          # Full-history state reconciliation
│   │   ├── session_utils.py     # Session → XML serialization for LLM context
│   │   └── triggers.py          # @Agent detection and stripping
│   ├── state/
│   │   ├── models.py            # GroupSession, MemberPreference, VenueOption
│   │   ├── session.py           # In-memory session store
│   │   └── preferences.py       # Member preference merge helpers
│   └── tools/
│       ├── search_coordinator.py# Yelp → Maps pipeline
│       ├── yelp_tool.py         # Yelp Fusion REST client
│       ├── maps_tool.py         # Geocode, distance matrix, fare estimation
│       └── calendar_tool.py     # Booking stub
├── imessage_watcher/            # TypeScript bridge (Photon/BlueBubbles)
├── tests/                       # Pytest — state, extraction, orchestrator, tools
├── test.py                      # End-to-end integration demo
└── .env.example
```

---

## Roadmap

- [x] Silent preference extraction
- [x] Active agent with Yelp + Maps tool loop
- [x] Multi-member location constraint validation
- [x] Uber fare estimation
- [x] Consensus tracking (won't book until all confirmed)
- [ ] Redis session persistence (survives server restarts)
- [ ] Google Calendar booking
- [ ] Web dashboard for group preference history
- [ ] OpenTable / Resy reservation API

---

## Contributing

Run tests before opening a PR:

```bash
python -m pytest tests/
```

Bug reports and ideas welcome via [GitHub Issues](https://github.com/JyotBuch/VetoClub.AI/issues).

---

## License

MIT
