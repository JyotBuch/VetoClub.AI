"""Silent extraction utilities for LetsPlanIt."""
from __future__ import annotations

import logging
from collections import Counter
from typing import Any, Dict, List, Optional
from xml.etree import ElementTree as ET

from server.llm.groq_client import complete
from server.state import preferences
from server.state.models import GroupSession

LOGGER = logging.getLogger(__name__)
MODEL_NAME = "llama-3.1-8b-instant"

EXTRACTION_SYSTEM_PROMPT = (
    "You are an extraction engine for group chat planning. "
    "Return ONLY the XML block exactly as specified. No prose, no markdown. "
    "If a field is unknown leave it empty. Values inside tags must be comma-separated without extra text. "
    "`dietary` is strictly for food restrictions/allergies (vegetarian, vegan, halal, kosher, gluten-free, nut-free, dairy-free). "
    "Dislikes, recent meals, or cuisine preferences belong in cuisine_dislikes/cuisine_likes, never dietary. "
    "If the sender pivots away from a previous cuisine (\"actually can we do Italian? I just had Indian food\"), "
    "record the old cuisine in cuisine_dislikes and the new one in cuisine_likes; do not carry the old cuisine forward as a like."
)

XML_TEMPLATE = (
    "<extraction>\n"
    "  <dietary></dietary>\n"
    "  <cuisine_likes></cuisine_likes>\n"
    "  <cuisine_dislikes></cuisine_dislikes>\n"
    "  <location></location>\n"
    "  <confirmed></confirmed>\n"
    "  <time></time>\n"
    "</extraction>"
)


def _build_user_prompt(sender: str, message: str) -> str:
    return (
        "Extract structured preferences from the following message. "
        "Respond only with the XML template filled with extracted data.\n\n"
        f"Sender: {sender}\n"
        f"Message: {message}\n\n"
        f"Template:\n{XML_TEMPLATE}"
    )


def _split_csv(value: Optional[str]) -> List[str]:
    if not value:
        return []
    parts = [item.strip() for item in value.split(",")]
    return [item for item in parts if item]


def _extract_xml_block(raw: str) -> Optional[str]:
    if not raw:
        return None
    start = raw.find("<extraction")
    end = raw.rfind("</extraction>")
    if start == -1 or end == -1:
        return None
    end += len("</extraction>")
    return raw[start:end]


def parse_extraction(raw: str) -> Dict[str, Any]:
    """Parse the XML extraction output into a structured dict."""

    block = _extract_xml_block(raw.strip()) if raw else None
    if not block:
        return {}

    try:
        root = ET.fromstring(block)
    except ET.ParseError:
        return {}

    if root.tag != "extraction":
        return {}

    data: Dict[str, Any] = {}
    list_fields = ["dietary", "cuisine_likes", "cuisine_dislikes"]
    for field in list_fields:
        text = root.findtext(field)
        values = _split_csv(text)
        if values:
            data[field] = values

    location = (root.findtext("location") or "").strip()
    if location:
        data["location"] = location

    time_value = (root.findtext("time") or "").strip()
    if time_value:
        data["time"] = time_value

    confirmed_raw = (root.findtext("confirmed") or "").strip().lower()
    confirmed: Optional[bool]
    if confirmed_raw == "true":
        confirmed = True
    elif confirmed_raw == "false":
        confirmed = False
    else:
        confirmed = None
    data["venue_confirmed"] = confirmed

    return data


async def extract_and_merge(msg: Dict[str, Any], session: GroupSession) -> GroupSession:
    """Call Groq silently and merge the extracted data into the session."""

    LOGGER.debug("[extract] processing message from %s", msg.get("sender"))
    sender = msg.get("sender")
    text = msg.get("text", "")
    if not sender or not text:
        return session

    user_prompt = _build_user_prompt(sender, text)
    messages = [
        {"role": "system", "content": EXTRACTION_SYSTEM_PROMPT},
        {"role": "user", "content": user_prompt},
    ]

    try:
        raw_response = await complete(
            model=MODEL_NAME,
            messages=messages,
            temperature=0,
        )
        extracted = parse_extraction(raw_response)
    except Exception as exc:  # pragma: no cover - defensive guard
        LOGGER.exception("Silent extraction failed: %s", exc)
        return session

    if not extracted:
        return session

    updates: Dict[str, Any] = {}
    for field in ("dietary", "cuisine_likes", "cuisine_dislikes"):
        values = extracted.get(field) or []
        if values:
            updates[field] = values
    location = extracted.get("location")
    if location:
        updates["location"] = location
    confirmed = extracted.get("venue_confirmed")
    if confirmed is not None:
        updates["venue_confirmed"] = confirmed

    if updates:
        preferences.upsert_member(session, sender, updates)
        if not session.cuisine:
            tally: Counter[str] = Counter()
            for pref in session.members.values():
                for like in pref.cuisine_likes:
                    if like:
                        tally[like.lower()] += 1
            if tally:
                cuisine, count = tally.most_common(1)[0]
                if count >= 3:
                    session.cuisine = cuisine

    time_value = extracted.get("time")
    if time_value:
        session.time = time_value
    if location:
        session.location_anchor = location

    session.dietary_filters = preferences.merge_dietary(session)

    return session
