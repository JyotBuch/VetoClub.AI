"""Active agent orchestration for LetsPlanIt."""
from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Tuple

from server.agent.resolver import resolve_full_state
from server.agent.session_utils import build_history, session_to_xml
from server.agent.triggers import strip_trigger
from server.config import THINKING_MODEL
from server.llm.groq_client import complete
from server.state.models import GroupSession
from server.state.session import save
from server.tools import (
    create_group_event,
    estimate_uber_fare,
    find_venues,
    geocode_location,
    get_travel_times,
)

LOGGER = logging.getLogger(__name__)
AGENT_MODEL = THINKING_MODEL
FALLBACK_REPLY = "Sorry, something went wrong. Try again in a moment."

TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "find_venues",
            "description": "Search for restaurants matching group cuisine, dietary needs, vibe, and all member location constraints. Call this when asked to find places.",
            "parameters": {
                "type": "object",
                "properties": {
                    "cuisine": {"type": "string", "description": "e.g. 'italian', 'thai'"},
                    "vibe": {"type": "string", "description": "e.g. 'chill dinner', 'upscale'"},
                    "dietary_filters": {"type": "array", "items": {"type": "string"}},
                    "party_size": {"type": "integer"},
                    "location_constraints": {
                        "type": "array",
                        "items": {
                            "type": "object",
                            "properties": {
                                "member": {"type": "string"},
                                "location": {"type": "string"},
                                "max_distance_mins": {"type": "integer"},
                            },
                            "required": ["member", "location", "max_distance_mins"],
                        },
                    },
                },
                "required": ["cuisine", "party_size", "location_constraints"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "get_uber_estimate",
            "description": "Estimate Uber fare for a specific member from their location to the selected venue. Only call when a member explicitly asks about fare.",
            "parameters": {
                "type": "object",
                "properties": {
                    "member_name": {"type": "string"},
                    "pickup_location": {"type": "string"},
                    "destination_address": {"type": "string"},
                    "budget_cap": {
                        "type": ["integer", "null"],
                        "description": "null if no budget mentioned",
                    },
                },
                "required": ["member_name", "pickup_location", "destination_address"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "create_group_event",
            "description": "Create a Google Calendar event for the group dinner. Only call when can_book is true — all members venue_confirmed.",
            "parameters": {
                "type": "object",
                "properties": {
                    "venue_name": {"type": "string"},
                    "venue_address": {"type": "string"},
                    "time_str": {"type": "string"},
                    "date_str": {"type": "string"},
                    "party_size": {"type": "integer"},
                    "dietary_notes": {"type": "array", "items": {"type": "string"}},
                    "group_id": {"type": "string"},
                },
                "required": ["venue_name", "venue_address", "time_str", "date_str", "party_size", "group_id"],
            },
        },
    },
]

# SYSTEM_PROMPT_STATIC = """You are LetsPlanIt, an AI group outing planner living inside this iMessage group chat.

# ## Persona
# You're friendly, efficient, and on it — like a well-connected friend who actually follows through. You speak casually but stay crisp. This is a chat, not a newsletter.

# ## Core Rules
# 1. **Only respond when explicitly @mentioned.** Never interject unprompted.
# 2. **Be concise.** Max 3 sentences unless presenting options or a summary list.
# 3. **Never confirm or promise a booking** unless `can_book: true` in the group state below.
# 4. **Booking gate:** `can_book` is only true when everyone has `venue_confirmed=true`; agreeing to cuisine alone is not sufficient.
# 5. **Name blockers explicitly.** If waiting on members: "Still need confirmation from Jamie and Priya."
# 6. **When taking action** (searching venues, estimating fares, checking availability), briefly narrate what you're doing before results arrive: "On it — searching rooftop spots in the Mission that work for 7 people."
# 7. **Resolve conflicts gracefully.** If member preferences clash, surface the tradeoff clearly and ask the group to weigh in rather than picking a side.
# 8. **If group state is missing or incomplete**, ask only for what's strictly needed to move forward — one question at a time.

# ## What You Know
# You have full context from the conversation history and structured group state below. Use both to inform every response — don't ask for information that's already there.

# Group state:
# <session>
# {session_xml}
# </session>

# Conversation history (last 20 messages):
# <history>
# {history}
# </history>

# ## Response Format
# - **Searching / acting:** One sentence saying what you're doing.
# - **Presenting options:** Short labeled list (max 4 options), each with 1-line rationale tied to known preferences.
# - **Waiting on people:** Name them. One sentence on what's needed from them.
# - **Ready to book:** Summarize the plan in ≤3 lines, then ask for final go-ahead if `can_book` is true.

# ## Tool Usage Rules
# - Call find_venues when asked to search for restaurants. Always pass:
#   - cuisine from session
#   - all location_constraints from session (never drop any member's constraint)
#   - dietary_filters from session
#   - party_size = number of members in session
# - Present venue results as a numbered list 1–5 with name, rating, price, distance, and one-line vibe description. Members will refer to options by number or name in follow-up messages.
# - If SearchResult.constraints_met is false, lead with the conflict_reason before showing any results. Never silently drop a member's constraint.
# - Call get_uber_estimate only when a specific member asks about their fare. Use their member.location as pickup. Always mention if estimate exceeds budget_cap. Always include the \"Estimate based on distance\" note in your reply.
# - Call create_group_event only when <can_book>true</can_book>. Never call it speculatively or before all members are venue_confirmed. After booking, share the calendar event URL with the group.
# - When a member says \"option 2\", \"the second one\", \"that first place\" — resolve against venue_options list from session (0-indexed).
# """

SYSTEM_PROMPT_STATIC = """You are Planxiety — the one person in this iMessage group who always knows where to go and actually makes it happen. You're not a bot. You're just the most organized one in the chat.

## Vibe
- Text like a real person. Casual, warm, a little playful.
- Short messages. 2-3 sentences max unless you're listing venues.
- No markdown. No bold. No bullet points with dashes. This is iMessage.
- Never say "Certainly!", "Great news!", "I'd be happy to". Just talk normally.
- Never refer to yourself as an AI, assistant, or bot.
- Use people's actual names. Say "y'all" when addressing the group.
- Occasionally use "ok so", "ngl", "lowkey", "honestly", "btw" — but don't overdo it.
- One emoji max, only when it really fits.

## Rules (don't break these)
1. Only respond when @mentioned. Never jump in unprompted.
2. Never confirm a booking unless can_book is true in the session below.
3. can_book is only true when everyone has venue_confirmed=true. Cuisine agreement alone doesn't count.
4. When waiting on people, name them casually: "still waiting on Nidhi and Johi to sign off"
5. If preferences clash, surface it and ask the group — don't pick a side.
6. Don't ask for info that's already in the session or history.

## What you know
Group state:
<session>
{session_xml}
</session>

Recent chat:
<history>
{history}
</history>

## How to respond in each situation

Searching:
"on it, looking for [cuisine] spots near [location] that work for everyone"

Dietary update acknowledged:
"got it [name], filtering for [restriction] places"

Presenting venues — use this exact format, no markdown:

1. Monteverde — 4.7★ $$$ · 12 min · veg friendly
   ngl this place is lowkey incredible, best pasta in the city

2. Piccolo Sogno — 4.6★ $$ · 15 min · veg friendly
   chill garden patio, perfect for a group dinner

3. Osteria Langhe — 4.5★ $$$ · 18 min · veg friendly
   more of a date night spot but the food is unreal

4. La Scarola — 4.4★ $$ · 20 min
   old school italian, cash only fyi

5. Coda di Volpe — 4.3★ $$ · 25 min · veg friendly
   neighborhood gem, never too packed on weeknights

Then add one personal take:
"personally I'd go with Monteverde but that's just me"
or
"Piccolo Sogno is the move if you want something lowkey"

No results found:
"ok so nothing [filter] is showing up near [location] rn — want me to widen the search a bit or switch it up?"

Location conflict:
"ok so [location A] and [location B] are like [N] mins apart which makes this tricky — want me to find a midpoint or should one spot take priority?"

Waiting on confirmations:
"still waiting on [names] to sign off, everyone else is good"

All confirmed:
"ok everyone's in — want me to lock it in and add it to the calendar?"

Uber within budget:
"Uber from [pickup] to [venue] is probably like $[low]-[high], [within/over] your $[cap] btw"
always end with: "heads up this is an estimate based on distance, actual fare may vary"

Booked:
"done! [venue] tonight at [time], party of [n] 🎉
[calendar url]"

## Tool rules
- Call find_venues when asked to search. Always pass cuisine, all location_constraints, dietary_filters, and party_size from session. Never drop a member's constraint.
- If SearchResult.constraints_met is false, lead with the conflict before showing results.
- Call get_uber_estimate only when a member explicitly asks about their fare. Always include the distance-estimate disclaimer.
- Call create_group_event only when can_book is true. Never speculatively.
- Resolve "option 2" / "the second one" / "that first place" against venue_options in session (0-indexed).
"""

SYSTEM_PROMPT_DYNAMIC = """
Current group state:
<session>
{session_xml}
</session>

Conversation history (last 20 messages):
<history>
{history}
</history>
"""


async def execute_tool(name: str, arguments: str, session: GroupSession) -> Tuple[Dict[str, Any], GroupSession]:
    """Execute a tool call and update session state accordingly."""

    try:
        args = json.loads(arguments or "{}")
    except json.JSONDecodeError:
        return {"error": "Invalid tool arguments"}, session

    if name == "find_venues":
        result = await find_venues(**args)
        session.venue_options = result.venues
        if result.venues:
            session.state = "awaiting_confirmation"
        return result.model_dump(), session

    if name == "get_uber_estimate":
        pickup = args.get("pickup_location")
        destination = args.get("destination_address")
        budget_cap = args.get("budget_cap")
        if budget_cap is None:
            budget_cap = session.uber_budget_cap

        pickup_coords = await geocode_location(pickup or "")
        destination_coords = await geocode_location(destination or "")
        if pickup_coords and destination_coords:
            travel_times = await get_travel_times(pickup_coords, [destination or ""])
            duration = travel_times[0] if travel_times else None
            if not duration:
                duration = 20
            distance_meters = duration * 60 * 8  # rough conversion at 8 m/s
            result = estimate_uber_fare(distance_meters, duration, budget_cap)
        else:
            result = {"message": "Could not estimate fare — location not found", "error": True}
        return result, session

    if name == "create_group_event":
        result = await create_group_event(**args)
        if result.get("event_id"):
            session.calendar_event_id = result.get("event_id")
            session.calendar_event_url = result.get("event_url")
            session.state = "booked"
        return result, session

    return {"error": f"Unknown tool: {name}"}, session


async def run_tool_loop(
    initial_response: Any,
    messages: List[Dict[str, Any]],
    session: GroupSession,
    max_iterations: int = 5,
) -> Tuple[str, GroupSession]:
    """Execute tool calls until completion."""

    response = initial_response
    for _ in range(max_iterations):
        if not getattr(response.choices[0], "finish_reason", None) == "tool_calls":
            final_message = getattr(response.choices[0].message, "content", "") or ""
            return final_message, session

        assistant_message = response.choices[0].message
        tool_calls = getattr(assistant_message, "tool_calls", []) or []
        messages.append(
            {
                "role": "assistant",
                "content": assistant_message.content or "",
                "tool_calls": [
                    {
                        "id": tc.id,
                        "type": "function",
                        "function": {"name": tc.function.name, "arguments": tc.function.arguments},
                    }
                    for tc in tool_calls
                ],
            }
        )

        for tc in tool_calls:
            result, session = await execute_tool(tc.function.name, tc.function.arguments, session)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": json.dumps(result)})

        save(session)
        response = await complete(
            model=AGENT_MODEL,
            messages=messages,
            temperature=0.1,
            max_tokens=1024,
            tools=TOOLS,
            tool_choice="auto",
            return_response=True,
        )

    final_choice = response.choices[0]
    final_content = getattr(final_choice.message, "content", "") or ""
    return final_content, session


async def run_agent(text: str, session: GroupSession) -> str:
    """Invoke the active agent when @Agent is mentioned."""

    user_text = strip_trigger(text).strip()
    if not user_text:
        user_text = "Provide guidance to the group using the known context."

    session = await resolve_full_state(session)
    save(session)

    session_xml = session_to_xml(session)
    history_text = build_history(session.message_history)
    context_block = SYSTEM_PROMPT_DYNAMIC.format(session_xml=session_xml, history=history_text)

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT_STATIC},
        {"role": "system", "content": context_block},
        {"role": "user", "content": user_text},
    ]

    try:
        initial_response = await complete(
            model=AGENT_MODEL,
            messages=messages,
            temperature=0.3,
            max_tokens=1024,
            tools=TOOLS,
            tool_choice="auto",
            return_response=True,
        )
        reply, session = await run_tool_loop(initial_response, messages, session)
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.exception("Active agent failed: %s", exc)
        return FALLBACK_REPLY

    return reply or FALLBACK_REPLY
