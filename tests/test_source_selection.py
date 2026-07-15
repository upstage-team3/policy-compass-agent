from __future__ import annotations

import pytest

from app.graph.fallbacks import (
    is_pending_cancel,
    pending_answer_fills_required_slot,
    routing_plan,
    source_selection_plan,
)
from app.graph.profile_contracts import requested_profile_clears


@pytest.mark.parametrize(
    ("message", "primary_source", "resource_type", "topic"),
    [
        (
            "청년 직업훈련 정책 찾아줘",
            "youth_policy",
            "policy",
            "교육·직업·훈련",
        ),
        (
            "청년 채용지원 정책 찾아줘",
            "youth_policy",
            "policy",
            "일자리",
        ),
        (
            "서울 데이터 분석 국비과정 찾아줘",
            "training",
            "training_course",
            "교육·직업·훈련",
        ),
        (
            "서울에서 지금 지원할 수 있는 회사 채용공고 찾아줘",
            "recruitment",
            "recruitment_listing",
            "일자리",
        ),
    ],
)
def test_resource_type_selects_policy_course_or_recruitment_source(
    message: str,
    primary_source: str,
    resource_type: str,
    topic: str,
) -> None:
    plan = source_selection_plan(message)

    assert plan["primary_source"] == primary_source
    assert plan["resource_type"] == resource_type
    assert plan["topic"] == topic
    assert routing_plan(message)["request_kind"] == primary_source


@pytest.mark.parametrize(
    ("message", "primary_source", "resource_type"),
    [
        ("온통청년에서 직업훈련 정책 찾아줘", "youth_policy", "policy"),
        ("온통청년 채용 지원 정책 보여줘", "youth_policy", "policy"),
        ("고용24에서 데이터 분석 훈련과정 찾아줘", "training", "training_course"),
        ("고용24 채용공고 조회해줘", "recruitment", "recruitment_listing"),
    ],
)
def test_explicit_provider_is_honored_before_overlapping_topic_markers(
    message: str,
    primary_source: str,
    resource_type: str,
) -> None:
    plan = source_selection_plan(message)

    assert plan["primary_source"] == primary_source
    assert plan["resource_type"] == resource_type
    assert routing_plan(message)["request_kind"] == primary_source


def test_training_card_eligibility_is_policy_not_course_listing() -> None:
    plan = source_selection_plan("국민내일배움카드 지원 조건을 알려줘")

    assert plan["primary_source"] == "youth_policy"
    assert plan["resource_type"] == "policy"


def test_named_training_card_does_not_hide_explicit_course_discovery() -> None:
    plan = source_selection_plan("국민내일배움카드로 들을 실제 데이터 과정을 찾아줘")

    assert plan["primary_source"] == "training"
    assert plan["resource_type"] == "training_course"


@pytest.mark.parametrize(
    ("message", "primary_source", "companion_source", "topic"),
    [
        (
            "청년 직업훈련 지원 정책하고 실제 데이터 과정을 둘 다 찾아줘",
            "youth_policy",
            "training",
            "교육·직업·훈련",
        ),
        (
            "청년 취업지원 정책과 현재 채용공고를 같이 보여줘",
            "youth_policy",
            "recruitment",
            "일자리",
        ),
    ],
)
def test_explicit_mixed_request_keeps_policy_primary_and_exposes_companion_source(
    message: str,
    primary_source: str,
    companion_source: str,
    topic: str,
) -> None:
    plan = source_selection_plan(message)

    assert plan["primary_source"] == primary_source
    assert plan["resource_type"] == "mixed"
    assert plan["topic"] == topic
    assert companion_source in plan["companion_sources"]
    # Phase 1 invokes only the primary source; companion_sources is a CTA/future
    # multi-source execution contract rather than an implicit second Tool call.
    assert routing_plan(message)["request_kind"] == primary_source


def test_region_scope_override_is_not_mistaken_for_profile_deletion_or_cancellation() -> None:
    message = "지역 상관없이 조회해줘"

    assert requested_profile_clears(message) == set()
    assert is_pending_cancel(message) is False


def test_region_slot_answer_containing_done_is_not_mistaken_for_pending_cancellation() -> None:
    message = "서울이면 됐어"
    pending = {
        "request_kind": "training",
        "response_mode": "recommend",
        "required_slots": ["training_region"],
    }

    assert is_pending_cancel(message) is False
    assert pending_answer_fills_required_slot(message, pending) is True


def test_explicit_pending_cancellation_remains_supported() -> None:
    assert is_pending_cancel("이번 검색은 그만할게") is True
