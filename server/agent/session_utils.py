"""Shared helpers for formatting session context."""
from __future__ import annotations

from typing import Iterable, List
from xml.sax.saxutils import escape

from server.state import preferences
from server.state.models import GroupSession, MemberPreference


def _csv(values: Iterable[str]) -> str:
    filtered = [escape(value.strip()) for value in values if value.strip()]
    return ", ".join(filtered)


def _member_to_xml(member: MemberPreference) -> str:
    return (
        "    <member>\n"
        f"      <name>{escape(member.name)}</name>\n"
        f"      <venue_confirmed>{str(bool(member.venue_confirmed)).lower()}</venue_confirmed>\n"
        f"      <dietary>{_csv(member.dietary)}</dietary>\n"
        f"      <cuisine_likes>{_csv(member.cuisine_likes)}</cuisine_likes>\n"
        f"      <cuisine_dislikes>{_csv(member.cuisine_dislikes)}</cuisine_dislikes>\n"
        "    </member>"
    )


def session_to_xml(session: GroupSession) -> str:
    """Serialize session context into the XML structure expected by prompts."""

    members_xml = "\n".join(_member_to_xml(member) for member in session.members.values())
    if members_xml:
        members_block = f"  <members>\n{members_xml}\n  </members>"
    else:
        members_block = "  <members />"

    dietary_filters = _csv(session.dietary_filters)
    pending = preferences.get_unconfirmed(session)
    pending_csv = _csv(pending)
    can_book = bool(session.selected_venue) and preferences.all_confirmed(session)

    def _tag(name: str, value: str | None) -> str:
        return f"  <{name}>{escape(value or '')}</{name}>"

    selected_name = ""
    if isinstance(session.selected_venue, dict):
        selected_name = session.selected_venue.get("name") or ""

    constraints_xml = "".join(
        [
            f"<constraint><member>{escape(c.member)}</member>"
            f"<location>{escape(c.location)}</location>"
            f"<max_distance_mins>{c.max_distance_mins}</max_distance_mins></constraint>"
            for c in session.location_constraints
        ]
    )

    option_entries = []
    for index, option in enumerate(session.venue_options, start=1):
        veg_tag = "veg ✓" if option.vegetarian_friendly else ""
        option_text = (
            f"{option.name} · {option.rating}★ · {option.price or ''} · "
            f"{option.distance_mins}min · {veg_tag}"
        )
        option_entries.append(f"<option index='{index}'>{escape(option_text)}</option>")
    options_xml = "".join(option_entries)

    party_size = len({entry.get("sender") for entry in session.message_history if entry.get("sender")})

    group_xml = [
        "<group>",
        _tag("state", session.state),
        _tag("event_type", session.event_type),
        _tag("cuisine", session.cuisine),
        _tag("time", session.time),
        _tag("location_anchor", session.location_anchor),
        _tag("selected_venue", selected_name),
        f"  <dietary_filters>{dietary_filters}</dietary_filters>",
        f"  <location_constraints>{constraints_xml}</location_constraints>",
        f"  <venue_options>{options_xml}</venue_options>",
        _tag("calendar_event_url", session.calendar_event_url),
        members_block,
        f"  <can_book>{str(can_book).lower()}</can_book>",
        f"  <pending_confirmations>{pending_csv}</pending_confirmations>",
        f"  <party_size>{party_size}</party_size>",
        "</group>",
    ]
    return "\n".join(group_xml)


def build_history(history: List[dict]) -> str:
    """Format message history into sender-prefixed lines."""

    lines: List[str] = []
    for entry in history:
        sender = entry.get("sender") or "Unknown"
        text = entry.get("text") or ""
        lines.append(f"{sender}: {text}")
    return "\n".join(lines)
