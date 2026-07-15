from __future__ import annotations

from app.graph import nodes
from app.graph.edges import route_after_evidence
from app.graph.evidence import assess_search_outcome
from app.graph.graph import build_agent_graph
from app.graph.search_contracts import SearchOutcome, SearchSource, SearchStatus


def test_youth_age_hard_gate_excludes_ineligible_candidate():
    outcome = SearchOutcome(
        source=SearchSource.YOUTH_POLICY,
        status=SearchStatus.SUCCESS,
        items=[
            {
                "policy_id": "Y1",
                "title": "서울 청년 주거 지원",
                "min_age": 19,
                "max_age": 34,
                "age_restricted": True,
                "match_scope": "exact",
            }
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"age": 40, "region": "서울"},
        search_query="주거",
    )

    assert assessed.status is SearchStatus.NO_MATCH
    assert assessed.items == []
    assert report["rejection_reasons"] == {"age_mismatch": 1}
    assert assessed.applied_filters["age_gate"] == 40


def test_youth_age_gate_keeps_missing_age_evidence_as_unverified_reference():
    outcome = SearchOutcome(
        source=SearchSource.YOUTH_POLICY,
        status=SearchStatus.SUCCESS,
        items=[
            {
                "policy_id": "Y1",
                "title": "서울 청년 지원",
                "region": "서울",
                "age_restricted": True,
                "match_scope": "exact",
            }
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"age": 24, "region": "서울"},
        search_query="지원",
    )

    assert assessed.status is SearchStatus.SUCCESS
    assert [item["policy_id"] for item in assessed.items] == ["Y1"]
    assert assessed.items[0]["match_scope"] == "unknown"
    assert assessed.items[0]["evidence_status"] == "unverified"
    assert assessed.items[0]["unverified_reasons"] == ["age_unverified"]
    assert report["rejection_reasons"] == {}
    assert report["unverified_reasons"] == {"age_unverified": 1}


def test_youth_region_gate_overrides_contradictory_exact_label():
    outcome = SearchOutcome(
        source=SearchSource.YOUTH_POLICY,
        status=SearchStatus.SUCCESS,
        items=[
            {
                "policy_id": "Y1",
                "title": "부산 청년 지원",
                "region": "부산",
                "age_restricted": False,
                "match_scope": "exact",
            }
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "서울"},
        search_query="지원",
    )

    assert assessed.items == []
    assert report["rejection_reasons"] == {"region_mismatch": 1}


def test_evidence_gate_rejects_explicitly_expired_candidate():
    outcome = SearchOutcome(
        source=SearchSource.RECRUITMENT,
        status=SearchStatus.SUCCESS,
        items=[
            {
                "item_id": "E1",
                "item_type": "event",
                "title": "지난 채용행사",
                "region": "서울",
                "end_date": "2000-01-01",
            }
        ],
    )

    assessed, report = assess_search_outcome(outcome, profile={"region": "서울"}, search_query="채용")

    assert assessed.items == []
    assert report["rejection_reasons"] == {"closed": 1}


def test_hard_gate_no_match_does_not_rewrite_query():
    assert (
        route_after_evidence(
            {
                "search_outcome": {"status": "no_match", "items": []},
                "evidence_assessment": {"rejection_reasons": {"region_mismatch": 2}},
                "search_query": "데이터 분석",
                "query_rewrite_count": 0,
            }
        )
        == "direct_response"
    )


def test_partial_failure_without_candidates_retries_only_within_total_budget():
    base_state = {
        "search_outcome": {"status": "partial", "items": [], "retryable": True},
        "evidence_assessment": {"rejection_reasons": {"region_mismatch": 1}},
    }

    assert route_after_evidence({**base_state, "search_attempt_count": 1}) == "retrieve"
    assert route_after_evidence({**base_state, "search_attempt_count": 2}) == "direct_response"


def test_training_region_gate_excludes_mismatch_but_keeps_unverified_region():
    outcome = SearchOutcome(
        source=SearchSource.TRAINING,
        status=SearchStatus.SUCCESS,
        items=[
            {"course_id": "T1", "title": "서울 과정", "region": "서울 강남구"},
            {"course_id": "T2", "title": "온라인 과정", "region": "온라인"},
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "부산"},
        search_query="데이터 분석",
    )

    assert [item["course_id"] for item in assessed.items] == ["T2"]
    assert assessed.status is SearchStatus.SUCCESS
    assert assessed.items[0]["match_scope"] == "unknown"
    assert assessed.items[0]["evidence_status"] == "unverified"
    assert assessed.items[0]["unverified_reasons"] == ["region_unverified"]
    assert report["rejection_reasons"] == {"region_mismatch": 1}
    assert report["unverified_reasons"] == {"region_unverified": 1}


