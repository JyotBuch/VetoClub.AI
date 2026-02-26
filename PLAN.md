# LetsPlanIt — Layer-wise Implementation Plan

> Build order follows the dependency graph: each layer is independently testable
> before the next begins. iMessage bridge (Photon) is already live — we start at Layer 1.

---

## Status Legend
| Symbol | Meaning |
|--------|---------|
| ✅ | Already built (Photon watcher + FastAPI scaffold) |
| 🔨 | Build this layer |
| ⏳ | Depends on prior layer |

---

## Layer 0 — Scaffold ✅
*Already done. Nothing to build here.*

- FastAPI app boots, loads `.env`, exposes `/health`
- Module stubs: `agent/`, `llm/`, `tools/`, `imessage/`, `state/`

---

## Layer 1 — iMessage Loop ✅
*Already done. Photon watcher is live.*

- Photon SDK watcher mirrors prior TS project
- Forwards inbound messages → FastAPI `/webhook`
- Exposes `/imessage/send` for outbound replies
- Self-message filtering in place
- Echo test passing: message in group → `[ECHO] I received: ...`

```
Photon SDK Watcher (Mac)
        │  POST /webhook
        ▼
   FastAPI /webhook
        │  POST /imessage/send
        ▼
Photon SDK Watcher → iMessage group
```

**Acceptance criteria (already met):**
- [ ] ✅ Send message in group → echo reply within seconds
- [ ] ✅ Self-messages are filtered and not re-processed

---

## Layer 2 — State & Preference Models 🔨
*Build the data layer before any agent logic touches it.*

### What to build

**`state/models.py`** — Pydantic models

```python
class MemberPreference(BaseModel):
    name: str
    dietary: list[str] = []           # ["vegetarian", "halal", "vegan"]
    cuisine_likes: list[str] = []
    cuisine_dislikes: list[str] = []
    location: Optional[str] = None    # "Riverwalk", "Devon St"
    confirmed: bool = False

class GroupSession(BaseModel):
    group_id: str
    members: dict[str, MemberPreference] = {}
    state: Literal[
        "idle", "gathering", "searching",
        "awaiting_confirmation", "booking", "booked"
    ] = "idle"
    event_type: Optional[str] = None
    cuisine: Optional[str] = None
    time: Optional[str] = None
    location_anchor: Optional[str] = None
    max_distance_mins: int = 30
    dietary_filters: list[str] = []
    # pending confirmations removed in later layers (derived via helper)
    selected_venue: Optional[dict] = None
    message_history: list[dict] = []   # last N messages for LLM context
    last_updated: datetime = Field(default_factory=datetime.now)
```

**`state/session.py`** — In-memory session store (Redis later)

```python
# Start with a simple dict store — swap for Redis in Layer 6
_sessions: dict[str, GroupSession] = {}

def get_or_create(group_id: str) -> GroupSession: ...
def save(session: GroupSession) -> None: ...
def get_all() -> list[GroupSession]: ...
```

**`state/preferences.py`** — Per-member CRUD helpers

```python
def upsert_member(session: GroupSession, name: str, updates: dict) -> None: ...
def get_unconfirmed(session: GroupSession) -> list[str]: ...
def all_confirmed(session: GroupSession) -> bool: ...
def merge_dietary(session: GroupSession) -> list[str]: ...
```

### Files to create
```
server/state/
  models.py
  session.py
  preferences.py
```

### Acceptance criteria
- [ ] `GroupSession` can be created, updated, and serialized to JSON
- [ ] `get_or_create` returns the same session for the same `group_id`
- [ ] `all_confirmed()` returns `False` until every member in the group has `confirmed=True`
- [ ] `merge_dietary()` returns the union of all members' dietary requirements

---

## Layer 3 — Silent Extraction (Groq, small model) 🔨
*Every message gets processed here regardless of @Agent. No replies sent.*

### What to build

**`agent/context.py`** — Lightweight preference extractor

Uses `llama-3.1-8b-instant` (fast, cheap) to pull structured data from each message
and merge it into the session.

```python
EXTRACT_PROMPT = """
Extract preferences from this group chat message. Return ONLY valid JSON, no preamble.
{
  "dietary": [],          // e.g. ["vegetarian", "halal"]
  "cuisine_likes": [],    // e.g. ["italian", "thai"]
  "cuisine_dislikes": [], // e.g. ["indian"]
  "location": null,       // any location string mentioned
  "confirmed": null,      // true if they agreed to something, false if rejected
  "time": null            // e.g. "8pm", "tonight"
}
Sender: "{sender}"
Message: "{text}"
"""

async def extract_and_merge(msg: dict, session: GroupSession) -> GroupSession:
    # 1. Call Groq llama-3.1-8b-instant with EXTRACT_PROMPT
    # 2. Parse JSON response
    # 3. Upsert into session.members[sender]
    # 4. Update session.time / session.dietary_filters if present
    # 5. Return updated session
```

