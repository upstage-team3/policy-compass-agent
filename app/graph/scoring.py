"""Eligibility Scorer: 사용자 조건과 정책 조건의 일치도를 계산하는 규칙 기반 로직.

LLM에 맡기지 않고 결정론적 규칙으로 계산하여, 동일 입력에 대해 항상 동일한
점수/근거가 산출되도록 한다 (근거 기반 신뢰성 있는 답변의 핵심 요소).
"""

from __future__ import annotations

from datetime import date
from typing import Any

from app.core.regions import region_match_scope
from app.core.relevance import policy_matches_interest

_REGION_WEIGHT = 0.25
_AGE_WEIGHT = 0.10
_EMPLOYMENT_WEIGHT = 0.10
_ENTREPRENEUR_WEIGHT = 0.15
_REGISTRATION_WEIGHT = 0.10
_INTEREST_WEIGHT = 0.20
_DEADLINE_WEIGHT = 0.10
_TOTAL_WEIGHT = sum(
    (
        _REGION_WEIGHT,
        _AGE_WEIGHT,
        _EMPLOYMENT_WEIGHT,
        _ENTREPRENEUR_WEIGHT,
        _REGISTRATION_WEIGHT,
        _INTEREST_WEIGHT,
        _DEADLINE_WEIGHT,
    )
)


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


