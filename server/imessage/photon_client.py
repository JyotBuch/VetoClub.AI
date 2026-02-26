"""Photon watcher client for sending outbound iMessage replies."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
PHOTON_URL_ENV = "PHOTON_WATCHER_URL"


async def send_message(group_id: str, text: str) -> None:
    """Send a message back to the iMessage group via the Photon watcher."""

    if not group_id or not text:
        return

    base_url = os.environ.get(PHOTON_URL_ENV)
    if not base_url:
        LOGGER.warning("PHOTON_WATCHER_URL is not configured; skipping send.")
        return

    url = base_url.rstrip("/") + "/imessage/send"
    payload: dict[str, Any] = {"group_id": group_id, "text": text}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload)
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network errors are expected in tests
        LOGGER.exception("Failed to send Photon message: %s", exc)
        return
