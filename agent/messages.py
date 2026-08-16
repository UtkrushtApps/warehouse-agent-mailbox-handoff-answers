from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


class AgentMessage(BaseModel):
    """Message contract shared by the dispatcher, robot, and file inbox."""

    model_config = ConfigDict(extra="forbid")

    sender: str = Field(min_length=1)
    receiver: str = Field(min_length=1)
    performative: Literal["request", "inform", "refuse"]
    conversation_id: str = Field(min_length=1)
    payload: dict[str, Any]