def test_training_region_gate_rejects_different_sigungu_in_same_sido():
    outcome = SearchOutcome(
        source=SearchSource.TRAINING,
        status=SearchStatus.SUCCESS,
        items=[
            {"course_id": "T1", "title": "강남 과정", "region": "서울 강남구"},
            {"course_id": "T2", "title": "노원 과정", "region": "서울 노원구"},
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "서울 강남구"},
        search_query="데이터 분석",
    )

    assert [item["course_id"] for item in assessed.items] == ["T1"]
    assert report["rejection_reasons"] == {"region_mismatch": 1}


def test_training_region_gate_keeps_sido_only_record_as_unverified_for_sigungu_request():
    outcome = SearchOutcome(
        source=SearchSource.TRAINING,
        status=SearchStatus.SUCCESS,
        items=[{"course_id": "T1", "title": "서울 과정", "region": "서울"}],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "서울 강남구"},
        search_query="데이터 분석",
    )

    assert [item["course_id"] for item in assessed.items] == ["T1"]
    assert assessed.status is SearchStatus.SUCCESS
    assert assessed.items[0]["match_scope"] == "unknown"
    assert assessed.items[0]["evidence_status"] == "unverified"
    assert report["rejection_reasons"] == {}
    assert report["unverified_reasons"] == {"region_unverified": 1}


def test_evidence_selection_deduplicates_titles_before_numbered_presentation():
    outcome = SearchOutcome(
        source=SearchSource.TRAINING,
        status=SearchStatus.SUCCESS,
        items=[
            {"course_id": "round-1", "title": "데이터 과정", "region": "서울"},
            {"course_id": "round-2", "title": "데이터 과정", "region": "서울"},
            {"course_id": "other", "title": "클라우드 과정", "region": "서울"},
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "서울"},
        search_query="데이터",
    )

    assert [item["course_id"] for item in assessed.items] == ["round-1", "other"]
    assert report["eligible_count"] == 3
    assert report["after_count"] == 2


def test_recruitment_gate_removes_unfiltered_company_records():
    outcome = SearchOutcome(
        source=SearchSource.RECRUITMENT,
        status=SearchStatus.SUCCESS,
        items=[
            {"item_id": "C1", "item_type": "company", "title": "무관한 기업소개"},
            {"item_id": "E1", "item_type": "event", "title": "서울 채용행사", "region": "서울"},
        ],
    )

    assessed, report = assess_search_outcome(
        outcome,
        profile={"region": "서울"},
        search_query="데이터 분석",
    )

    assert [item["item_id"] for item in assessed.items] == ["E1"]
    assert report["rejection_reasons"] == {"unsupported_recruitment_type": 1}
    assert assessed.applied_filters["allowed_item_types"] == ["event", "open_recruitment"]


def test_partial_failure_is_not_downgraded_to_no_match_when_known_items_are_rejected():
    outcome = SearchOutcome(
        source=SearchSource.RECRUITMENT,
        status=SearchStatus.PARTIAL,
        items=[{"item_id": "E1", "item_type": "event", "title": "부산 채용행사", "region": "부산"}],
        warnings=["공채속보 API 호출 실패"],
        retryable=True,
    )

    assessed, report = assess_search_outcome(outcome, profile={"region": "서울"}, search_query="채용")

    assert assessed.status is SearchStatus.PARTIAL
    assert assessed.retryable is True
    assert assessed.items == []
    assert report["rejection_reasons"] == {"region_mismatch": 1}


async def test_partial_failure_without_eligible_items_uses_fixed_abstention():
    result = await nodes.direct_response_node(
        {
            "request_kind": "recruitment",
            "response_mode": "recommend",
            "search_outcome": {"status": "partial", "items": []},
            "profile": {"region": "서울"},
        }
    )

    assert "전체 결과가 없다고 단정할 수 없" in result["final_response"]
    assert result["direct_response_reason"] == "partial"


def test_recruitment_event_keeps_missing_career_evidence_as_unverified_reference():
    outcome = SearchOutcome(
        source=SearchSource.RECRUITMENT,
        status=SearchStatus.SUCCESS,
        items=[
            {"item_id": "E1", "item_type": "event", "title": "서울 채용행사", "region": "서울"},
            {"item_id": "E2", "item_type": "event", "title": "서울 신입 채용행사", "region": "서울"},
        ],
        applied_filters={"career_level": "신입"},
    )

    assessed, report = assess_search_outcome(outcome, profile={"region": "서울"}, search_query="채용")

    assert [item["item_id"] for item in assessed.items] == ["E1", "E2"]
    assert assessed.items[0]["match_scope"] == "unknown"
    assert assessed.items[0]["evidence_status"] == "unverified"
    assert assessed.items[0]["unverified_reasons"] == ["career_unverified"]
    assert assessed.items[1]["match_scope"] == "exact"
    assert assessed.items[1]["evidence_status"] == "verified"
    assert report["rejection_reasons"] == {}
    assert report["unverified_reasons"] == {"career_unverified": 1}