**`agent/triggers.py`** — @Agent detection

```python
AGENT_TRIGGERS = ["@agent", "@Agent", "@AGENT"]

def is_agent_mentioned(text: str) -> bool:
    return any(t in text for t in AGENT_TRIGGERS)

def strip_trigger(text: str) -> str:
    # Remove @Agent from message before passing to LLM
    ...
```

**Updated `/webhook` handler in `main.py`**

```python
@app.post("/webhook")
async def webhook(payload: MessagePayload):
    if payload.is_self:
        return

    session = get_or_create(payload.group_id)
    session.message_history.append({"sender": payload.sender, "text": payload.text})

    # ALWAYS run silent extraction
    session = await extract_and_merge(payload.__dict__, session)
    save(session)

    # Only reply if @Agent is mentioned (handled in Layer 4)
    if is_agent_mentioned(payload.text):
        pass  # Layer 4 plugs in here
```

### Files to create / modify
```
server/agent/
  context.py       ← new
  triggers.py      ← new
server/main.py     ← update webhook handler
```

### Acceptance criteria
- [ ] Send "I'm vegetarian" in group → `session.members["Sender"].dietary == ["vegetarian"]`
- [ ] Send "let's do Italian" → `session.members["Sender"].cuisine_likes == ["italian"]`
- [ ] Send "works for me" → `session.members["Sender"].venue_confirmed == True`
- [ ] `@Agent` mention detected correctly, not detected in normal messages
- [ ] No reply is sent to the chat during silent extraction

---

## Layer 4 — Active Agent (Groq, large model) 🔨
*Runs only when @Agent is mentioned. Returns a reply string.*

### What to build

**`agent/orchestrator.py`** — Full reasoning agent

Uses `llama-3.3-70b-versatile` with the full session context.
At this layer, tools are stubs — the agent reasons and replies in plain text.

```python
SYSTEM_PROMPT = """
You are LetsPlanIt, a group outing planner in an iMessage group chat.

Rules:
- You only respond when @Agent is mentioned.
- You have already silently tracked preferences from the whole conversation.
- NEVER book or confirm without all members agreeing.
- If someone hasn't confirmed, name them explicitly: "still waiting on Johi".
- Be concise. This is a chat, not an email.
- When you need to search for venues or estimate fares, call the appropriate tool.

Current group state:
{state_json}

Conversation (last 20 messages):
{history}
"""

async def run_agent(text: str, session: GroupSession) -> str:
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT.format(
                state_json=session.model_dump_json(indent=2),
                history=format_history(session.message_history[-20:])
            )},
            {"role": "user", "content": strip_trigger(text)}
        ],
        tools=[],        # tools wired in Layer 5
        tool_choice="none"
    )
    return response.choices[0].message.content
```

**Updated `/webhook` handler**

```python
    if is_agent_mentioned(payload.text):
        reply = await run_agent(payload.text, session)
        await photon_client.send(payload.group_id, reply)
```

### Files to create / modify
```
server/agent/
  orchestrator.py    ← new
server/llm/
  groq_client.py     ← new (Groq client singleton)
server/main.py       ← update webhook handler
```

### Acceptance criteria
- [ ] "@Agent find us somewhere for dinner" → coherent reply using session context
- [ ] Agent names unconfirmed members instead of assuming consensus
- [ ] No reply sent for messages without `@Agent`
- [ ] Session cuisine/dietary context is reflected in the agent's reply
- [ ] `llama-3.1-8b` used for extraction, `llama-3.3-70b` used for active response

---

## Layer 5 — MCP Tools (Yelp, Maps, Uber, OpenTable) 🔨
*Wire real tool calls into the active agent.*

### What to build

**`tools/mcp_server.py`** — FastMCP tool definitions

