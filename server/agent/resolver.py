"""Post-response resolution for LetsPlanIt sessions."""
from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from server.agent.session_utils import build_history, session_to_xml
from server.llm.groq_client import complete
from server.state import preferences
from server.state.models import GroupSession

LOGGER = logging.getLogger(__name__)
MODEL_NAME = "llama-3.3-70b-versatile"
VALID_STATES = {"idle", "gathering", "searching", "awaiting_confirmation", "booking", "booked"}

SYSTEM_MESSAGE = (
    "You are LetsPlanIt's state resolver. Return only the requested XML snapshot with no extra text."
)
PROMPT_TEMPLATE = (
    "Using the group chat history and current session state, resolve the definitive ground truth. "
    "Clarify pronouns, references, implicit agreements, and temporary dietary constraints.\n\n"
    "Return ONLY this XML block, no prose, no markdown:\n\n"
    "<resolved_state>\n"
    "  <session>\n"
    "    <state></state>\n"
    "    <event_type></event_type>\n"
    "    <cuisine></cuisine>\n"
    "    <time></time>\n"
    "    <location_anchor></location_anchor>\n"
    "    <dietary_filters></dietary_filters>\n"
    "    <selected_venue></selected_venue>\n"
    "  </session>\n"
    "  <members>\n"
    "    <member>\n"
    "      <name></name>\n"
    "      <dietary></dietary>\n"
    "      <cuisine_likes></cuisine_likes>\n"
    "      <cuisine_dislikes></cuisine_dislikes>\n"
    "      <location></location>\n"
    "      <venue_confirmed>false</venue_confirmed>\n"
    "    </member>\n"
    "  </members>\n"
    "</resolved_state>\n\n"
    "Rules:\n"
    "- 'That option', 'it', 'that place' ALWAYS refers to the most recently named venue in the conversation.\n"
    "- Phrases like \"Yeah I'm good with that\", \"works for me\", \"sounds good\" mean venue_confirmed=true for the speaker.\n"
    "- If a venue has been named and members are confirming it, populate <selected_venue> with that venue name; otherwise leave it empty.\n"
    "- The <state> field must be exactly one of: idle, gathering, searching, awaiting_confirmation, booking, booked.\n"
    "- Any mention of dietary needs, even temporary ones (\"today\", \"tonight\"), must update that member's dietary list and be included in dietary_filters.\n"
    "- Only include facts supported by the chat. If uncertain, leave the tag empty.\n\n"
    "Current session state:\n<session>\n{session_xml}\n</session>\n\n"
    "Full conversation history:\n<history>\n{history}\n</history>"
)


def _extract_xml_block(raw: str) -> Optional[str]:
    if not raw:
        return None
    start = raw.find("<resolved_state")
    end = raw.rfind("</resolved_state>")
    if start == -1 or end == -1:
        return None
    end += len("</resolved_state>")
    return raw[start:end]


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_member(node: ET.Element) -> Dict[str, Any]:
    data: Dict[str, Any] = {}
    name = (node.findtext("name") or "").strip()
    if not name:
        return {}
    data["name"] = name
    for field in ("dietary", "cuisine_likes", "cuisine_dislikes"):
        values = _split_csv(node.findtext(field))
        if values:
            data[field] = values
    location = (node.findtext("location") or "").strip()
    if location:
        data["location"] = location
    for field in ("venue_confirmed",):
        text = (node.findtext(field) or "").strip().lower()
        if text in {"true", "false"}:
            data[field] = text == "true"
    return data


def _parse_response(raw: str) -> Dict[str, Any]:
    block = _extract_xml_block(raw.strip()) if raw else None
    if not block:
        return {}
    try:
        root = ET.fromstring(block)
    except ET.ParseError:
        return {}
    if root.tag != "resolved_state":
        return {}

    data: Dict[str, Any] = {"session": {}, "members": []}
    session_el = root.find("session")
    if session_el is not None:
        for tag in ("state", "event_type", "cuisine", "time", "location_anchor", "selected_venue"):
            text = (session_el.findtext(tag) or "").strip()
            if text:
                data["session"][tag] = text
        dietary_filters = _split_csv(session_el.findtext("dietary_filters"))
        if dietary_filters:
            data["session"]["dietary_filters"] = dietary_filters

    members_el = root.find("members")
    if members_el is not None:
        for member_el in members_el.findall("member"):
            parsed = _parse_member(member_el)
            if parsed:
                data["members"].append(parsed)

    return data


def _apply_snapshot(session: GroupSession, snapshot: Dict[str, Any]) -> GroupSession:
    session_fields = snapshot.get("session", {})
    for key in ("state", "event_type", "cuisine", "time", "location_anchor"):
        if key not in session_fields:
            continue
        value = session_fields[key]
        if key == "state" and value not in VALID_STATES:
            LOGGER.warning("[resolver] invalid state value '%s' — skipping", value)
            continue
        setattr(session, key, value)
    if "selected_venue" in session_fields:
        venue = session_fields["selected_venue"]
        session.selected_venue = {"name": venue} if venue else None

    for member_data in snapshot.get("members", []):
        name = member_data.get("name")
        if not name:
            continue
        payload: Dict[str, Any] = {"name": name}
        for field in ("dietary", "cuisine_likes", "cuisine_dislikes", "location"):
            if field in member_data:
                payload[field] = member_data[field]
        for field in ("venue_confirmed",):
            if field in member_data:
                payload[field] = member_data[field]
        preferences.upsert_member(session, name, payload)

    session.dietary_filters = preferences.merge_dietary(session)
    return session


async def resolve_full_state(session: GroupSession) -> GroupSession:
    """Resolve full session truth using the high-capacity model."""

    prompt = PROMPT_TEMPLATE.format(
        session_xml=session_to_xml(session),
        history=build_history(session.message_history),
    )
    messages = [
        {"role": "system", "content": SYSTEM_MESSAGE},
        {"role": "user", "content": prompt},
    ]

    try:
        raw_response = await complete(
            model=MODEL_NAME,
            messages=messages,
            temperature=0.2,
        )
        snapshot = _parse_response(raw_response)
    except Exception as exc:  # pragma: no cover
        LOGGER.exception("State resolution failed: %s", exc)
        return session

    if not snapshot:
        return session

    return _apply_snapshot(session, snapshot)