async def test_graph_retries_retryable_source_failure_once_then_abstains(monkeypatch):
    class OfflineLLM:
        is_configured = False

    class UnavailableTrainingTool:
        def __init__(self):
            self.calls = 0

        async def execute(self, payload):  # noqa: ARG002
            self.calls += 1
            return [
                {
                    "course_id": "work24-training-guide",
                    "title": "검색 안내",
                    "fallback_reason": "고용24 훈련과정 API 호출 실패",
                }
            ]

    tool = UnavailableTrainingTool()
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "_training_tool", tool)

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        }
    )

    assert tool.calls == 2
    assert result["search_attempt_count"] == 2
    assert result["search_outcome"]["status"] == "unavailable"
    assert "검색 결과가 없다는 뜻은 아니" in result["final_response"]


async def test_graph_retry_and_rewrite_share_one_total_retrieve_budget(monkeypatch):
    class OfflineLLM:
        is_configured = False

    class MixedFailureTrainingTool:
        def __init__(self):
            self.calls = 0

        async def execute(self, payload):  # noqa: ARG002
            self.calls += 1
            if self.calls == 1:
                return [
                    {
                        "course_id": "work24-training-guide",
                        "title": "검색 안내",
                        "fallback_reason": "고용24 훈련과정 API 호출 실패",
                    }
                ]
            return []

    tool = MixedFailureTrainingTool()
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "_training_tool", tool)

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        }
    )

    assert tool.calls == 2
    assert result["search_attempt_count"] == 2
    assert result["query_rewrite_count"] == 0
    assert result["search_outcome"]["status"] == "no_match"


async def test_graph_rewrites_known_query_once_without_relaxing_region(monkeypatch):
    class OfflineLLM:
        is_configured = False

    class RewriteTrainingTool:
        def __init__(self):
            self.queries: list[tuple[str | None, str | None]] = []

        async def execute(self, payload):
            self.queries.append((payload.desired_job, payload.training_region))
            if payload.desired_job == "데이터 분석":
                return []
            return [
                {
                    "course_id": "T1",
                    "title": "데이터 실무 과정",
                    "region": "서울",
                    "detail_url": "https://www.work24.go.kr/course/T1",
                }
            ]

    tool = RewriteTrainingTool()
    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "_training_tool", tool)

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        }
    )

    assert tool.queries == [("데이터 분석", "서울"), ("데이터", "서울")]
    assert result["query_rewrite_count"] == 1
    assert result["search_attempt_count"] == 2
    assert result["search_outcome"]["status"] == "success"
    assert "카드 1건" in result["final_response"]
    assert "데이터 실무 과정" not in result["final_response"]
    assert "https://www.work24.go.kr/course/T1" not in result["final_response"]


async def test_answer_verification_loop_is_bounded_to_one_rebuild(monkeypatch):
    class OfflineLLM:
        is_configured = False

    class TrainingTool:
        async def execute(self, payload):  # noqa: ARG002
            return [
                {
                    "course_id": "T1",
                    "title": "데이터 분석 과정",
                    "region": "서울",
                    "detail_url": "https://www.work24.go.kr/course/T1",
                }
            ]

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "_training_tool", TrainingTool())
    monkeypatch.setattr(nodes, "validate_response_state", lambda state: ["forced_validation_failure"])

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        }
    )

    assert result["response_revision_count"] == 1
    assert result["response_validation_status"] == "failed"
    assert "안전하게 검증하지 못해" in result["final_response"]


async def test_direct_search_reply_retries_direct_path_without_entering_answer_builder(monkeypatch):
    class OfflineLLM:
        is_configured = False

    validation_calls = 0

    def fail_once(state):  # noqa: ARG001
        nonlocal validation_calls
        validation_calls += 1
        return ["forced_once"] if validation_calls == 1 else []

    async def forbidden_answer_builder(state):  # noqa: ARG001
        raise AssertionError("missing-slot reply must not enter build_answer")

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "validate_response_state", fail_once)
    monkeypatch.setattr(nodes, "response_node", forbidden_answer_builder)

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "국비과정 찾아줘",
            "profile": {},
        }
    )

    assert result["response_revision_count"] == 1
    assert result["response_validation_status"] == "passed"
    assert result["missing_slots"]
