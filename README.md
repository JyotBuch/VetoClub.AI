# 🍽️ LetsPlanIt

> A conversation-context-aware group outing planner, living inside your iMessage group chat.

LetsPlanIt is an AI agent that **silently listens** to your group chat, builds up context about everyone's preferences, and springs into action the moment someone tags `@Agent`. It handles the full loop — finding places, checking dietary needs, estimating Uber costs, tracking who's confirmed, and making the reservation.

---

## ✨ How It Works

```
Group Chat                          LetsPlanIt Agent
──────────                          ───────────────
Jyot:  "Guys we should do something tonight!"
Nidhi: "I don't mind Indian food actually!"
Johi:  "Yeah Indian works for me too!"          → [silent extraction: cuisine=indian]
Alisha:"Actually can we do Italian?             → [silent extraction: Alisha dislikes indian,
        I just had Indian food :("                 prefers italian]
Nidhi: "I'm good with Italian"                  → [silent extraction: Nidhi confirms italian]
Johi:  "Yeah let's do it tonight at 8!"         → [silent extraction: time=8pm, date=today]
Nidhi: "find Italian places in Chicago
        with a chill dinner vibe @Agent"         ──→ AGENT ACTIVATES
                                                     ↓ Yelp search
                                                     ↓ Maps distance filter (<30 min)
                                                     → Shows suggestions
Alisha:"Actually I'm vegetarian today,
        can you make sure they serve veg? @Agent" ──→ Updates preferences
                                                      ↓ Re-runs Yelp with veg filter
                                                      → Updated suggestions
Jyot:  "La Italiano works for me"
Alisha:"Yeah I'm good with that option too"
Jyot:  "Confirm that option for us @Agent"       ──→ CONFIRMATION CHECK
                                                      → "Waiting to hear from Johi & Nidhi"
Nidhi: "Works for me"
Johi:  "How much would an Uber cost me
        from Riverwalk? @Agent"                  ──→ Uber estimate: $28
Johi:  "Cool, make the reservation @Agent"       ──→ Reservation made
                                                      → "You guys are on for
                                                         La Italiano tonight @8! 🎉"
```

---

## 🏗️ Architecture

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

## 🗂️ Project Structure

```
letsPlanIt/
├── bridge/                         # TypeScript — Photon SDK
│   ├── src/
│   │   ├── imessage.ts             # iMessage listener
│   │   ├── gateway.ts              # HTTP relay to Python backend
│   │   └── types.ts                # Shared message types
│   ├── package.json
│   └── tsconfig.json
│
├── server/                         # Python — Core backend
│   ├── main.py                     # FastAPI entry point
│   ├── agent/
│   │   ├── orchestrator.py         # Groq agent (active mode)
│   │   ├── context.py              # Silent preference extractor
│   │   └── triggers.py             # @Agent mention detection
│   ├── state/
│   │   ├── session.py              # Group session manager
│   │   ├── preferences.py          # Per-member preference CRUD
│   │   └── models.py               # Pydantic models
│   ├── tools/
│   │   ├── mcp_server.py           # FastMCP server
│   │   ├── yelp_tool.py            # Restaurant search
│   │   ├── maps_tool.py            # Distance + travel time
│   │   ├── uber_tool.py            # Fare estimation
│   │   └── opentable_tool.py       # Reservations
│   └── db/
│       └── store.py                # SQLite via SQLModel
│
├── demo/
│   └── demo.py                     # 🎬 Full demo script (no iMessage needed)
│
├── .env.example
├── docker-compose.yml
└── README.md
```

---

## 🚀 Quick Start

### Prerequisites

| Tool | Version | Purpose |
|------|---------|---------|
| Python | 3.11+ | Backend server |
| Node.js | 20+ | TypeScript bridge |
| Redis | 7+ | Session state |
| BlueBubbles | Latest | iMessage relay (requires a Mac) |

### 1. Clone & Install

```bash
git clone https://github.com/yourname/letsPlanIt
cd letsPlanIt

# Python backend
cd server
pip install -r requirements.txt

# TypeScript bridge
cd ../bridge
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
OPENTABLE_API_KEY=...

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
cd bridge && npm run dev
```

### 4. Try the Demo (no iMessage needed)

```bash
pip install rich
python demo/demo.py
```

---

## 🎬 Demo Script

> `demo/demo.py` simulates the full Chicago dinner planning scenario end-to-end in your terminal.
> No iMessage, no BlueBubbles, no real API keys required — all external calls are mocked.

