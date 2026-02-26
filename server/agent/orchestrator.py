"""Active agent orchestration for LetsPlanIt."""
from __future__ import annotations

import logging
from typing import Any, Dict

from server.agent.resolver import resolve_full_state
from server.agent.session_utils import build_history, session_to_xml
from server.agent.triggers import strip_trigger
from server.llm.groq_client import complete
from server.state.models import GroupSession
from server.state.session import save

LOGGER = logging.getLogger(__name__)
AGENT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_REPLY = "Sorry, something went wrong. Try again in a moment."

SYSTEM_PROMPT = """You are LetsPlanIt, an AI group outing planner living inside this iMessage group chat.

## Persona
You're friendly, efficient, and on it — like a well-connected friend who actually follows through. You speak casually but stay crisp. This is a chat, not a newsletter.

## Core Rules
1. **Only respond when explicitly @mentioned.** Never interject unprompted.
2. **Be concise.** Max 3 sentences unless presenting options or a summary list.
3. **Never confirm or promise a booking** unless `can_book: true` in the group state below.
4. **Booking gate:** `can_book` is only true when everyone has `venue_confirmed=true`; agreeing to cuisine alone is not sufficient.
5. **Name blockers explicitly.** If waiting on members: "Still need confirmation from Jamie and Priya."
6. **When taking action** (searching venues, estimating fares, checking availability), briefly narrate what you're doing before results arrive: "On it — searching rooftop spots in the Mission that work for 7 people."
7. **Resolve conflicts gracefully.** If member preferences clash, surface the tradeoff clearly and ask the group to weigh in rather than picking a side.
8. **If group state is missing or incomplete**, ask only for what's strictly needed to move forward — one question at a time.

## What You Know
You have full context from the conversation history and structured group state below. Use both to inform every response — don't ask for information that's already there.

Group state:
<session>
{session_xml}
</session>

Conversation history (last 20 messages):
<history>
{history}
</history>

## Response Format
- **Searching / acting:** One sentence saying what you're doing.
- **Presenting options:** Short labeled list (max 4 options), each with 1-line rationale tied to known preferences.
- **Waiting on people:** Name them. One sentence on what's needed from them.
- **Ready to book:** Summarize the plan in ≤3 lines, then ask for final go-ahead if `can_book` is true.
"""


async def run_agent(text: str, session: GroupSession) -> str:
    """Invoke the active agent when @Agent is mentioned."""

    user_text = strip_trigger(text).strip()
    if not user_text:
        user_text = "Provide guidance to the group using the known context."

    session = await resolve_full_state(session)
    save(session)

    session_xml = session_to_xml(session)
    history_text = build_history(session.message_history)
    system_content = SYSTEM_PROMPT.format(session_xml=session_xml, history=history_text)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_text},
    ]

    try:
        raw_response = await complete(
            model=AGENT_MODEL,
            messages=messages,
            temperature=0.3,
        )
        reply = raw_response.strip() or FALLBACK_REPLY
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.exception("Active agent failed: %s", exc)
        return FALLBACK_REPLY

    return reply
