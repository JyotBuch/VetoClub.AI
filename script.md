# LetsPlanIt — Live Demo Script
### Chicago Dinner · 4 Friends · iMessage Group
> This is a real transcript of the agent running end-to-end on February 26, 2026.
> All agent responses were generated live by `llama-3.3-70b-versatile` via Groq.
> No responses were hardcoded or scripted.

---

## Scene 1 — The Plan Begins
*Agent is silent. Every message is being processed by `llama-3.1-8b-instant` in the background.*

> **Jyot:** Guys we should do something tonight!

> **Nidhi:** I dont mind Indian food actually!
> `→ [silent] Nidhi.cuisine_likes = ["Indian"]`

> **Johi:** Yeah Indian works for me too!
> `→ [silent] Johi.cuisine_likes = ["Indian"]`

> **Alisha:** Actually can we do Italian? I just had Indian food
> `→ [silent] Alisha.cuisine_likes = ["Italian"], cuisine_dislikes = ["Indian"]`

> **Nidhi:** Im good with Italian, havent had that in a while
> `→ [silent] Nidhi.cuisine_likes = ["Indian", "Italian"]`

> **Johi:** Yeah lets do it tonight at 8
> `→ [silent] session.time = "8"`

**State after Scene 1**
```
cuisine:          null        ← not yet resolved at group level
time:             "8"
location_anchor:  null
dietary_filters:  []
members:
  Jyot    cuisine_likes=[]          venue_confirmed=false
  Nidhi   cuisine_likes=[Italian]   venue_confirmed=false
  Johi    cuisine_likes=[Indian]    venue_confirmed=false
  Alisha  cuisine_likes=[Italian]   venue_confirmed=false
                  cuisine_dislikes=[Indian]
```

---

## Scene 2 — @Agent Activated
*Nidhi mentions @Agent. `resolve_full_state` runs with full conversation history.
`llama-3.3-70b-versatile` takes over.*

> **Nidhi:** find Italian places in Chicago with a chill dinner vibe @Agent

**🤖 Agent →**
```
On it — searching for Italian restaurants in Chicago that fit
a chill dinner vibe for 4 people at 8 PM.
```

**State after Scene 2**
```
state:            searching   ← advanced from idle
event_type:       dinner
cuisine:          "Italian"   ← resolver set from group consensus
time:             "8"
location_anchor:  "Chicago"   ← extracted from Nidhi's message
dietary_filters:  []
members:
  Jyot    venue_confirmed=false
  Nidhi   cuisine_likes=[Indian, Italian]   location=Chicago   venue_confirmed=false
  Johi    cuisine_likes=[Indian]            venue_confirmed=false
  Alisha  cuisine_likes=[Italian]           venue_confirmed=false
```

---

## Scene 3 — Mid-Conversation Dietary Update
*Alisha mentions @Agent with a new constraint.
Resolver updates dietary filters without losing prior state.*

> **Alisha:** Actually I am vegetarian today, can you make sure they serve veg food? @Agent

**🤖 Agent →**
```
On it — searching for Italian restaurants in Chicago that serve
vegetarian options and have a chill dinner vibe for 8 PM.
```

**State after Scene 3**
```
state:            searching
cuisine:          "Italian"
dietary_filters:  ["vegetarian"]   ← added from Alisha's update
members:
  Alisha  dietary=["vegetarian"]   venue_confirmed=false
  (others unchanged)
```

---

## Scene 4 — Confirmation Gating
*Jyot names the venue. Alisha agrees implicitly.
Jyot triggers @Agent to confirm.*

> **Jyot:** La Italiano works for me
> `→ [silent] Jyot.venue_confirmed = true, selected_venue = "La Italiano"`

> **Alisha:** Yeah Im good with that option too
> `→ [silent] resolver resolves "that option" → La Italiano → Alisha.venue_confirmed = true`

> **Jyot:** Confirm that option for us @Agent

**🤖 Agent →**
```
Still need confirmation from Nidhi and Johi on La Italiano
as the chosen venue.
```

**State after Scene 4**
```
state:            awaiting_confirmation
selected_venue:   {"name": "La Italiano"}
members:
  Jyot    venue_confirmed=true   ✓
  Nidhi   venue_confirmed=false  ✗  ← named by agent
  Johi    venue_confirmed=false  ✗  ← named by agent
  Alisha  venue_confirmed=true   ✓  ← "that option" resolved correctly
```

---

## Scene 5 — Remaining Confirmations + Uber Check
*Nidhi confirms silently. Johi asks about Uber before committing.*

> **Nidhi:** Works for me
> `→ [silent] Nidhi.venue_confirmed = true`

> **Johi:** How much would an Uber cost me from Riverwalk? @Agent

**🤖 Agent →**
```
On it — estimating the Uber fare from Riverwalk to La Italiano.
```

**State after Scene 5**
```
state:            awaiting_confirmation
location_anchor:  "Riverwalk"   ← updated from Johi's message
selected_venue:   {"name": "La Italiano"}
members:
  Jyot    venue_confirmed=true   ✓
  Nidhi   venue_confirmed=true   ✓
  Johi    venue_confirmed=false  ✗   location="Riverwalk"
  Alisha  venue_confirmed=true   ✓
```

---

## Scene 6 — Booked
*Johi confirms and asks to book. All 4 members confirmed.
Agent completes the reservation.*

> **Johi:** Cool make the reservation @Agent

**🤖 Agent →**
```
You guys are on for La Italiano tonight at 8!
```

**State after Scene 6**
```
state:            booked   ✓
selected_venue:   {"name": "La Italiano"}
cuisine:          "Italian"
time:             "8"
location_anchor:  "Riverwalk"
dietary_filters:  ["vegetarian"]
members:
  Jyot    venue_confirmed=true   ✓
  Nidhi   venue_confirmed=true   ✓
  Johi    venue_confirmed=true   ✓
  Alisha  venue_confirmed=true   ✓
                  dietary=["vegetarian"]
```

---

## What the Agent Got Right

| Capability | Evidence |
|---|---|
| Silent preference extraction | Cuisine preferences populated across 6 messages with no @Agent |
| Time extraction | `session.time = "8"` from *"lets do it tonight at 8"* |
| Location extraction | `location_anchor` updated from both *"Chicago"* and *"Riverwalk"* |
| Mid-conversation dietary update | Alisha's vegetarian constraint picked up and reflected in reply |
| Pronoun resolution | *"Yeah I'm good with that option too"* → `Alisha.venue_confirmed = true` |
| Confirmation gating | Correctly named Nidhi and Johi as unconfirmed, blocked booking |
| Party size awareness | Agent said *"for 4 people"* without being told the group size |
| State machine | `idle → searching → awaiting_confirmation → booked` |
| Uber context | Extracted Johi's pickup location from a casual question, not a command |

---

## Known Gaps (fixed before Layer 5)

| Issue | Detail |
|---|---|
| `Alisha.dietary` noise | *"I just had Indian food"* incorrectly extracted as dietary restriction, not cuisine dislike |
| `Nidhi.cuisine_likes` carries both | `["Indian", "Italian"]` — correct but noisy for Yelp filtering |
| `Johi.cuisine_likes` not updated | Still shows `["Indian"]` after implicitly agreeing to Italian |

---

*Layer 5 wires real Yelp, Maps, Uber, and OpenTable tool calls into this exact flow.*
*The agent responses above will become real venue suggestions, real distances, real fares, and real reservations.*