```python
#!/usr/bin/env python3
"""
LetsPlanIt — Full Demo Script
Simulates the group chat scenario from the product spec.
Mocks Yelp, Maps, Uber, and OpenTable so no real API keys are needed.
Run: python demo.py
"""

import asyncio
import time
from rich.console import Console
from rich.panel import Panel

console = Console()

# ─── Mock API Responses ───────────────────────────────────────────────────────

MOCK_RESTAURANTS = [
    {
        "name": "La Italiano",
        "address": "742 W Fullerton Ave, Chicago",
        "distance_mins": 18,
        "rating": 4.6,
        "vibe": "Cozy, chill dinner atmosphere",
        "has_vegetarian": True,
        "price": "$$",
    },
    {
        "name": "Piccolo Sogno",
        "address": "464 N Halsted St, Chicago",
        "distance_mins": 24,
        "rating": 4.4,
        "vibe": "Romantic, upscale Italian",
        "has_vegetarian": True,
        "price": "$$$",
    },
    {
        "name": "Café Spiaggia",
        "address": "980 N Michigan Ave, Chicago",
        "distance_mins": 29,
        "rating": 4.3,
        "vibe": "Casual lakeside Italian",
        "has_vegetarian": False,
        "price": "$$",
    },
]

MOCK_UBER_FARE = 28
MOCK_CONFIRMATION_CODE = "LPI-8842"

# ─── Group State ──────────────────────────────────────────────────────────────

class GroupSession:
    def __init__(self):
        self.members = {
            "Jyot":  {"dietary": [], "cuisine_likes": [], "cuisine_dislikes": [], "confirmed": False},
            "Nidhi": {"dietary": [], "cuisine_likes": [], "cuisine_dislikes": [], "confirmed": False},
            "Johi":  {"dietary": [], "cuisine_likes": [], "cuisine_dislikes": [], "confirmed": False},
            "Alisha":{"dietary": [], "cuisine_likes": [], "cuisine_dislikes": [], "confirmed": False},
        }
        self.state = "idle"
        self.cuisine = None
        self.time = None
        self.results = []
        self.selected = None
        self.dietary_filters = []

session = GroupSession()

# ─── Display Helpers ──────────────────────────────────────────────────────────

COLORS = {
    "Jyot":  "bold red",
    "Nidhi": "bold magenta",
    "Johi":  "bold blue",
    "Alisha":"bold green",
    "Agent": "bold white",
}

def chat_msg(sender: str, text: str, delay: float = 0.9):
    time.sleep(delay)
    color = COLORS.get(sender, "white")
    if sender == "Agent":
        console.print(Panel(f"🤖  {text}", border_style="dark_orange3", title="[bold dark_orange3]Agent[/]"))
    else:
        console.print(f"  [{color}]{sender}:[/]  {text}")

def agent_thinking(task: str):
    time.sleep(0.3)
    console.print(f"  [dim italic]  ↳ {task}[/dim italic]")
    time.sleep(0.5)

def show_restaurants(restaurants: list, filters: list = []):
    filter_str = "  ·  ".join(filters) if filters else "no filters"
    console.print(f"\n  [bold yellow]📍 Suggestions[/bold yellow]  [dim]{filter_str}[/dim]")
    for r in restaurants:
        veg = "  [green]🥗 veg[/green]" if r["has_vegetarian"] else ""
        console.print(
            f"    [cyan]{r['name']}[/cyan]  ⭐ {r['rating']}  "
            f"🕐 {r['distance_mins']} min  {r['price']}{veg}"
        )
        console.print(f"    [dim]{r['address']} — {r['vibe']}[/dim]")
    console.print()

# ─── Demo Scenes ──────────────────────────────────────────────────────────────

async def run_demo():
    console.print()
    console.print(Panel(
        "[bold]🍽️  LetsPlanIt — Live Demo[/bold]\n"
        "[dim]Chicago dinner planning  ·  4 friends  ·  iMessage group[/dim]",
        border_style="bright_blue", padding=(1, 4)
    ))
    console.print()
    time.sleep(1)

    # ── Scene 1: The plan begins ───────────────────────────────────────────
    console.print("[bold dim]── Scene 1: The plan begins ──[/bold dim]\n")

    chat_msg("Jyot",  "Guys! We should do something tonight!")
    chat_msg("Nidhi", "I don't mind Indian food actually!")
    agent_thinking("Silent extraction → Nidhi: cuisine_likes=[indian]")
    session.members["Nidhi"]["cuisine_likes"].append("indian")

    chat_msg("Johi",  "Yeah Indian works for me too!")
    agent_thinking("Silent extraction → Johi: cuisine_likes=[indian]")
    session.members["Johi"]["cuisine_likes"].append("indian")

    chat_msg("Alisha","Actually, can we do Italian? I just had Indian food 😅")
    agent_thinking("Silent extraction → Alisha: cuisine_dislikes=[indian], likes=[italian]")
    session.members["Alisha"]["cuisine_dislikes"].append("indian")
    session.members["Alisha"]["cuisine_likes"].append("italian")

    chat_msg("Nidhi", "I'm good with Italian, haven't had that in a while")
    agent_thinking("Silent extraction → Nidhi: updated to likes=[italian]")
    session.members["Nidhi"]["cuisine_likes"] = ["italian"]

    chat_msg("Johi",  "Yeah let's do it tonight at 8!")
    agent_thinking("Silent extraction → time=8pm  ·  group consensus: italian")
    session.time = "8:00 PM"
    session.cuisine = "italian"

    # ── Scene 2: @Agent activated ──────────────────────────────────────────
    console.print("\n[bold dim]── Scene 2: @Agent activated ──[/bold dim]\n")

    chat_msg("Nidhi", "find Italian places in Chicago with a chill dinner vibe @Agent", delay=1.0)
    agent_thinking("@Agent detected → switching to ACTIVE MODE")
    agent_thinking("Calling Yelp: Italian · Chicago · <30 min from Devon St · chill dinner")
    session.state = "searching"

    results = [r for r in MOCK_RESTAURANTS if r["distance_mins"] <= 30]
    session.results = results

    chat_msg("Agent", "Looking for a restaurant for you guys!")
    show_restaurants(results, filters=["<30 min", "Italian", "chill dinner"])

    # ── Scene 3: Dietary update ────────────────────────────────────────────
    console.print("[bold dim]── Scene 3: Preference update mid-conversation ──[/bold dim]\n")

    chat_msg("Alisha","Actually I'm vegetarian today, can you make sure they serve veg food? @Agent")
    agent_thinking("Silent extraction → Alisha: dietary=[vegetarian]")
    session.members["Alisha"]["dietary"].append("vegetarian")
    session.dietary_filters.append("vegetarian")

    agent_thinking("Re-filtering results: must have vegetarian options")
    veg_results = [r for r in results if r["has_vegetarian"]]
    session.results = veg_results

    chat_msg("Agent", "Let me send restaurants with the updated preferences")
    show_restaurants(veg_results, filters=["<30 min", "Italian", "chill dinner", "has veg ✓"])

    # ── Scene 4: Building consensus ───────────────────────────────────────
    console.print("[bold dim]── Scene 4: Consensus building ──[/bold dim]\n")

    session.selected = veg_results[0]  # La Italiano

    chat_msg("Jyot",  '"La Italiano" works for me')
    agent_thinking("Silent extraction → Jyot: confirmed=True")
    session.members["Jyot"]["confirmed"] = True

    chat_msg("Alisha","Yeah I'm good with that option too")
    agent_thinking("Silent extraction → Alisha: confirmed=True")
    session.members["Alisha"]["confirmed"] = True

    chat_msg("Jyot",  "Confirm that option for us @Agent")
    agent_thinking("Checking confirmations: Jyot ✓  Alisha ✓  Johi ✗  Nidhi ✗")
    chat_msg("Agent", "Just waiting to hear from Johi & Nidhi 👀")

    chat_msg("Nidhi", "Works for me!")
    agent_thinking("Silent extraction → Nidhi: confirmed=True")
    session.members["Nidhi"]["confirmed"] = True

    # ── Scene 5: Uber check ────────────────────────────────────────────────
    console.print("\n[bold dim]── Scene 5: Uber estimate ──[/bold dim]\n")

    chat_msg("Johi",  "How much would an Uber cost me from Riverwalk? @Agent")
    agent_thinking("Calling Uber API: Riverwalk → La Italiano")
    time.sleep(0.6)
    chat_msg("Agent", f"For the current choice, your Uber would cost you ${MOCK_UBER_FARE} 🚗")

    chat_msg("Johi",  "Cool, make the reservation @Agent")
    agent_thinking("Silent extraction → Johi: confirmed=True")
    session.members["Johi"]["confirmed"] = True
    agent_thinking("All 4 members confirmed ✓ → calling OpenTable")
    time.sleep(0.8)

    # ── Scene 6: Booked! ──────────────────────────────────────────────────
    console.print("\n[bold dim]── Scene 6: Booked 🎉 ──[/bold dim]\n")

    chat_msg(
        "Agent",
        f"You guys are on for [bold]La Italiano[/bold] tonight @8! 🎉\n"
        f"  📍 742 W Fullerton Ave, Chicago\n"
        f"  👥 Party of 4  ·  Confirmation: {MOCK_CONFIRMATION_CODE}\n"
        f"  🥗 Vegetarian options available for Alisha",
        delay=0.5
    )

    # ── Final state printout ───────────────────────────────────────────────
    console.print()
    confirmed = [n for n, p in session.members.items() if p["confirmed"]]
    console.print(Panel(
        "[bold green]✅ Demo Complete[/bold green]\n\n"
        "[dim]Final group state:[/dim]\n"
        + "\n".join([
            f"  [cyan]{name}[/cyan]  confirmed={'[green]✓[/green]' if p['confirmed'] else '[red]✗[/red]'}  "
            f"dietary={p['dietary'] or '-'}  likes={p['cuisine_likes'] or '-'}"
            for name, p in session.members.items()
        ]) +
        f"\n\n[dim]Venue:[/dim] [bold]{session.selected['name']}[/bold]  "
        f"[dim]Time:[/dim] [bold]{session.time}[/bold]  "
        f"[dim]Code:[/dim] [bold]{MOCK_CONFIRMATION_CODE}[/bold]",
        border_style="green", padding=(1, 2)
    ))

if __name__ == "__main__":
    asyncio.run(run_demo())
```

