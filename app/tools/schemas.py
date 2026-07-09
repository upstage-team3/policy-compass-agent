from __future__ import annotations

from pydantic import BaseModel, Field


class PolicySearchInput(BaseModel):
    """정책 검색 Tool의 입력 스키마 (Agent가 호출하는 도구의 계약)."""

    region: str | None = None
    employment_status: str | None = None
    is_entrepreneur: bool | None = None
    has_registered_business: bool | None = None
    interest_fields: list[str] = Field(default_factory=list)
    keywords: str = ""
    limit: int = 10
