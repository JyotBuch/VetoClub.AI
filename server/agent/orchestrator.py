"""Active agent orchestration for LetsPlanIt."""
from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List
from xml.sax.saxutils import escape

from server.agent.triggers import strip_trigger
from server.llm.groq_client import complete
from server.state import preferences
from server.state.models import GroupSession, MemberPreference

LOGGER = logging.getLogger(__name__)
AGENT_MODEL = "llama-3.3-70b-versatile"
FALLBACK_REPLY = "Sorry, something went wrong. Try again in a moment."

SYSTEM_PROMPT = """YYou are LetsPlanIt, an AI group outing planner living inside this iMessage group chat.

## Persona
You're friendly, efficient, and on it — like a well-connected friend who actually follows through. You speak casually but stay crisp. This is a chat, not a newsletter.

## Core Rules
1. **Only respond when explicitly @mentioned.** Never interject unprompted.
2. **Be concise.** Max 3 sentences unless presenting options or a summary list.
3. **Never confirm or promise a booking** unless `can_book: true` in the group state below.
4. **Name blockers explicitly.** If waiting on members: "Still need confirmation from Jamie and Priya."
5. **When taking action** (searching venues, estimating fares, checking availability), briefly narrate what you're doing before results arrive: "On it — searching rooftop spots in the Mission that work for 7 people."
6. **Resolve conflicts gracefully.** If member preferences clash, surface the tradeoff clearly and ask the group to weigh in rather than picking a side.
7. **If group state is missing or incomplete**, ask only for what's strictly needed to move forward — one question at a time.

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


def _csv(values: Iterable[str]) -> str:
    filtered = [escape(value.strip()) for value in values if value.strip()]
    return ", ".join(filtered)


def _member_to_xml(member: MemberPreference) -> str:
    return (
        "    <member>\n"
        f"      <name>{escape(member.name)}</name>\n"
        f"      <confirmed>{str(bool(member.confirmed)).lower()}</confirmed>\n"
        f"      <dietary>{_csv(member.dietary)}</dietary>\n"
        f"      <cuisine_likes>{_csv(member.cuisine_likes)}</cuisine_likes>\n"
        f"      <cuisine_dislikes>{_csv(member.cuisine_dislikes)}</cuisine_dislikes>\n"
        "    </member>"
    )


def session_to_xml(session: GroupSession) -> str:
    """Serialize session context into the XML structure expected by the prompt."""

    members_xml = "\n".join(_member_to_xml(member) for member in session.members.values())
    if members_xml:
        members_block = f"  <members>\n{members_xml}\n  </members>"
    else:
        members_block = "  <members />"

    dietary_filters = _csv(session.dietary_filters)
    pending = session.pending_confirmations or preferences.get_unconfirmed(session)
    pending_csv = _csv(pending)
    can_book = bool(session.selected_venue) and preferences.all_confirmed(session)

    def _tag(name: str, value: str | None) -> str:
        return f"  <{name}>{escape(value or '')}</{name}>"

    group_xml = [
        "<group>",
        _tag("state", session.state),
        _tag("cuisine", session.cuisine),
        _tag("time", session.time),
        _tag("location_anchor", session.location_anchor),
        f"  <dietary_filters>{dietary_filters}</dietary_filters>",
        members_block,
        f"  <can_book>{str(can_book).lower()}</can_book>",
        f"  <pending_confirmations>{pending_csv}</pending_confirmations>",
        "</group>",
    ]
    return "\n".join(group_xml)


def _build_history(history: List[Dict[str, Any]]) -> str:
    lines: List[str] = []
    for entry in history:
        sender = entry.get("sender") or "Unknown"
        text = entry.get("text") or ""
        lines.append(f"{sender}: {text}")
    return "\n".join(lines)


async def run_agent(text: str, session: GroupSession) -> str:
    """Invoke the active agent when @Agent is mentioned."""

    user_text = strip_trigger(text).strip()
    if not user_text:
        user_text = "Provide guidance to the group using the known context."

    session_xml = session_to_xml(session)
    history_text = _build_history(session.message_history)
    system_content = SYSTEM_PROMPT.format(session_xml=session_xml, history=history_text)

    messages = [
        {"role": "system", "content": system_content},
        {"role": "user", "content": user_text},
    ]

    try:
        response = await complete(
            model=AGENT_MODEL,
            messages=messages,
            temperature=0.3,
        )
        return response.strip() or FALLBACK_REPLY
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.exception("Active agent failed: %s", exc)
        return FALLBACK_REPLY
