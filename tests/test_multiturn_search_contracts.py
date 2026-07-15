from __future__ import annotations

import json

from app.graph import nodes
from app.graph.search_contracts import SearchOutcome, SearchSource, SearchStatus


class StubLLM:
    is_configured = True

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)

    async def complete(self, messages, **kwargs):
        del messages, kwargs
        return self.responses.pop(0)


class OfflineLLM:
    is_configured = False


class CapturingRecruitmentTool:
    def __init__(self) -> None:
        self.payload = None

    async def execute_outcome(self, payload):
        self.payload = payload
        return SearchOutcome(
            source=SearchSource.RECRUITMENT,
            status=SearchStatus.NO_MATCH,
        )


async def test_new_recruitment_search_replaces_pending_policy_without_filter_contamination(monkeypatch):
    """A new resource request must not inherit the previous policy task's topic filters."""

    message = "아니 지금 채용공고가 있는 회사 있어?"
    profile = {
        "region": "서울",
        "age": 24,
        "policy_topic": "금융·복지·문화",
        "preferred_support_type": "청년수당",
        "request_kind": "youth_policy",
    }
    pending = {
        "original_request": "서울 청년수당 조건을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "청년수당",
        "required_slots": ["employment_status"],
    }
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM('{"action":"SEARCH","response_mode":"recommend","request_kind":"recruitment","search_query":null}'),
    )

    routed = await nodes.router_node(
        {
            "user_input": message,
            "profile": profile,
            "pending_request": pending,
        }
    )

    assert routed["action"] == "SEARCH"
    assert routed["request_kind"] == "recruitment"
    assert routed["pending_action"] == "REPLACE"
    assert routed["pending_request"] == {}

    tool = CapturingRecruitmentTool()
    monkeypatch.setattr(nodes, "_recruitment_tool", tool)
    searched = await nodes.policy_search_node(
        {
            "user_input": message,
            "profile": profile,
            **routed,
        }
    )

    assert tool.payload is not None
    assert tool.payload.desired_job is None
    assert tool.payload.keywords == ""
    serialized_input = json.dumps(tool.payload.model_dump(mode="json"), ensure_ascii=False)
    applied_filters = searched["search_outcome"]["applied_filters"]
    assert "금융·복지·문화" not in serialized_input
    assert "청년수당" not in serialized_input
    assert "policy_topic" not in applied_filters
    assert "preferred_support_type" not in applied_filters


async def test_region_unrestricted_followup_keeps_recruitment_search_without_work_region_filter(monkeypatch):
    """ANY is a turn-level filter mode; it must not erase the saved residence."""

    message = "지역 상관없이 조회해줘"
    profile = {
        "region": "서울",
        "desired_job": "데이터 분석",
        "request_kind": "recruitment",
    }
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM(
            '{"action":"SEARCH","response_mode":"recommend","request_kind":"recruitment","search_query":"데이터 분석"}'
        ),
    )

    routed = await nodes.router_node(
        {
            "user_input": message,
            "profile": profile,
            "request_kind": "recruitment",
            "search_query": "데이터 분석",
        }
    )

    assert routed["action"] == "SEARCH"
    assert routed["request_kind"] == "recruitment"

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    extracted = await nodes.profile_extractor_node(
        {
            "user_input": message,
            "profile": profile,
            **routed,
        }
    )
    assert extracted["profile"]["region"] == "서울"

    tool = CapturingRecruitmentTool()
    monkeypatch.setattr(nodes, "_recruitment_tool", tool)
    searched = await nodes.policy_search_node(
        {
            "user_input": message,
            "profile": extracted["profile"],
            **routed,
        }
    )

    assert tool.payload is not None
    assert tool.payload.preferred_work_region is None
    assert "work_region" not in searched["search_outcome"]["applied_filters"]


async def test_region_unrestricted_uses_last_no_match_plan_without_candidate_snapshot(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())

    routed = await nodes.router_node(
        {
            "user_input": "지역 상관없이 조회해줘",
            "profile": {"region": "서울"},
            "last_presented_candidates": [],
            "last_search_plan": {
                "request_kind": "recruitment",
                "response_mode": "recommend",
                "search_query": "데이터 분석",
                "effective_filters": {"work_region": "서울", "region_mode": "specific"},
                "source_status": "no_match",
            },
        }
    )

    assert routed["action"] == "SEARCH"
    assert routed["request_kind"] == "recruitment"
    assert routed["search_query"] == "데이터 분석"
    assert routed["turn_relation"] == "REFINE"
    assert routed["region_filter_mode"] == "any"


async def test_explicit_work24_recruitment_correction_overrides_stale_policy_profile(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())

    result = await nodes.router_node(
        {
            "user_input": "청년 지원 정책 분야가 아니라 취업 관련해서 고용24 공고 정보를 원하는거야",
            "profile": {
                "region": "서울",
                "policy_topic": "금융·복지·문화",
                "preferred_support_type": "청년수당",
                "request_kind": "youth_policy",
            },
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "recruitment"
    assert result["response_mode"] == "recommend"
    assert result["search_query"] is None


async def test_region_slot_answer_with_done_word_resumes_pending_instead_of_cancelling(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())

    result = await nodes.router_node(
        {
            "user_input": "서울이면 됐어",
            "profile": {"desired_job": "데이터 분석"},
            "pending_request": {
                "original_request": "데이터 분석 채용공고 찾아줘",
                "request_kind": "recruitment",
                "response_mode": "recommend",
                "search_query": "데이터 분석",
                "required_slots": ["work_region"],
            },
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "recruitment"
    assert result["resumed_pending"] is True
    assert result["pending_action"] == "RESUME"
