"""Photon bridge client utilities."""
from __future__ import annotations

import logging
import os
from typing import Any, Dict

import httpx

logger = logging.getLogger("grouptrip.photon")


class PhotonClientError(RuntimeError):
    """Raised when the Photon client fails to send a message."""


async def send_message(chat_guid: str, text: str) -> None:
    """Send a message to the given chat via the local Photon bridge server."""

    base_url = (
        os.getenv("IMESSAGE_BRIDGE_URL")
        or os.getenv("BLUEBUBBLES_URL")  # backwards compatibility
        or "http://127.0.0.1:3001"
    )
    shared_secret = os.getenv("IMESSAGE_BRIDGE_TOKEN")

    endpoint = os.getenv("IMESSAGE_BRIDGE_SEND_PATH", "/imessage/send")
    url = f"{base_url.rstrip('/')}{endpoint}"
    payload: Dict[str, Any] = {
        "chatGuid": chat_guid,
        "text": text,
    }

    logger.debug("Sending Photon message to %s", chat_guid)

    try:
        headers = {"x-bridge-token": shared_secret} if shared_secret else None
        async with httpx.AsyncClient(timeout=5.0) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
    except httpx.HTTPStatusError as exc:
        logger.error("Photon HTTP error %s: %s", exc.response.status_code, exc.response.text)
        raise PhotonClientError("Photon API returned an error") from exc
    except httpx.HTTPError as exc:  # network failure, timeout, etc.
        logger.error("Photon request failed: %s", exc)
        raise PhotonClientError("Photon API request failed") from exc

    logger.info("Photon send succeeded for chat %s", chat_guid)
