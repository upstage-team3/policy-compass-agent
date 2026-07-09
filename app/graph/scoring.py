"""Eligibility Scorer: 사용자 조건과 정책 조건의 일치도를 계산하는 규칙 기반 로직.

LLM에 맡기지 않고 결정론적 규칙으로 계산하여, 동일 입력에 대해 항상 동일한
점수/근거가 산출되도록 한다 (근거 기반 신뢰성 있는 답변의 핵심 요소).
"""

from __future__ import annotations

from datetime import date
from typing import Any


def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    try:
        return date.fromisoformat(value)
    except ValueError:
        return None


def deadline_status(apply_end: str | None, *, today: date | None = None) -> str:
    today = today or date.today()
    end = _parse_date(apply_end)
    if end is None:
        return "상시"
    if end < today:
        return "마감"
    if (end - today).days <= 14:
        return "마감임박"
    return "모집중"


def score_policy(
    profile: dict[str, Any], policy: dict[str, Any], *, today: date | None = None
) -> dict[str, Any]:
    """사용자 조건(profile)과 정책(policy)의 적합도를 0.0~1.0 사이 점수로 계산한다."""

    score = 0.0
    reasons: list[str] = []
    follow_ups: list[str] = []

    region = profile.get("region")
    policy_regions = policy.get("region") or ["전국"]
    if "전국" in policy_regions:
        score += 0.2
        reasons.append("전국 대상 사업이라 거주 지역과 무관하게 신청할 수 있어요.")
    elif region and region in policy_regions:
        score += 0.3
        reasons.append(f"{region} 거주자를 대상으로 하는 사업이에요.")
    elif region:
        score -= 0.3
        follow_ups.append("사업 공고에 명시된 지역 조건을 다시 확인해보세요.")
    else:
        follow_ups.append("거주 지역 조건을 확인해보세요.")

    age = profile.get("age")
    min_age, max_age = policy.get("min_age"), policy.get("max_age")
    if age is not None and (min_age is not None or max_age is not None):
        if (min_age is None or age >= min_age) and (max_age is None or age <= max_age):
            score += 0.2
            reasons.append("연령 조건을 충족해요.")
        else:
            score -= 0.3
            follow_ups.append("연령 조건을 다시 확인해보세요.")
    elif min_age is not None or max_age is not None:
        follow_ups.append("연령 조건을 확인해보세요.")

    employment_status = profile.get("employment_status")
    target_statuses = policy.get("target_employment_status") or []
    if target_statuses:
        if employment_status in target_statuses:
            score += 0.2
            reasons.append("현재 상태(취업 준비/재직 등)와 지원 대상이 일치해요.")
        else:
            score -= 0.2
            follow_ups.append("취업/재직 상태 조건을 다시 확인해보세요.")

    target_entrepreneur = policy.get("target_entrepreneur")
    if target_entrepreneur is not None:
        is_entrepreneur = profile.get("is_entrepreneur")
        if is_entrepreneur is not None and is_entrepreneur == target_entrepreneur:
            score += 0.15
            reasons.append("창업(예정) 여부 조건과 일치해요.")
        else:
            follow_ups.append("창업(예정) 여부 조건을 확인해보세요.")

    requires_registration = policy.get("requires_business_registration")
    if requires_registration is not None:
        has_registered = profile.get("has_registered_business")
        if has_registered is not None and has_registered == requires_registration:
            score += 0.15
            reasons.append("사업자 등록 여부 조건과 일치해요.")
        else:
            follow_ups.append("사업자 등록 여부 조건을 확인해보세요.")

    interest_fields = set(profile.get("interest_fields") or [])
    if interest_fields:
        haystack = f"{policy.get('category', '')} {policy.get('support_content', '')} {policy.get('title', '')}"
        if any(field in haystack for field in interest_fields):
            score += 0.15
            reasons.append("관심 분야와 관련된 사업이에요.")

    status = deadline_status(policy.get("apply_end"), today=today)
    if status == "마감":
        score *= 0.3
        follow_ups.append("모집이 마감되었을 가능성이 있어요. 다음 회차 공고 여부를 확인해보세요.")
    elif status == "마감임박":
        follow_ups.append("마감이 임박했을 수 있어요. 신청 기간을 서둘러 확인해보세요.")

    score = max(0.0, min(1.0, round(score, 2)))
    if not reasons:
        reasons.append("입력하신 조건과 대략적으로 관련이 있는 사업이에요. 상세 조건은 공고문에서 확인해주세요.")

    return {
        "policy": policy,
        "match_score": score,
        "match_reasons": reasons,
        "follow_up_checks": follow_ups,
        "deadline_status": status,
    }
