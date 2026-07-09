from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class UserProfile(BaseModel):
    age: int | None = None
    employment_status: (
        Literal["unemployed_seeking_job", "employed", "student", "not_specified"] | None
    ) = None
    graduation_status: (
        Literal["enrolled", "expected_graduate", "graduated_within_2y", "graduated_over_2y"] | None
    ) = None
    region: str | None = None
    is_entrepreneur: bool | None = None
    has_registered_business: bool | None = None
    interest_fields: list[str] = Field(default_factory=list)


class ChatRequest(BaseModel):
    session_id: str
    message: str


class ChatTurnResponse(BaseModel):
    session_id: str
    intent: str
    reply: str
    profile: UserProfile
    missing_slots: list[str] = Field(default_factory=list)
    recommendations: list[dict] = Field(default_factory=list)
