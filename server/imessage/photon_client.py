"""Photon watcher client for sending outbound iMessage replies."""
from __future__ import annotations

import logging
import os
from typing import Any

import httpx

LOGGER = logging.getLogger(__name__)
PHOTON_URL_ENV = "PHOTON_WATCHER_URL"
PHOTON_ALT_URL_ENV = "IMESSAGE_BRIDGE_URL"
PHOTON_GUID_ENV = "PHOTON_GROUP_CHAT_GUID"
PHOTON_TOKEN_ENV = "PHOTON_SHARED_SECRET"
PHOTON_ALT_TOKEN_ENV = "IMESSAGE_BRIDGE_TOKEN"
BLUEBUBBLES_URL_ENV = "BLUEBUBBLES_URL"


async def send_message(group_id: str, text: str) -> None:
    """Send a message back to the iMessage group via the Photon watcher."""

    if not group_id or not text:
        return

    base_url = (
        os.environ.get(PHOTON_URL_ENV)
        or os.environ.get(PHOTON_ALT_URL_ENV)
        or os.environ.get(BLUEBUBBLES_URL_ENV)
    )
    if not base_url:
        LOGGER.warning("PHOTON_WATCHER_URL is not configured; skipping send.")
        return

    url = base_url.rstrip("/") + "/imessage/send"
    target_group = os.environ.get(PHOTON_GUID_ENV) or group_id
    headers: dict[str, str] = {}
    shared_secret = os.environ.get(PHOTON_TOKEN_ENV) or os.environ.get(PHOTON_ALT_TOKEN_ENV)
    if shared_secret:
        headers["x-bridge-token"] = shared_secret
    payload: dict[str, Any] = {"chatGuid": target_group, "text": text}

    try:
        async with httpx.AsyncClient(timeout=10) as client:
            response = await client.post(url, json=payload, headers=headers or None)
            response.raise_for_status()
    except Exception as exc:  # pragma: no cover - network errors are expected in tests
        LOGGER.exception("Failed to send Photon message: %s", exc)
        return