```python
from fastmcp import FastMCP
mcp = FastMCP("LetsPlanIt")

@mcp.tool()
async def search_restaurants(
    cuisine: str,
    location_anchor: str,
    max_distance_minutes: int = 30,
    dietary_requirements: list[str] = [],
    vibe: str = "chill dinner"
) -> list[dict]:
    """Search Yelp for restaurants matching group preferences."""
    ...

@mcp.tool()
async def check_travel_time(origin: str, destination: str) -> int:
    """Returns travel time in minutes via Google Maps."""
    ...

@mcp.tool()
async def get_uber_estimate(pickup: str, destination: str) -> dict:
    """Returns Uber fare estimate and ETA."""
    ...

@mcp.tool()
async def make_reservation(
    venue_name: str,
    party_size: int,
    time: str,
    date: str,
    special_requirements: list[str] = []
) -> dict:
    """Books a reservation via OpenTable. Returns confirmation code."""
    ...
```

**`tools/yelp_tool.py`** — Yelp Fusion API wrapper  
**`tools/maps_tool.py`** — Google Maps Distance Matrix  
**`tools/uber_tool.py`** — Uber Price Estimates API  
**`tools/opentable_tool.py`** — OpenTable reservations  

**Update `orchestrator.py`** — pass tools to Groq

```python
from tools.mcp_server import mcp

async def run_agent(text: str, session: GroupSession) -> str:
    tools = mcp.get_tool_schemas()   # inject all FastMCP tools
    response = groq.chat.completions.create(
        model="llama-3.3-70b-versatile",
        messages=[...],
        tools=tools,
        tool_choice="auto"
    )
    # Handle tool_use blocks, execute tools, feed results back
    return await handle_tool_loop(response, session)
```

### Files to create / modify
```
server/tools/
  mcp_server.py       ← new
  yelp_tool.py        ← new
  maps_tool.py        ← new
  uber_tool.py        ← new
  opentable_tool.py   ← new
server/agent/
  orchestrator.py     ← update (add tool loop)
.env                  ← add YELP_API_KEY, GOOGLE_MAPS_API_KEY, UBER_*, OPENTABLE_*
```

### Acceptance criteria
- [ ] "@Agent find Italian near Devon St" → real Yelp results with distance validated by Maps
- [ ] Results filtered by merged dietary requirements automatically
- [ ] "@Agent how much is an Uber from Riverwalk?" → real fare estimate for selected venue
- [ ] "@Agent make the reservation" (all confirmed) → OpenTable booking + confirmation code
- [ ] "@Agent make the reservation" (not all confirmed) → names who hasn't confirmed, no booking

---

## Layer 6 — State Persistence (Redis + SQLite) 🔨
*Make sessions survive restarts. Preference history persists across conversations.*

### What to build

**Redis** — Active session store (TTL = 24h)

```python
# state/session.py — swap dict for Redis
import redis.asyncio as redis

async def get_or_create(group_id: str) -> GroupSession:
    raw = await r.get(f"session:{group_id}")
    if raw:
        return GroupSession.model_validate_json(raw)
    return GroupSession(group_id=group_id)

async def save(session: GroupSession) -> None:
    await r.setex(
        f"session:{group_id}",
        86400,                          # 24h TTL
        session.model_dump_json()
    )
```

**SQLite via SQLModel** — Long-term preference memory

```python
# db/store.py
class MemberRecord(SQLModel, table=True):
    id: Optional[int] = Field(default=None, primary_key=True)
    group_id: str
    name: str
    dietary: str        # JSON array
    cuisine_likes: str  # JSON array
    cuisine_dislikes: str
    updated_at: datetime

# On session save, write preferences to SQLite for cross-session memory
# On session create, load known preferences from SQLite as defaults
```

### Files to create / modify
```
server/state/
  session.py     ← update (Redis backend)
server/db/
  store.py       ← new (SQLModel + SQLite)
docker-compose.yml ← add Redis service
.env             ← add REDIS_URL
```

### Acceptance criteria
- [ ] Restart FastAPI → existing session survives (loaded from Redis)
- [ ] Second conversation in same group → Alisha's vegetarian preference pre-loaded from SQLite
- [ ] Redis TTL expires after 24h → session starts fresh for next outing
- [ ] `docker-compose up` boots Redis alongside FastAPI

---

## Layer 7 — Confirmation State Machine 🔨
*Formalize the state transitions so the agent can never book prematurely.*

### What to build

**`state/machine.py`** — Explicit state transitions

