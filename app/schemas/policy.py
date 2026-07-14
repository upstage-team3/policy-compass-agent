from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class PolicyItem(BaseModel):
    """정책/지원사업 데이터 모델 (외부 API 응답을 정규화한 형태)."""

    id: str
    title: str
    agency: str
    category: str  # "구직창업" | "창업" | "경영/기술" 등
    target_description: str
    region: list[str] = Field(default_factory=list)
    min_age: int | None = None
    max_age: int | None = None
    target_employment_status: list[str] = Field(default_factory=list)
    target_entrepreneur: bool | None = None
    requires_business_registration: bool | None = None
    apply_start: str | None = None
    apply_end: str | None = None
    apply_method: str
    support_content: str
    source_url: str
    match_scope: Literal["exact", "nationwide", "nearby", "unknown"] = "unknown"
    distance_km: float | None = None


class PolicySearchResult(BaseModel):
    """자격 적합도 스코어링이 완료된 추천 결과."""

    policy: PolicyItem
    match_score: float
    match_reasons: list[str]
    follow_up_checks: list[str]
    deadline_status: str  # "모집중" | "마감임박" | "마감" | "상시"


class PolicySearchRequest(BaseModel):
    query: str
    top_k: int = 5