---

## 🧠 State Machine

```
idle
 └─► gathering          ← first "we should do X" message
      └─► searching     ← @Agent invoked with a task
           └─► awaiting_confirmation   ← results shown to group
                └─► booking           ← all members confirmed
                     └─► booked ──────────────────────► idle
```

The agent **never books** until every member in `pending_confirmations` has explicitly agreed. If someone hasn't responded, the agent surfaces it — *"still waiting to hear from Johi & Nidhi"* — and holds.

---

## 🔧 Agent Modes

### Silent Mode *(always on)*
Every incoming message is passed through `llama-3.1-8b-instant` for lightweight structured extraction. No response is sent. The session state is updated quietly in the background.

Extracts:
- Dietary preferences (`vegetarian`, `halal`, `vegan`, ...)
- Cuisine likes / dislikes
- Location anchors and distance hints
- Implicit confirmations and rejections
- Time preferences

### Active Mode *(triggered by `@Agent`)*
Full `llama-3.3-70b-versatile` reasoning with MCP tool access, using all silently-gathered context.

Handles:
- Yelp search with accumulated preference filters
- Google Maps distance validation
- Uber fare estimates per member
- OpenTable reservation with full party size
- Consensus checking and confirmation gating

---

## 🛠️ MCP Tools

| Tool | API | What it does |
|------|-----|-------------|
| `search_restaurants` | Yelp Fusion | Search with cuisine, vibe, distance, dietary filters |
| `check_travel_time` | Google Maps | Validate <N min radius from anchor location |
| `get_uber_estimate` | Uber API | Fare estimate from any member's pickup point |
| `make_reservation` | OpenTable | Book for party size + requested time |

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

