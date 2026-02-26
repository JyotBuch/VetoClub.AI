"""Simple in-memory session store for LetsPlanIt."""
from __future__ import annotations

from typing import Dict, List, Optional

from .models import GroupSession

_sessions: Dict[str, GroupSession] = {}


def get_or_create(group_id: str) -> GroupSession:
    """Return an existing session or create a fresh one."""

    if not group_id:
        raise ValueError("group_id must be a non-empty string")

    if group_id not in _sessions:
        _sessions[group_id] = GroupSession(group_id=group_id)
    return _sessions[group_id]


def save(session: GroupSession) -> None:
    """Persist a session in-memory while updating its timestamp."""

    if not session.group_id:
        raise ValueError("session.group_id must be set before saving")

    session.touch()
    _sessions[session.group_id] = session


def get_all() -> List[GroupSession]:
    """Return all known sessions."""

    return list(_sessions.values())


def get(group_id: str) -> Optional[GroupSession]:
    """Fetch a session without creating it."""

    return _sessions.get(group_id)


def delete(group_id: str) -> bool:
    """Delete a session if it exists."""

    if group_id in _sessions:
        del _sessions[group_id]
        return True
    return False


def clear() -> None:
    """Remove all sessions from the in-memory store."""

    _sessions.clear()
