from __future__ import annotations

import asyncio
from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.graph import nodes
from app.graph.search_contracts import (
    SearchOutcome,
    SearchSource,
    SearchStatus,
    outcome_from_raw,
)
from app.tools.executor import TrainingCourseSearchTool, YouthPolicySearchTool
from app.tools.schemas import (
    TrainingCourseItem,
    TrainingCourseSearchInput,
    YouthPolicyItem,
    YouthPolicySearchInput,
)


def test_outcome_serializes_as_json_compatible_status_contract():
    outcome = SearchOutcome(
        source=SearchSource.YOUTH_POLICY,
        status=SearchStatus.SUCCESS,
        items=[{"policy_id": "Y1", "title": "청년 정책"}],
    )

    assert outcome.model_dump(mode="json") == {
        "source": "youth_policy",
        "status": "success",
        "items": [{"policy_id": "Y1", "title": "청년 정책"}],
        "requested_filters": {},
        "applied_filters": {},
        "warnings": [],
        "retryable": False,
    }


def test_outcome_from_raw_accepts_pydantic_items_and_preserves_filters():
    outcome = outcome_from_raw(
        "training",
        [TrainingCourseItem(course_id="T1", title="데이터 분석")],
        requested_filters={"training_region": "서울"},
        applied_filters={"training_region_code": "11"},
    )

    assert outcome.status is SearchStatus.SUCCESS
    assert outcome.items[0]["course_id"] == "T1"
    assert outcome.requested_filters == {"training_region": "서울"}
    assert outcome.applied_filters == {"training_region_code": "11"}


def test_outcome_drops_raw_upstream_payload_before_graph_state():
    outcome = outcome_from_raw(
        SearchSource.TRAINING,
        [
            {
                "course_id": "T1",
                "title": "데이터 과정",
                "raw": {"unapproved": "value"},
                "raw_payload": {"large": "blob"},
            }
        ],
    )

    assert outcome.items == [{"course_id": "T1", "title": "데이터 과정"}]


def test_tool_input_rejects_removed_or_unknown_filter():
    with pytest.raises(ValidationError):
        TrainingCourseSearchInput(desired_job="데이터 분석", online_available=True)


def test_empty_successful_search_is_no_match_not_unavailable():
    outcome = outcome_from_raw(SearchSource.RECRUITMENT, [])

    assert outcome.status is SearchStatus.NO_MATCH
    assert outcome.items == []
    assert outcome.retryable is False


@pytest.mark.parametrize(
    ("reason", "retryable"),
    [
        ("EMPLOYMENT24_TRAINING_API_KEY 미설정", False),
        ("고용24 훈련과정 API 호출 실패", True),
        ("고용24 훈련과정 응답 파싱 실패", True),
        ("온통청년 API가 일시적으로 응답하지 않았어요.", True),
    ],
)
def test_unavailable_guide_is_warning_not_candidate(reason: str, retryable: bool):
    outcome = outcome_from_raw(
        SearchSource.TRAINING,
        [
            TrainingCourseItem(
                course_id="work24-training-guide",
                title="검색 안내",
                fallback_reason=reason,
            )
        ],
    )

    assert outcome.status is SearchStatus.UNAVAILABLE
    assert outcome.items == []
    assert outcome.warnings == [reason]
    assert outcome.retryable is retryable


def test_no_match_guide_is_distinct_from_source_failure():
    reason = "고용24 훈련과정 검색 결과 없음. 공식 화면에서 다시 확인해주세요."
    outcome = outcome_from_raw(
        SearchSource.TRAINING,
        [
            TrainingCourseItem(
                course_id="work24-training-guide",
                title="검색 안내",
                fallback_reason=reason,
            )
        ],
    )

    assert outcome.status is SearchStatus.NO_MATCH
    assert outcome.items == []
    assert outcome.warnings == [reason]
    assert outcome.retryable is False


def test_actual_items_plus_guide_are_partial_and_guide_is_removed():
    outcome = outcome_from_raw(
        SearchSource.YOUTH_POLICY,
        [
            YouthPolicyItem(policy_id="Y1", title="실제 정책"),
            YouthPolicyItem(
                policy_id="youthcenter-guide",
                title="조회 안내",
                fallback_reason="온통청년 API가 일시적으로 응답하지 않았어요.",
            ),
        ],
    )

    assert outcome.status is SearchStatus.PARTIAL
    assert [item["policy_id"] for item in outcome.items] == ["Y1"]
    assert outcome.retryable is True


async def test_execute_keeps_legacy_raw_list_while_execute_outcome_removes_guide():
    guide = YouthPolicyItem(
        policy_id="youthcenter-guide",
        title="조회 안내",
        fallback_reason="온통청년 API 키가 설정되지 않아 현재 조회할 수 없어요.",
    )

    class Repository:
        async def search(self, payload):
            del payload
            return [guide]

    tool = YouthPolicySearchTool(Repository())
    payload = YouthPolicySearchInput(region="서울", page=3)

    assert await tool.execute(payload) == [guide]
    outcome = await tool.execute_outcome(payload)
    assert outcome.status is SearchStatus.UNAVAILABLE
    assert outcome.items == []
    assert outcome.requested_filters == {"region": "서울"}


async def test_execute_outcome_exposes_tool_exception_as_unavailable():
    class Repository:
        async def search(self, payload):
            del payload
            raise RuntimeError("secret upstream detail")

    tool = TrainingCourseSearchTool(Repository())
    payload = TrainingCourseSearchInput(desired_job="데이터 분석", training_region="서울")

    assert await tool.execute(payload) == []
    outcome = await tool.execute_outcome(payload)
    assert outcome.status is SearchStatus.UNAVAILABLE
    assert outcome.retryable is True
    assert outcome.items == []
    assert "secret upstream detail" not in outcome.warnings[0]
    assert outcome.requested_filters == {
        "desired_job": "데이터 분석",
        "training_region": "서울",
    }


async def test_graph_search_boundary_turns_source_timeout_into_retryable_unavailable(monkeypatch):
    class SlowTool:
        async def execute(self, payload):  # noqa: ARG002
            await asyncio.sleep(1)
            return []

    monkeypatch.setattr(nodes, "get_settings", lambda: SimpleNamespace(source_search_timeout_seconds=0.001))

    outcome = await nodes._execute_search_outcome(
        SlowTool(),
        TrainingCourseSearchInput(desired_job="데이터 분석"),
        source=SearchSource.TRAINING,
        applied_filters={"keyword": "데이터 분석"},
    )

    assert outcome.status is SearchStatus.UNAVAILABLE
    assert outcome.retryable is True
    assert outcome.items == []
    assert outcome.applied_filters == {"keyword": "데이터 분석"}