**TypeScript** (`bridge/package.json`)
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

## 📱 iMessage Setup (Photon SDK)

The watcher is a separate service (lives in `imessage_watcher/`) that:
- Listens to your iMessage group via Photon SDK
- Forwards every inbound message to FastAPI `POST /webhook`
- Exposes `POST /imessage/send` for the backend to send replies back

**1. Start the watcher (Mac only)**
```bash
cd imessage_watcher
npm install
npm run start
```

**2. Point FastAPI at the watcher**
```env
# .env
PHOTON_WATCHER_URL=http://localhost:3000   # where /imessage/send lives
WEBHOOK_SECRET=your_secret
```

**3. Verify the bridge**

Send any message in the group — you should get `[ECHO] I received: ...` back within seconds.
Once that's working, the agent layer drops straight in on top of `/webhook`.

### Message Flow
```python
# FastAPI receives from watcher
@app.post("/webhook")
async def webhook(payload: MessagePayload):
    if payload.is_self:          # filter echo messages
        return
    response = await agent.process(payload)
    if response:
        await photon_client.send(payload.group_id, response)
```

The agent's `process()` runs silent extraction on every message,
and only returns a reply string when `@Agent` is mentioned.


---

## 🗺️ Roadmap

- [ ] Core agent + silent extraction pipeline
- [ ] Yelp + Maps MCP tools
- [ ] Uber fare estimation
- [ ] OpenTable reservation
- [ ] BlueBubbles / Photon bridge
- [ ] Redis session persistence + SQLite preference store
- [ ] Multi-group support
- [ ] Web dashboard for viewing group preference history
- [ ] Flight + hotel fetching *(slope feature)*
- [ ] Google Scraper / web automation for venues without APIs

---

## 📄 License

MIT