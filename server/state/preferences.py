"""Helpers for manipulating per-member preferences within a session."""
from __future__ import annotations

from typing import Any, Mapping

from .models import GroupSession, MemberPreference


def upsert_member(session: GroupSession, name: str, updates: Mapping[str, Any]) -> None:
    """Create or merge a member preference profile."""

    if not name:
        raise ValueError("name must be provided")

    payload = dict(updates or {})
    payload["name"] = name

    existing = session.members.get(name)
    if existing is None:
        session.members[name] = MemberPreference(**payload)
        return

    for key, value in payload.items():
        if key == "name":
            continue
        if isinstance(value, list):
            current: list[Any] = getattr(existing, key, []) or []
            merged = list(dict.fromkeys(current + value))
            setattr(existing, key, merged)
        else:
            setattr(existing, key, value)


def get_unconfirmed(session: GroupSession) -> list[str]:
    """Return names for members who have not confirmed the venue yet."""

    return [name for name, pref in session.members.items() if not pref.venue_confirmed]


def all_confirmed(session: GroupSession) -> bool:
    """True only when the group has members and each confirmed the venue."""

    if not session.members:
        return False
    return all(pref.venue_confirmed for pref in session.members.values())


def merge_dietary(session: GroupSession) -> list[str]:
    """Union of all members' dietary filters with deduplication."""

    merged: list[str] = []
    seen: set[str] = set()
    for pref in session.members.values():
        for restriction in pref.dietary:
            normalized = restriction.strip()
            if not normalized:
                continue
            if normalized not in seen:
                seen.add(normalized)
                merged.append(normalized)
    return merged