```python
TRANSITIONS = {
    "idle":                   ["gathering"],
    "gathering":              ["searching"],
    "searching":              ["awaiting_confirmation"],
    "awaiting_confirmation":  ["searching", "booking"],  # can re-search if prefs change
    "booking":                ["booked"],
    "booked":                 ["idle"],
}

def transition(session: GroupSession, to: str) -> GroupSession:
    assert to in TRANSITIONS[session.state], \
        f"Invalid transition: {session.state} → {to}"
    session.state = to
    return session

def can_book(session: GroupSession) -> bool:
    return (
        session.state == "awaiting_confirmation"
        and all_confirmed(session)
        and session.selected_venue is not None
    )
```

**Update `orchestrator.py`** — guard booking behind `can_book()`

```python
if tool_name == "make_reservation":
    if not can_book(session):
        unconfirmed = get_unconfirmed(session)
        return f"Still waiting to hear from {', '.join(unconfirmed)} before I can book."
    result = await make_reservation(...)
    transition(session, "booked")
```

### Files to create / modify
```
server/state/
  machine.py        ← new
server/agent/
  orchestrator.py   ← update (guard booking)
```

### Acceptance criteria
- [ ] Agent refuses to book if any member unconfirmed, names them explicitly
- [ ] State only advances forward (no illegal transitions)
- [ ] Mid-flow preference change (e.g. Alisha goes vegetarian) triggers re-search without losing state
- [ ] After booking, state resets to `idle` for next outing

---

## Layer 8 — Multi-group Support 🔨
*Each iMessage group gets its own isolated session.*

### What to build

- `group_id` is already the key in the session store — this is mostly validation
- Add a `GroupRegistry` to track all active groups
- Add `/admin/sessions` endpoint for debugging

```python
# GET /admin/sessions
@app.get("/admin/sessions")
async def list_sessions():
    return [s.model_dump() for s in get_all_sessions()]
```

- Rate limit: one active booking workflow per group at a time
- Handle the case where a group chat has a user in multiple groups

### Files to create / modify
```
server/state/
  session.py     ← add get_all_sessions()
server/main.py   ← add /admin/sessions route
```

### Acceptance criteria
- [ ] Two different group chats run simultaneously without state bleed
- [ ] `/admin/sessions` returns all active group sessions
- [ ] Same user in two groups has independent preference state per group

---

## Layer 9 — Hardening & Edge Cases 🔨
*Make it production-ready before shipping.*

### Checklist

**Error handling**
- [ ] Yelp returns 0 results → agent suggests broadening criteria, doesn't crash
- [ ] OpenTable unavailable → agent reports failure, offers to retry
- [ ] Groq API timeout → retry with backoff, fallback message to group
- [ ] Malformed webhook payload → log and ignore, never 500

**Rate limiting**
- [ ] Max 1 active Groq call per group at a time (queue concurrent messages)
- [ ] Yelp / Maps / Uber calls debounced (don't re-fetch if context unchanged)

**Message edge cases**
- [ ] Very long group chat history → truncate to last 20 messages for LLM context
- [ ] Non-English messages → pass through, let Groq handle gracefully
- [ ] Agent mentioned but no clear task → ask clarifying question
- [ ] Simultaneous `@Agent` mentions from two users → handle one, queue the other

**Security**
- [ ] Validate webhook signature from Photon watcher
- [ ] Never log message content to disk (privacy)
- [ ] API keys loaded from env only, never hardcoded

---

## Full Dependency Graph

```
Layer 0 (Scaffold) ✅
    └── Layer 1 (iMessage / Photon) ✅
            └── Layer 2 (State Models)
                    └── Layer 3 (Silent Extraction)
                            └── Layer 4 (Active Agent)
                                    └── Layer 5 (MCP Tools)
                                            └── Layer 6 (Persistence)
                                                    └── Layer 7 (State Machine)
                                                            └── Layer 8 (Multi-group)
                                                                    └── Layer 9 (Hardening)
```

---

## Estimated Build Order

| Layer | Effort | Unlocks |
|-------|--------|---------|
| 2 — State Models | ~2h | Foundation for all logic |
| 3 — Silent Extraction | ~3h | Preference awareness |
| 4 — Active Agent | ~3h | First real @Agent replies |
| 5 — MCP Tools | ~6h | Real venue search + booking |
| 6 — Persistence | ~3h | Survives restarts, memory across convos |
| 7 — State Machine | ~2h | Safe booking gate |
| 8 — Multi-group | ~2h | Production-ready isolation |
| 9 — Hardening | ~4h | Ship it |

**Total: ~25h of focused build time across 7 layers.**

The natural "demo-able" milestone is after Layer 5 — at that point the agent reads the group
chat, tracks preferences silently, searches Yelp, estimates Uber, and books a table.
