from __future__ import annotations

from pydantic import BaseModel, Field


class PolicySearchInput(BaseModel):
    """정책 검색 Tool의 입력 스키마 (Agent가 호출하는 도구의 계약)."""

    region: str | None = None
    age: int | None = None
    employment_status: str | None = None
    graduation_status: str | None = None
    is_entrepreneur: bool | None = None
    has_registered_business: bool | None = None
    desired_job: str | None = None
    preferred_support_type: str | None = None
    interest_fields: list[str] = Field(default_factory=list)
    keywords: str = ""
    limit: int = 10


class YouthPolicySearchInput(BaseModel):
    """온통청년 청년정책 검색 Tool 입력 계약."""

    region: str | None = None
    age: int | None = None
    employment_status: str | None = None
    graduation_status: str | None = None
    support_types: list[str] = Field(default_factory=list)
    interest_fields: list[str] = Field(default_factory=list)
    keywords: str = ""
    page: int = 1
    page_size: int = 10


class YouthPolicyItem(BaseModel):
    """온통청년 또는 내부 fallback 청년정책 표준 출력."""

    source: str = "youthcenter"
    policy_id: str
    title: str
    organization: str | None = None
    region: str | None = None
    target_summary: str | None = None
    support_summary: str | None = None
    application_period: str | None = None
    application_method: str | None = None
    detail_url: str | None = None
    fallback_reason: str | None = None
    raw: dict = Field(default_factory=dict)


class TrainingCourseSearchInput(BaseModel):
    """고용24 국민내일배움카드 훈련과정 검색 Tool 입력 계약."""

    desired_job: str | None = None
    training_region: str | None = None
    training_region_code: str | None = None
    training_start_date_from: str | None = None
    training_start_date_to: str | None = None
    online_available: bool | None = None
    keywords: str = ""
    page: int = 1
    page_size: int = 10


class TrainingCourseItem(BaseModel):
    """고용24 훈련과정 표준 출력."""

    source: str = "work24_training"
    course_id: str
    course_round: str | None = None
    title: str
    institution: str | None = None
    region: str | None = None
    address: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    cost: str | None = None
    actual_cost: str | None = None
    ncs_code: str | None = None
    target: str | None = None
    capacity: str | None = None
    contact: str | None = None
    detail_url: str | None = None
    institution_url: str | None = None
    fallback_reason: str | None = None
    raw: dict = Field(default_factory=dict)


class RecruitmentInfoSearchInput(BaseModel):
    """고용24 채용 보조 정보 검색 Tool 입력 계약."""

    desired_job: str | None = None
    occupation_codes: list[str] = Field(default_factory=list)
    preferred_work_region: str | None = None
    employment_type: str | None = None
    career_level: str | None = None
    education_level: str | None = None
    include_events: bool = True
    include_open_recruitments: bool = True
    include_company_info: bool = True
    keywords: str = ""
    page: int = 1
    page_size: int = 10


class RecruitmentInfoItem(BaseModel):
    """고용24 채용행사/공채속보/기업정보 또는 탐색 가이드 표준 출력."""

    source: str = "work24_recruitment"
    item_id: str
    item_type: str  # event | open_recruitment | company | guide
    title: str
    company: str | None = None
    region: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None
    detail_url: str | None = None
    fallback_reason: str | None = None
    raw: dict = Field(default_factory=dict)
