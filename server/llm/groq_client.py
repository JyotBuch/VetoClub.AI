"""Groq client utilities for LetsPlanIt."""
from __future__ import annotations

import asyncio
import os
from typing import Any, Dict, List, Optional

try:  # Optional at import-time for testing environments without Groq SDK.
    from groq import Groq
except ImportError:  # pragma: no cover - handled gracefully when client is requested.
    Groq = None  # type: ignore[assignment]

_client: Optional[Groq] = None


def _get_client() -> Groq:
    """Return a singleton Groq client configured with the API key."""

    global _client
    if _client is not None:
        return _client

    if Groq is None:
        raise RuntimeError("Groq SDK is not installed. Please add 'groq' to your environment.")

    api_key = os.environ.get("GROQ_API_KEY")
    if not api_key:
        raise RuntimeError("GROQ_API_KEY environment variable is not set")

    _client = Groq(api_key=api_key)
    return _client


async def complete(
    model: str,
    messages: List[Dict[str, str]],
    **kwargs: Any,
) -> str:
    """Execute a Groq chat completion and return the first choice content."""

    client = _get_client()

    def _run_completion() -> Any:
        return client.chat.completions.create(model=model, messages=messages, **kwargs)

    response = await asyncio.to_thread(_run_completion)
    if not response.choices:
        return ""

    message = response.choices[0].message
    content = getattr(message, "content", "")
    return content or ""
