"""State and preference models for LetsPlanIt."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Literal, Optional

from pydantic import BaseModel, ConfigDict, Field, field_validator

MAX_MESSAGE_HISTORY = 20


class MemberPreference(BaseModel):
    """Per-member preference profile captured from chat."""

    model_config = ConfigDict(validate_assignment=True)

    name: str
    dietary: list[str] = Field(default_factory=list)
    cuisine_likes: list[str] = Field(default_factory=list)
    cuisine_dislikes: list[str] = Field(default_factory=list)
    location: Optional[str] = None
    confirmed: bool = False


class GroupSession(BaseModel):
    """In-memory representation of a group's planning session."""

    model_config = ConfigDict(validate_assignment=True)

    group_id: str
    members: Dict[str, MemberPreference] = Field(default_factory=dict)
    state: Literal[
        "idle",
        "gathering",
        "searching",
        "awaiting_confirmation",
        "booking",
        "booked",
    ] = "idle"
    event_type: Optional[str] = None
    cuisine: Optional[str] = None
    time: Optional[str] = None
    location_anchor: Optional[str] = None
    max_distance_mins: int = 30
    dietary_filters: list[str] = Field(default_factory=list)
    pending_confirmations: list[str] = Field(default_factory=list)
    selected_venue: Optional[Dict[str, Any]] = None
    message_history: list[Dict[str, Any]] = Field(default_factory=list)
    last_updated: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))

    @field_validator("message_history", mode="after")
    @classmethod
    def _trim_message_history(
        cls, history: list[Dict[str, Any]]
    ) -> list[Dict[str, Any]]:
        if len(history) <= MAX_MESSAGE_HISTORY:
            return history
        return history[-MAX_MESSAGE_HISTORY:]

    def append_message(self, message: Dict[str, Any]) -> None:
        """Append a message while enforcing the rolling history limit."""

        self.message_history.append(message)
        if len(self.message_history) > MAX_MESSAGE_HISTORY:
            # Keep the most recent entries only.
            self.message_history = self.message_history[-MAX_MESSAGE_HISTORY:]

    def touch(self) -> None:
        """Advance last_updated to now (UTC)."""

        self.last_updated = datetime.now(timezone.utc)