def score_policy(profile: dict[str, Any], policy: dict[str, Any], *, today: date | None = None) -> dict[str, Any]:
    """전체 평가 기준 대비 확인된 일치 근거로 추천 순위용 적합도를 계산한다.

    점수는 신청 가능성이 아니다. 명백한 지역·자격·마감 불일치는 하드 제외하고,
    값이 없는 조건은 임의로 통과시키지 않는다. match_score는 전체 가중치 대비
    확인된 일치 가중치이고, evidence_coverage는 실제 비교할 수 있었던 가중치 비율이다.
    """

    matched_weight = 0.0
    evaluated_weight = 0.0
    reasons: list[str] = []
    follow_ups: list[str] = []
    hard_mismatches: list[str] = []
    is_recommendable = True

    region = profile.get("region")
    policy_regions = policy.get("region") or []
    declared_scope = policy.get("match_scope")
    calculated_scope = region_match_scope(region, policy_regions)
    if declared_scope == "nearby":
        recommendation_scope = "nearby_reference"
        is_recommendable = False
        distance = policy.get("distance_km")
        distance_text = f" 약 {distance:g}km" if isinstance(distance, (int, float)) else ""
        reasons.append(f"요청 지역에서{distance_text} 떨어진 지역의 참고 결과예요.")
        follow_ups.append("가까운 지역 정책이라도 거주 요건 때문에 신청하지 못할 수 있어요.")
    elif calculated_scope == "nationwide":
        recommendation_scope = "nationwide"
        evaluated_weight += _REGION_WEIGHT
        matched_weight += _REGION_WEIGHT * 0.9
        reasons.append("전국 대상 사업이라 거주 지역과 무관하게 신청할 수 있어요.")
    elif calculated_scope == "exact":
        recommendation_scope = "exact"
        evaluated_weight += _REGION_WEIGHT
        matched_weight += _REGION_WEIGHT
        reasons.append(f"{region} 거주자를 대상으로 하는 사업이에요.")
    elif calculated_scope == "mismatch":
        recommendation_scope = "excluded"
        evaluated_weight += _REGION_WEIGHT
        is_recommendable = False
        hard_mismatches.append("요청 지역과 사업 대상 지역이 일치하지 않아요.")
        follow_ups.append("사업 공고의 거주 지역 조건을 다시 확인해보세요.")
    else:
        recommendation_scope = "excluded"
        is_recommendable = False
        hard_mismatches.append("사업 대상 지역을 확인할 수 없어요.")
        follow_ups.append("공고 원문에서 대상 지역을 확인해보세요.")

    age = profile.get("age")
    min_age, max_age = policy.get("min_age"), policy.get("max_age")
    if age is not None and (min_age is not None or max_age is not None):
        evaluated_weight += _AGE_WEIGHT
        if (min_age is None or age >= min_age) and (max_age is None or age <= max_age):
            matched_weight += _AGE_WEIGHT
            reasons.append("연령 조건을 충족해요.")
        else:
            is_recommendable = False
            hard_mismatches.append("연령 조건과 일치하지 않아요.")
            follow_ups.append("연령 조건을 다시 확인해보세요.")
    elif min_age is not None or max_age is not None:
        follow_ups.append("연령 조건을 확인해보세요.")

    employment_status = profile.get("employment_status")
    target_statuses = policy.get("target_employment_status") or []
    if target_statuses:
        if employment_status is None:
            follow_ups.append("취업/재직 상태 조건을 확인해보세요.")
        elif employment_status in target_statuses:
            evaluated_weight += _EMPLOYMENT_WEIGHT
            matched_weight += _EMPLOYMENT_WEIGHT
            reasons.append("현재 상태(취업 준비/재직 등)와 지원 대상이 일치해요.")
        else:
            evaluated_weight += _EMPLOYMENT_WEIGHT
            is_recommendable = False
            hard_mismatches.append("취업/재직 상태 조건과 일치하지 않아요.")
            follow_ups.append("취업/재직 상태 조건을 다시 확인해보세요.")

    target_entrepreneur = policy.get("target_entrepreneur")
    if target_entrepreneur is not None:
        is_entrepreneur = profile.get("is_entrepreneur")
        if is_entrepreneur is None:
            follow_ups.append("창업(예정) 여부 조건을 확인해보세요.")
        elif is_entrepreneur == target_entrepreneur:
            evaluated_weight += _ENTREPRENEUR_WEIGHT
            matched_weight += _ENTREPRENEUR_WEIGHT
            reasons.append("창업(예정) 여부 조건과 일치해요.")
        else:
            evaluated_weight += _ENTREPRENEUR_WEIGHT
            is_recommendable = False
            hard_mismatches.append("창업(예정) 여부 조건과 일치하지 않아요.")
            follow_ups.append("창업(예정) 여부 조건을 확인해보세요.")

    requires_registration = policy.get("requires_business_registration")
    if requires_registration is not None:
        has_registered = profile.get("has_registered_business")
        if has_registered is None:
            follow_ups.append("사업자 등록 여부 조건을 확인해보세요.")
        elif has_registered == requires_registration:
            evaluated_weight += _REGISTRATION_WEIGHT
            matched_weight += _REGISTRATION_WEIGHT
            reasons.append("사업자 등록 여부 조건과 일치해요.")
        else:
            evaluated_weight += _REGISTRATION_WEIGHT
            is_recommendable = False
            hard_mismatches.append("사업자 등록 여부 조건과 일치하지 않아요.")
            follow_ups.append("사업자 등록 여부 조건을 확인해보세요.")

    interest_fields = set(profile.get("interest_fields") or [])
    if interest_fields:
        evaluated_weight += _INTEREST_WEIGHT
        if policy_matches_interest(
            list(interest_fields),
            title=policy.get("title", ""),
            category=policy.get("category", ""),
            support_content=policy.get("support_content", ""),
        ):
            matched_weight += _INTEREST_WEIGHT
            reasons.append("관심 분야와 관련된 사업이에요.")

    status = deadline_status(policy.get("apply_end"), today=today)
    if status == "마감":
        evaluated_weight += _DEADLINE_WEIGHT
        is_recommendable = False
        hard_mismatches.append("현재 모집이 마감된 공고예요.")
        follow_ups.append("모집이 마감된 공고예요. 다음 회차 공고 여부를 확인해보세요.")
    elif status == "마감임박":
        evaluated_weight += _DEADLINE_WEIGHT
        matched_weight += _DEADLINE_WEIGHT
        follow_ups.append("마감이 임박했을 수 있어요. 신청 기간을 서둘러 확인해보세요.")
    elif policy.get("apply_end"):
        evaluated_weight += _DEADLINE_WEIGHT
        matched_weight += _DEADLINE_WEIGHT

    score = round(matched_weight / _TOTAL_WEIGHT, 2) if is_recommendable else 0.0
    evidence_coverage = round(min(evaluated_weight / _TOTAL_WEIGHT, 1.0), 2)
    if not reasons:
        reasons.append("구조화된 조건만으로는 일치 근거가 부족해요.")

    return {
        "policy": policy,
        "match_score": score,
        "evidence_coverage": evidence_coverage,
        "match_reasons": reasons,
        "follow_up_checks": follow_ups,
        "hard_mismatches": hard_mismatches,
        "is_recommendable": is_recommendable,
        "recommendation_scope": recommendation_scope,
        "deadline_status": status,
    }
