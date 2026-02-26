"""Trigger utilities for detecting @Agent mentions."""
from __future__ import annotations

AGENT_TRIGGERS = ["@agent", "@Agent", "@AGENT"]


def is_agent_mentioned(text: str) -> bool:
    """Return True if any trigger phrase appears in the text."""

    if not text:
        return False
    return any(trigger in text for trigger in AGENT_TRIGGERS)


def strip_trigger(text: str) -> str:
    """Remove all trigger phrases from the provided text."""

    if not text:
        return ""
    cleaned = text
    for trigger in AGENT_TRIGGERS:
        cleaned = cleaned.replace(trigger, "")
    return cleaned.strip()
