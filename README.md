# 🍽️ LetsPlanIt

> A conversation-context-aware group outing planner that lives inside your iMessage group chat.

LetsPlanIt is an AI concierge that **silently listens** to your group’s vibe, remembers every preference, and springs into action the moment someone tags `@Agent`. It handles the whole loop — search, dietary checks, Uber estimates, consensus tracking, and the final reservation — while sounding like a reliable friend in the chat.

| Status | Stack | Channels |
|--------|-------|----------|
| 🚧 Active Build | Python · FastAPI · Groq | iMessage (Photon SDK) |

<details>
<summary><strong>Table of Contents</strong></summary>

- [🧭 Overview](#-overview)
- [💡 Why You'll Love It](#-why-youll-love-it)
- [🧰 Feature Highlights](#-feature-highlights)
- [🗂️ Repository Tour](#️-repository-tour)
- [⚙️ Architecture](#️-architecture)
- [💬 Conversation Flow](#-conversation-flow)
- [🚀 Getting Started](#-getting-started)
- [🎬 Demo Mode](#-demo-mode)
- [🔧 Tooling & Integrations](#-tooling--integrations)
- [🧠 State Machine](#-state-machine)
- [📱 iMessage Bridge](#-imessage-bridge)
- [🗺️ Roadmap](#️-roadmap)
- [🤝 Contributing](#-contributing)
- [📄 License](#-license)

</details>

---

## 🧭 Overview

LetsPlanIt joins your existing chat like any other friend. Every message (even without `@Agent`) is silently parsed for cues — cuisines, dietary needs, locations, confirmations, budgets. When someone finally says “`find Italian places @Agent`”, the agent already knows the group preferences and responds instantly with curated options.

## 💡 Why You'll Love It

- **Hands-off planning** — the group keeps chatting casually; the agent handles structure.
- **Memory that sticks** — dietary needs, favorite cuisines, and location tolerances accumulate over time.
- **Tool-aware reasoning** — Yelp for candidates, Google Maps for distance checks, Uber estimates, OpenTable booking.
- **Conversation aware** — references to “option 2” or “that first place” map back to real venues.
- **Safe automations** — bookings only happen when everyone explicitly confirms.

## 🧰 Feature Highlights

- 🕵️ Silent extraction with `llama-3.1-8b-instant` (preferences, confirmations, timing).
- 🤖 Active orchestration with `llama-3.3-70b-versatile` + Groq tool calls.
- 🗺️ Multi-anchor distance validation & Uber fare estimation powered by Google Maps.
- 🥗 Dietary-aware Yelp search that respects vegetarian/vegan/halal filters.
- 📅 Google Calendar MCP integration (coming online) for reservation sharing.
- 🧠 Robust session memory (Redis + Pydantic models) across multiple group chats.

---

## 🗂️ Repository Tour

```
letsPlanIt/
├── imessage_watcher/            # TypeScript bridge (Photon SDK)
│   ├── src/
│   │   ├── imessage.ts          # Watches your Mac’s Messages DB
│   │   ├── gateway.ts           # Relays inbound/outbound HTTP payloads
│   │   └── types.ts             # Shared message contracts
│   └── package.json             # Node runtime config
│
├── server/                      # Python backend
│   ├── main.py                  # FastAPI entry point + webhook
│   ├── agent/
│   │   ├── context.py           # Silent extraction pipeline
│   │   ├── orchestrator.py      # Active agent + tool loop
│   │   └── triggers.py          # @Agent detection helpers
│   ├── state/
│   │   ├── session.py           # Session registry (Redis-compatible)
│   │   ├── preferences.py       # Merge/update helpers per member
│   │   └── models.py            # Pydantic data contracts
│   ├── tools/
│   │   ├── search_coordinator.py# Yelp → Maps orchestration
│   │   ├── yelp_tool.py         # Yelp Fusion client
│   │   ├── maps_tool.py         # Geocoding + distance matrix + Uber math
│   │   └── calendar_tool.py     # Google Calendar MCP stub
│   └── demo/                    # Optional CLI demo (no iMessage required)
│
├── tests/                       # Pytest suites for every layer
├── .env.example                 # Environment template
└── README.md                    # You are here 👋
```

---

## ⚙️ Architecture

```
┌─────────────────────────────────────────────────────────┐
│               iMessage (Photon SDK Watcher (MAC))        │
│                    TypeScript Bridge                     │
└────────────────────────┬────────────────────────────────┘
                         │ HTTP POST /message
┌────────────────────────▼────────────────────────────────┐
│                  FastAPI Core Server                     │
│                                                         │
│   Message Router → Session Manager (Redis + SQLite)     │
│                         │                               │
│              Agent Orchestrator (Groq LLM)              │
│          llama-3.3-70b  ←→  llama-3.1-8b-instant        │
│           (active mode)      (silent extraction)        │
│                         │                               │
│              ┌──────────▼──────────┐                    │
│              │   FastMCP Tools      │                    │
│              │  Yelp · Maps · Uber  │                    │
│              │  OpenTable           │                    │
│              └─────────────────────┘                    │
└─────────────────────────────────────────────────────────┘
```

---

## 💬 Conversation Flow

```
Group Chat                          LetsPlanIt Agent
──────────                          ───────────────
Jyot:  "Guys we should do something tonight!"
Nidhi: "I don't mind Indian food actually!"
Johi:  "Yeah Indian works for me too!"          → [silent extraction: cuisine=indian]
Alisha:"Actually can we do Italian?             → [silent extraction: dislikes=indian,
        I just had Indian food :("                 likes=italian]
Nidhi: "I'm good with Italian"                  → [silent extraction: likes=italian]
Johi:  "Yeah let's do it tonight at 8!"         → [silent extraction: time=8pm]
Nidhi: "find Italian places in Chicago
        with a chill vibe @Agent"                ──→ ACTIVE MODE (Yelp + Maps)
Alisha:"I'm vegetarian today, pls only veg @Agent" → filters update + re-search
Jyot:  "La Italiano works for me"
Alisha:"Yeah I'm good with that option too"
Jyot:  "Confirm for us @Agent"                  ──→ needs Johi + Nidhi ✅
Nidhi: "Works for me"
Johi:  "How much is Uber from Riverwalk? @Agent"→ ride estimate $28
Johi:  "Cool, make the reservation @Agent"      ──→ reservation + calendar link 🎉
```

---

## 🚀 Getting Started

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend server |
| Node.js | 20+ | Photon SDK bridge |
| Redis | 7+ | Session persistence |
| BlueBubbles / Photon | Latest | iMessage relay (macOS) |

### 1. Clone & Install

```bash
git clone https://github.com/yourname/letsPlanIt
cd letsPlanIt

# Python backend
cd server
pip install -r requirements.txt

# TypeScript bridge
cd ../imessage_watcher
npm install
```

### 2. Configure Environment

```bash
cp .env.example .env
```

```env
# .env
GROQ_API_KEY=gsk_...
YELP_API_KEY=...
GOOGLE_MAPS_API_KEY=...
UBER_CLIENT_ID=...
UBER_CLIENT_SECRET=...

BLUEBUBBLES_URL=http://your-mac-mini:1234
BLUEBUBBLES_PASSWORD=your_password

REDIS_URL=redis://localhost:6379
```

### 3. Run

```bash
# Start Redis
docker-compose up -d redis

# Start Python backend
cd server && uvicorn main:app --reload --port 8000

# Start TypeScript bridge
cd imessage_watcher && npm run dev
```

### 4. Try the Demo (optional)

```bash
pip install rich
python server/demo/demo.py
```

---

## 🎬 Demo Mode

> `demo/demo.py` simulates the full Chicago dinner planning scenario end-to-end in your terminal. All external calls are mocked so you can watch the experience without real API keys or iMessage.

*(Script excerpt omitted here for brevity — open `server/demo/demo.py` to view the full walkthrough.)*

---

## 🔧 Tooling & Integrations

| Tool | API | Purpose |
|------|-----|---------|
| `find_venues` | Yelp + Google Maps | Combine restaurant search with constraint validation |
| `get_uber_estimate` | Google Maps data | Estimate fares based on distance + budget caps |
| `create_group_event` | Google Calendar MCP | Share booking details back with the group |

> More MCP endpoints (OpenTable, flight/hotel search) are stubbed and ready for expansion.

---

## 🧠 State Machine

```
idle
 └─► gathering          ← first "we should do X" message
      └─► searching     ← @Agent invoked with a task
           └─► awaiting_confirmation   ← results shown to group
                └─► booking           ← all members venue-confirmed
                     └─► booked ──────────────────────► idle
```

The agent **never books** until every member has `venue_confirmed=true`. If someone hasn't responded, the agent surfaces it — *"still waiting to hear from Johi & Nidhi"* — and holds.

---

## 🔧 Agent Modes

### Silent Mode *(always on)*
- Every incoming message is passed through `llama-3.1-8b-instant` for lightweight structured extraction.
- Extracts dietary preferences, cuisine likes/dislikes, locations, confirmations, time hints.
- No responses are sent; the session state updates quietly in the background.

### Active Mode *(triggered by `@Agent`)*
- Full `llama-3.3-70b-versatile` reasoning with Groq tool access.
- Handles Yelp search, Google Maps validation, Uber estimates, calendar events.
- Maintains option indices so references like "option 2" map back to saved venues.

---

## 📦 Dependencies

**Python** (`server/requirements.txt`)
```
fastapi
uvicorn
groq
fastmcp
sqlmodel
redis
pydantic
httpx
rich
```

**TypeScript** (`imessage_watcher/package.json`)
```json
{
  "dependencies": {
    "photon-sdk": "latest",
    "axios": "^1.6.0",
    "typescript": "^5.0.0"
  }
}
```

---

## 📱 iMessage Bridge

The watcher (in `imessage_watcher/`) listens to your macOS Messages DB through Photon SDK, forwards inbound messages to `POST /webhook`, and exposes `POST /imessage/send` for responses.

1. **Start the watcher (Mac only)**
   ```bash
   cd imessage_watcher
   npm install
   npm run start
   ```
2. **Point FastAPI at the watcher**
   ```env
   PHOTON_WATCHER_URL=http://localhost:3000
   PHOTON_SHARED_SECRET=your_secret
   ```
3. **Verify the loop** — send a test message; you should receive an `[ECHO]` reply within seconds. Once this echo flow works, swap in the real agent webhook.

---

## 🗺️ Roadmap

- [ ] Core agent + silent extraction pipeline
- [ ] Yelp + Maps MCP tools
- [ ] Uber fare estimation
- [ ] Google Calendar booking + share links
- [ ] BlueBubbles / Photon bridge
- [ ] Redis session persistence + SQLite preference store
- [ ] Multi-group support
- [ ] Web dashboard for viewing group preference history
- [ ] Flight + hotel fetching *(slope feature)*
- [ ] Google Scraper / web automation for venues without APIs

---

## 🤝 Contributing

Ideas, bug reports, and PRs are welcome! Please run formatting (`ruff`, `black`) and tests (`python -m pytest`) before opening a pull request.

## 📄 License

MIT
