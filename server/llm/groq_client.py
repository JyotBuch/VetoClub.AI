"""Groq client utilities for LetsPlanIt."""
from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

try:  # Optional at import-time for testing environments without Groq SDK.
    from groq import Groq
except ImportError:  # pragma: no cover - handled gracefully when client is requested.
    Groq = None  # type: ignore[assignment]

LOGGER = logging.getLogger(__name__)
TOKEN_LOG_PATH = Path("token_usage.log")

_client: Optional[Groq] = None


def _log_usage(model: str, usage: Any) -> None:
    if usage is None:
        return
    record = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "model": model,
        "prompt_tokens": getattr(usage, "prompt_tokens", None),
        "completion_tokens": getattr(usage, "completion_tokens", None),
        "total_tokens": getattr(usage, "total_tokens", None),
    }
    try:
        with TOKEN_LOG_PATH.open("a", encoding="utf-8") as log_file:
            log_file.write(json.dumps(record) + "\n")
    except Exception as exc:  # pragma: no cover - logging best effort
        LOGGER.debug("Failed to log token usage: %s", exc)


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
    messages: List[Dict[str, Any]],
    return_response: bool = False,
    **kwargs: Any,
) -> Any:
    """Execute a Groq chat completion and optionally return the raw response."""

    client = _get_client()

    def _run_completion() -> Any:
        return client.chat.completions.create(model=model, messages=messages, **kwargs)

    response = await asyncio.to_thread(_run_completion)
    _log_usage(model, getattr(response, "usage", None))
    if return_response:
        return response

    if not getattr(response, "choices", None):
        return ""

    message = response.choices[0].message
    content = getattr(message, "content", "")
    return content or ""
