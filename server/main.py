"""FastAPI entry point for LetsPlanIt."""
from __future__ import annotations

from fastapi import FastAPI
from pydantic import BaseModel

from server.agent.context import extract_and_merge
from server.agent.orchestrator import run_agent
from server.agent.triggers import is_agent_mentioned
from server.imessage.photon_client import send_message
from server.state.session import get_or_create, save

app = FastAPI()


class MessagePayload(BaseModel):
    group_id: str
    sender: str
    text: str
    timestamp: str
    is_self: bool = False


@app.post("/webhook")
async def webhook(payload: MessagePayload) -> dict[str, str]:
    """Handle inbound messages from the Photon watcher."""

    if payload.is_self:
        return {"status": "ignored"}

    session = get_or_create(payload.group_id)

    message_entry = payload.model_dump()
    session.append_message(message_entry)

    session = await extract_and_merge(message_entry, session)
    save(session)

    if is_agent_mentioned(payload.text):
        reply = await run_agent(payload.text, session)
        await send_message(payload.group_id, reply)

    return {"status": "ok"}
