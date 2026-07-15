from __future__ import annotations

from datetime import date

import pytest

from app.core.dates import deadline_status
from app.graph import edges, nodes
from app.graph.graph import build_agent_graph
from app.graph.response_composer import (
    clarification_template,
    clean_response_text,
    compose_card_summary_reply,
    compose_search_status_reply,
)
from app.graph.search_contracts import SearchStatus


class StubLLM:
    is_configured = True

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.responses.pop(0)


def test_graph_registers_only_eight_meaningful_nodes():
    graph_nodes = set(build_agent_graph().get_graph().nodes) - {"__start__", "__end__"}

    assert graph_nodes == {
        "prepare_request",
        "direct_response",
        "retrieve",
        "assess_evidence",
        "rewrite_query",
        "build_answer",
        "verify_answer",
        "finalize",
    }


def test_heuristic_route_recommend():
    assert nodes._heuristic_route("취업 준비 중인데 받을 수 있는 지원금 있어?") == "RECOMMEND"


def test_heuristic_route_eligibility_check():
    assert nodes._heuristic_route("이 사업 자격 되나요?") == "ELIGIBILITY_CHECK"


def test_heuristic_route_out_of_scope():
    assert nodes._heuristic_route("세무 상담 좀 해줄 수 있어?") == "OUT_OF_SCOPE"
    assert nodes._heuristic_route("청년 전세대출 상담 정책을 찾아줘") == "RECOMMEND"


def test_heuristic_route_general():
    assert nodes._heuristic_route("안녕하세요") == "GENERAL"
    assert nodes._heuristic_route("왜 나한테 우울증 상담을 받아보라고 했어?") == "GENERAL"
    assert nodes._heuristic_route("재밌는 영화 추천해줘") == "GENERAL"
    assert nodes._heuristic_route("삶이 뭐야?") == "GENERAL"
    assert nodes._heuristic_route("요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어") == "GENERAL"


async def test_fallback_router_keeps_specific_youth_policy_query():
    result = await nodes.router_node(
        {
            "user_input": "청년 월세 지원 정책은 없어?",
            "profile": {"region": "경기", "age": 24},
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "월세"


async def test_fallback_router_uses_official_search_for_named_policy_explanation(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())

    result = await nodes.router_node({"user_input": "청년도약계좌의 현재 조건을 설명해줘"})

    assert result["action"] == "SEARCH"
    assert result["response_mode"] == "explain"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "청년도약계좌"


async def test_router_uses_llm_to_classify_unrelated_general_message(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"out_of_scope","request_kind":"general"}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "오늘 저녁 뭐 먹을까?"})

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "out_of_scope"
    assert result["routing_source"] == "llm"
    assert len(llm.calls) == 1


async def test_router_uses_llm_to_classify_greeting(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"general","request_kind":"general"}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "안녕"})

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "general"
    assert result["routing_source"] == "llm"
    assert len(llm.calls) == 1


async def test_router_uses_llm_for_non_request_training_conversation(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"general","request_kind":"general"}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어"})

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "general"
    assert result["routing_source"] == "llm"
    assert len(llm.calls) == 1


async def test_fallback_router_repeats_completed_search_after_region_correction():
    result = await nodes.router_node(
        {
            "user_input": "경기도 말고 서울로",
            "request_kind": "youth_policy",
            "response_mode": "recommend",
            "search_query": "금융",
            "profile": {"region": "경기", "age": 24, "policy_topic": "금융·복지·문화"},
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "금융"


async def test_region_correction_recovers_source_and_query_from_candidate_snapshot():
    result = await nodes.router_node(
        {
            "user_input": "경기도 말고 서울로",
            "last_presented_candidates": [
                {
                    "source": "training",
                    "search_query": "데이터 분석",
                    "title": "데이터 분석 과정",
                }
            ],
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "training"
    assert result["search_query"] == "데이터 분석"
    assert result["routing_source"] == "deterministic_followup"


async def test_missing_candidate_snapshot_blocks_free_form_numbered_followup(monkeypatch):
    llm = StubLLM("존재하지 않는 정책은 월 50만 원을 지원해요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    routed = await nodes.router_node({"user_input": "1번 자세히 알려줘"})
    response = await nodes.conversation_node({"user_input": "1번 자세히 알려줘", **routed})

    assert routed["action"] == "RESPOND"
    assert routed["routing_source"] == "candidate_reference_missing"
    assert "직전 카드 정보를 현재 대화에서 확인할 수 없어요" in response["final_response"]
    assert "50만 원" not in response["final_response"]
    assert len(llm.calls) == 0


def test_clean_response_text_removes_markdown_formal_intro_and_internal_fields():
    text = (
        '### 답변\n사용자님의 질문("청년 지원 정책 정보 요청")에 따라, 서울 정책 후보를 추천합니다.\n'
        "### 추천 정책\n1. **서울 정책**\n- `application_period`와 `detail_url` 확인 필요"
    )

    cleaned = clean_response_text(text)

    assert "###" not in cleaned
    assert "**" not in cleaned
    assert "`" not in cleaned
    assert "사용자님의 질문" not in cleaned
    assert "application_period" not in cleaned
    assert "detail_url" not in cleaned


def test_clean_response_text_keeps_only_final_revision_and_removes_meta_emoji():
    cleaned = clean_response_text(
        "초안 답변입니다.\n---\n수정된 답변:\n안녕하세요! 필요한 청년정책을 언제든 물어보세요. 😊"
    )

    assert cleaned == "안녕하세요! 필요한 청년정책을 언제든 물어보세요."
    assert "초안" not in cleaned
    assert "수정된 답변" not in cleaned


def test_clarification_template_avoids_broken_korean_particle():
    reply = clarification_template(["거주 지역", "만 나이"])

    assert reply == "정확한 결과를 찾으려면 다음 정보가 필요해요: 거주 지역, 만 나이."
    assert "나이을" not in reply


async def test_clarification_uses_llm_with_request_context(monkeypatch):
    llm = StubLLM("서울에서 맞는 정책을 찾으려면 거주 지역과 만 나이를 알려주세요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.clarification_node(
        {
            "user_input": "주거 정책을 찾아줘",
            "request_kind": "youth_policy",
            "response_mode": "recommend",
            "missing_slots": ["region", "age"],
            "profile": {},
        }
    )

    assert "거주 지역과 만 나이" in result["final_response"]
    assert len(llm.calls) == 1
    payload = llm.calls[0]["messages"][1]["content"]
    assert "주거 정책을 찾아줘" in payload
    assert "거주 지역" in payload


def test_card_summary_deduplicates_titles_without_repeating_details():
    response = compose_card_summary_reply(
        request_kind="youth_policy",
        source_status=SearchStatus.SUCCESS,
        candidates=[
            {
                "title": "서울 청년정책",
                "detail_url": "https://example.com/policy/1",
            },
            {
                "title": "서울 청년정책",
                "detail_url": "https://example.com/policy/2",
            },
        ],
    )

    assert "카드 1건" in response
    assert "서울 청년정책" not in response
    assert "https://" not in response


async def test_router_accepts_llm_general_decision_for_non_request_training_conversation(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"general","request_kind":"general","search_query":null}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "요즘 개발 교육을 듣고 있어"})

    assert {
        key: result[key]
        for key in (
            "intent",
            "action",
            "response_mode",
            "request_kind",
            "search_query",
            "routing_source",
            "resumed_pending",
        )
    } == {
        "intent": "GENERAL",
        "action": "RESPOND",
        "response_mode": "general",
        "request_kind": "general",
        "search_query": None,
        "routing_source": "llm",
        "resumed_pending": False,
    }
    assert len(llm.calls) == 1
    assert result["pending_action"] == "NONE"
    assert result["training_results"] == []


async def test_router_falls_back_to_heuristics_when_llm_returns_invalid_json(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", StubLLM("not-json"))

    result = await nodes.router_node({"user_input": "서울 데이터 분석 국비과정 찾아줘"})

    assert result["intent"] == "RECOMMEND"
    assert result["action"] == "SEARCH"
    assert result["response_mode"] == "recommend"
    assert result["request_kind"] == "training"
    assert result["routing_source"] == "heuristic"


async def test_router_returns_validated_llm_search_query(monkeypatch):
    llm = StubLLM(
        '{"action":"SEARCH","response_mode":"recommend","request_kind":"training",'
        '"search_query":"  클라우드   엔지니어  "}'
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "서울에서 클라우드 쪽으로 배울 과정을 찾아줘"})

    assert result["request_kind"] == "training"
    assert result["search_query"] == "클라우드 엔지니어"


async def test_router_discards_inferred_job_query_for_broad_youth_policy_request(monkeypatch):
    llm = StubLLM(
        '{"action":"SEARCH","response_mode":"recommend","request_kind":"youth_policy","search_query":"일자리"}'
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "청년 지원 정책에 대한 정보를 얻고 싶어"})

    assert result["search_query"] is None


async def test_profile_extractor_discards_inferred_job_topic_for_broad_policy_request(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", StubLLM('{"policy_topic":"일자리"}'))

    result = await nodes.profile_extractor_node(
        {
            "user_input": "청년 지원 정책에 대한 정보를 얻고 싶어",
            "request_kind": "youth_policy",
            "profile": {},
        }
    )

    assert "policy_topic" not in result["profile"]


async def test_conversation_node_uses_llm_for_friendly_greeting(monkeypatch):
    llm = StubLLM("안녕하세요! 청년정책이나 취업 준비에 필요한 내용을 편하게 말씀해 주세요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.conversation_node({"user_input": "안녕하세요", "response_mode": "general"})

    assert result["final_response"].startswith("안녕하세요!")
    assert "취업 준비" in result["final_response"]
    assert result["final_response"].endswith("말씀해 주세요.")
    assert len(llm.calls) == 1


async def test_general_career_conversation_uses_llm_for_actionable_advice(monkeypatch):
    llm = StubLLM(
        "지금 듣는 교육의 목표 직무를 먼저 정하고, 이번 주에는 배운 내용을 작은 프로젝트 하나로 정리해 보세요."
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.conversation_node(
        {
            "user_input": "요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어",
            "response_mode": "general",
        }
    )

    assert "작은 프로젝트" in result["final_response"]
    assert "정책나침반은" not in result["final_response"]
    assert len(llm.calls) == 1


async def test_conversation_node_answers_brief_capability_question_friendly():
    result = await nodes.conversation_node({"user_input": "뭐해?", "response_mode": "general"})

    assert "청년 정책과 지원 정보를 찾아드릴 준비" in result["final_response"]
    assert "정책나침반 에이전트" in result["final_response"]
    assert result["final_response"].endswith("언제든지 말씀해 주세요.")


async def test_brief_social_guard_does_not_swallow_policy_question():
    result = await nodes.prepare_request_node({"user_input": "안녕, 청년 월세 정책 찾아줘"})

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "월세"


async def test_conversation_node_uses_short_policy_redirect_without_llm(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())

    result = await nodes.conversation_node(
        {
            "user_input": "지금 내가 우울하다는 얘기야? 왜 나한테 상담을 받아보래?",
            "response_mode": "general",
        }
    )

    assert result["final_response"].startswith("정책나침반은 갓 사회에 진입한 청년")
    assert "현재 범위 밖의 요청에는 답변드리기 어려워요." in result["final_response"]
    assert "우울" not in result["final_response"]


async def test_out_of_scope_reply_does_not_list_specific_professions():
    result = await nodes.conversation_node({"user_input": "세무 상담해줘", "response_mode": "out_of_scope"})

    assert "현재 범위 밖의 요청에는 답변드리기 어려워요." in result["final_response"]
    assert "정책나침반" in result["final_response"]
    assert "세무" not in result["final_response"]
    assert "법률" not in result["final_response"]


async def test_route_validator_preserves_valid_llm_decision():
    result = await nodes.route_validator_node(
        {
            "user_input": "안녕하세요",
            "intent": "GENERAL",
            "action": "RESPOND",
            "response_mode": "general",
            "request_kind": "general",
            "routing_source": "llm",
        }
    )

    assert result == {"route_validation_status": "passed", "route_validation_errors": []}


async def test_route_validator_recovers_greeting_misclassified_as_out_of_scope():
    result = await nodes.route_validator_node(
        {
            "user_input": "안녕",
            "intent": "OUT_OF_SCOPE",
            "action": "RESPOND",
            "response_mode": "out_of_scope",
            "request_kind": "general",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["brief_social_misclassified"]
    assert result["routing_source"] == "semantic_guard"
    assert result["response_mode"] == "general"


async def test_route_validator_recovers_explicit_scope_request_misclassified_as_general():
    result = await nodes.route_validator_node(
        {
            "user_input": "세무 상담해줘",
            "intent": "GENERAL",
            "action": "RESPOND",
            "response_mode": "general",
            "request_kind": "general",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["explicit_out_of_scope_misclassified"]
    assert result["response_mode"] == "out_of_scope"


async def test_route_validator_falls_back_only_for_invalid_contract():
    result = await nodes.route_validator_node(
        {
            "user_input": "안녕하세요",
            "intent": "GENERAL",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "general",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["route_contract_invalid"]
    assert result["routing_source"] == "route_validation_fallback"
    assert result["action"] == "RESPOND"


async def test_route_validator_recovers_valid_but_semantically_wrong_general_route():
    result = await nodes.route_validator_node(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "intent": "GENERAL",
            "action": "RESPOND",
            "response_mode": "general",
            "request_kind": "general",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["explicit_search_request_misclassified"]
    assert result["routing_source"] == "semantic_guard"
    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "training"


async def test_route_validator_recovers_wrong_source_for_explicit_training_request():
    result = await nodes.route_validator_node(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "intent": "RECOMMEND",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "youth_policy",
            "routing_source": "llm",
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["explicit_source_misclassified"]
    assert result["routing_source"] == "semantic_guard"
    assert result["request_kind"] == "training"


async def test_route_validator_rejects_valid_search_route_for_pending_greeting():
    result = await nodes.route_validator_node(
        {
            "user_input": "안녕하세요",
            "intent": "RECOMMEND",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "youth_policy",
            "routing_source": "llm",
            "pending_request": {
                "original_request": "주거 정책을 찾아줘",
                "request_kind": "youth_policy",
                "required_slots": ["region", "age"],
            },
        }
    )

    assert result["route_validation_status"] == "revised"
    assert result["route_validation_errors"] == ["non_search_request_misclassified"]
    assert result["routing_source"] == "semantic_guard"
    assert result["action"] == "RESPOND"
    assert result["pending_action"] == "KEEP"


async def test_response_validator_allows_helpful_general_reply():
    result = await nodes.response_validator_node(
        {
            "response_mode": "general",
            "final_response": "많이 속상하셨겠어요.",
        }
    )

    assert result["response_validation_status"] == "passed"
    assert result["response_validation_errors"] == []


async def test_response_validator_rejects_card_details_then_deterministic_rebuild_passes():
    state = {
        "user_input": "데이터 분석 과정 찾아줘",
        "action": "SEARCH",
        "response_mode": "recommend",
        "request_kind": "training",
        "final_response": "데이터 분석 과정: https://unsupported.example/course",
        "training_results": [
            {
                "course_id": "course-1",
                "title": "데이터 분석 과정",
                "detail_url": "https://work24.example/course-1",
            }
        ],
    }

    validation = await nodes.response_validator_node(state)
    assert "card_summary_missing" in validation["response_validation_errors"]
    assert "card_detail_duplicated" in validation["response_validation_errors"]
    assert "card_url_duplicated" in validation["response_validation_errors"]
    assert edges.route_after_verification({**state, **validation}) == "build_answer"

    rebuilt = await nodes.response_node({**state, **validation})
    assert "카드 1건" in rebuilt["final_response"]
    assert "데이터 분석 과정" not in rebuilt["final_response"]
    assert "https://work24.example/course-1" not in rebuilt["final_response"]
    assert "https://unsupported.example/course" not in rebuilt["final_response"]

    passed = await nodes.response_validator_node({**state, **validation, **rebuilt})
    assert passed["response_validation_errors"] == []
    assert edges.route_after_verification(passed) == "finalize"


async def test_response_validator_rejects_any_presented_card_detail_in_search_bubble():
    result = await nodes.response_validator_node(
        {
            "action": "SEARCH",
            "response_mode": "recommend",
            "final_response": "첫 과정 https://example.com/one",
            "training_results": [
                {"course_id": "T1", "title": "첫 과정", "detail_url": "https://example.com/one"},
                {"course_id": "T2", "title": "둘째 과정", "detail_url": "https://example.com/two"},
            ],
        }
    )

    assert "card_summary_missing" in result["response_validation_errors"]
    assert "card_detail_duplicated" in result["response_validation_errors"]
    assert "card_url_duplicated" in result["response_validation_errors"]


async def test_router_sends_named_policy_explanation_to_search(monkeypatch):
    llm = StubLLM(
        '{"action":"SEARCH","response_mode":"explain","request_kind":"youth_policy","search_query":"청년도약계좌"}'
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "청년도약계좌의 현재 조건을 설명해줘"})

    assert result["intent"] == "EXPLAIN"
    assert result["action"] == "SEARCH"
    assert result["response_mode"] == "explain"
    assert result["request_kind"] == "youth_policy"


async def test_search_explanation_skips_recommendation_slots():
    result = await nodes.missing_slot_node({"response_mode": "explain", "request_kind": "youth_policy", "profile": {}})

    assert result["missing_slots"] == []


async def test_topic_listing_explanation_still_requires_personalization_slots():
    result = await nodes.missing_slot_node(
        {
            "response_mode": "explain",
            "request_kind": "youth_policy",
            "profile": {"policy_topic": "주거"},
        }
    )

    assert result["missing_slots"] == ["region", "age"]


def test_route_after_prepare_uses_action_and_missing_slots():
    assert edges.route_after_prepare({"action": "RESPOND"}) == "direct_response"
    assert edges.route_after_prepare({"action": "SEARCH", "missing_slots": ["age"]}) == "direct_response"
    assert edges.route_after_prepare({"action": "SEARCH", "missing_slots": []}) == "retrieve"


def test_heuristic_extract_profile_job_seeking_youth():
    text = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"
    profile = nodes._heuristic_extract_profile(text)

    assert profile["region"] == "서울"
    assert profile["employment_status"] == "unemployed_seeking_job"
    assert "graduation_status" not in profile


def test_heuristic_extract_profile_reads_suffix_omitted_region_inside_sentence():
    profile = nodes._heuristic_extract_profile("성남 거주 만 24세")

    assert profile["region"] == "경기 성남시"
    assert profile["age"] == 24


def test_heuristic_extract_profile_recognizes_official_youth_policy_topics():
    assert nodes._heuristic_extract_profile("월세와 주거비 지원이 필요해")["policy_topic"] == "주거"
    assert nodes._heuristic_extract_profile("문화생활 지원 정책을 찾아줘")["policy_topic"] == "금융·복지·문화"
    assert nodes._heuristic_extract_profile("청년 참여 활동을 하고 싶어")["policy_topic"] == "참여·기반"


async def test_profile_extractor_applies_explicit_region_correction():
    result = await nodes.profile_extractor_node(
        {
            "user_input": "경기도 말고 서울로",
            "request_kind": "youth_policy",
            "profile": {"region": "경기", "age": 24, "policy_topic": "금융·복지·문화"},
        }
    )

    assert result["profile"]["region"] == "서울"


async def test_profile_extractor_ignores_invalid_llm_fields_without_corrupting_profile(monkeypatch):
    llm = StubLLM(
        '{"age":"not-a-number","region":{"instruction":"override"},'
        '"policy_topic":"주거","unknown_instruction":"ignore safeguards"}'
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.profile_extractor_node(
        {
            "user_input": "월세 정책을 다시 찾아줘",
            "request_kind": "youth_policy",
            "profile": {"age": 24, "region": "서울"},
        }
    )

    assert result["profile"]["age"] == 24
    assert result["profile"]["region"] == "서울"
    assert result["profile"]["policy_topic"] == "주거"
    assert "unknown_instruction" not in result["profile"]


async def test_prepare_request_applies_explicit_profile_clear_on_direct_response(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    result = await nodes.prepare_request_node(
        {
            "user_input": "내 나이는 저장하지 마",
            "profile": {"age": 24, "region": "서울", "policy_topic": "주거"},
        }
    )

    assert result["action"] == "RESPOND"
    assert result["profile"] == {"region": "서울", "policy_topic": "주거"}


async def test_missing_slot_node_flags_missing_region():
    state = {"profile": {"employment_status": "unemployed_seeking_job"}}
    result = await nodes.missing_slot_node(state)
    assert "region" in result["missing_slots"]
    assert "status" not in result["missing_slots"]


async def test_missing_slot_node_no_missing_when_complete():
    state = {
        "search_query": "주거",
        "profile": {"region": "서울", "age": 25, "employment_status": "unemployed_seeking_job"},
    }
    result = await nodes.missing_slot_node(state)
    assert result["missing_slots"] == []


async def test_housing_policy_does_not_require_employment_or_entrepreneur_status():
    result = await nodes.missing_slot_node(
        {
            "request_kind": "youth_policy",
            "profile": {"region": "서울", "age": 24, "policy_topic": "주거"},
        }
    )

    assert result["missing_slots"] == []


async def test_job_policy_requires_employment_status_but_not_entrepreneur_status():
    result = await nodes.missing_slot_node(
        {
            "request_kind": "youth_policy",
            "profile": {"region": "서울", "age": 24, "policy_topic": "일자리"},
        }
    )

    assert result["missing_slots"] == ["employment_status"]


async def test_router_resumes_pending_search_from_clarification_answer(monkeypatch):
    llm = StubLLM(
        '{"action":"SEARCH","response_mode":"recommend","request_kind":"youth_policy",'
        '"search_query":"주거","resume_pending":true}'
    )
    monkeypatch.setattr(nodes, "_llm", llm)
    pending = {
        "original_request": "거주지원을 받고 싶어",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node(
        {
            "user_input": "서울에 살고 있고 취업 준비 중인 만 25세야",
            "pending_request": pending,
            "conversation_history": [{"role": "assistant", "content": "지역과 나이를 알려주세요"}],
        }
    )

    assert result["resumed_pending"] is True
    assert result["search_query"] == "주거"
    assert result["routing_source"] == "llm"
    router_payload = llm.calls[0]["messages"][1]["content"]
    assert "pending_request" in router_payload
    assert "recent_history" in router_payload


async def test_router_keeps_pending_for_unrelated_greeting(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node({"user_input": "안녕하세요", "pending_request": pending})

    assert result["action"] == "RESPOND"
    assert result["resumed_pending"] is False
    assert result["pending_action"] == "KEEP"
    assert "pending_request" not in result


async def test_router_cancels_pending_without_calling_llm(monkeypatch):
    llm = StubLLM("사용되면 안 되는 응답")
    monkeypatch.setattr(nodes, "_llm", llm)
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "required_slots": ["region"],
    }

    result = await nodes.router_node({"user_input": "그거 취소해줘", "pending_request": pending})

    assert result["action"] == "RESPOND"
    assert result["pending_action"] == "CANCEL"
    assert result["pending_request"] == {}
    assert result["resumed_pending"] is False
    assert llm.calls == []


async def test_router_rejects_llm_pending_resume_without_slot_evidence(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM(
            '{"action":"SEARCH","response_mode":"recommend","request_kind":"youth_policy",'
            '"search_query":"주거","resume_pending":true}'
        ),
    )
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node({"user_input": "안녕하세요", "pending_request": pending})

    assert result["action"] == "RESPOND"
    assert result["resumed_pending"] is False
    assert result["pending_action"] == "KEEP"
    assert result["routing_source"] == "pending_validation_fallback"


async def test_graph_preserves_pending_when_llm_misclassifies_greeting_as_search(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM('{"action":"SEARCH","response_mode":"recommend","request_kind":"youth_policy"}'),
    )
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await build_agent_graph().ainvoke(
        {"user_input": "안녕하세요", "pending_request": pending},
        config={"configurable": {"thread_id": "pending-greeting-semantic-guard"}},
    )

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "general"
    assert result["routing_source"] == "semantic_guard"
    assert result["pending_action"] == "KEEP"
    assert result["pending_request"] == pending
    assert result["final_response"].startswith("안녕하세요!")


async def test_router_prioritizes_filled_pending_slots_over_wrong_new_llm_search(monkeypatch):
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM(
            '{"action":"SEARCH","response_mode":"recommend","request_kind":"training",'
            '"search_query":"데이터","resume_pending":false}'
        ),
    )
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node(
        {
            "user_input": "서울에 살고 있고 만 25세야",
            "pending_request": pending,
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "주거"
    assert result["resumed_pending"] is True
    assert result["pending_action"] == "RESUME"
    assert result["routing_source"] == "pending_slot_guard"


@pytest.mark.parametrize("misclassified_mode", ["general", "out_of_scope"])
async def test_router_records_pending_guard_when_llm_misclassifies_region_answer(
    monkeypatch,
    misclassified_mode,
):
    monkeypatch.setattr(
        nodes,
        "_llm",
        StubLLM(
            '{"action":"RESPOND","response_mode":"'
            + misclassified_mode
            + '","request_kind":"general","resume_pending":true}'
        ),
    )
    pending = {
        "original_request": "금융관련 지원 정책이 있어?",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "금융",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node({"user_input": "성남 거주", "pending_request": pending})

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "youth_policy"
    assert result["search_query"] == "금융"
    assert result["resumed_pending"] is True
    assert result["pending_action"] == "RESUME"
    assert result["routing_source"] == "pending_slot_guard"


async def test_new_search_replaces_pending_and_cannot_reuse_old_query(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    pending = {
        "original_request": "주거 정책을 찾아줘",
        "request_kind": "youth_policy",
        "response_mode": "recommend",
        "search_query": "주거",
        "required_slots": ["region", "age"],
    }

    result = await nodes.router_node(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "pending_request": pending,
        }
    )

    assert result["action"] == "SEARCH"
    assert result["request_kind"] == "training"
    assert result["pending_action"] == "REPLACE"
    assert result["pending_request"] == {}
    assert result["search_query"] is None


async def test_router_does_not_resume_pending_search_for_out_of_scope_fallback(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    result = await nodes.router_node(
        {
            "user_input": "법률 자문을 해줘",
            "pending_request": {
                "original_request": "주거 정책을 찾아줘",
                "request_kind": "youth_policy",
                "response_mode": "recommend",
                "search_query": "주거",
            },
        }
    )

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "out_of_scope"
    assert result["resumed_pending"] is False


async def test_clarification_stores_original_search_plan(monkeypatch):
    monkeypatch.setattr(nodes, "_llm", StubLLM("나이와 거주 지역을 알려주시겠어요?"))
    result = await nodes.clarification_node(
        {
            "user_input": "거주지원을 받고 싶어",
            "request_kind": "youth_policy",
            "response_mode": "recommend",
            "search_query": "주거",
            "missing_slots": ["region", "age"],
            "profile": {},
        }
    )

    assert result["pending_request"]["original_request"] == "거주지원을 받고 싶어"
    assert result["pending_request"]["search_query"] == "주거"
    assert result["pending_request"]["required_slots"] == ["region", "age"]


async def test_fresh_turn_state_prevents_previous_search_from_replacing_next_answers(monkeypatch):
    class OfflineLLM:
        is_configured = False

    class TrainingResult:
        def model_dump(self):
            return {
                "course_id": "course-1",
                "title": "이전 턴 데이터 분석 과정",
                "region": "서울",
                "detail_url": "https://example.com/course-1",
            }

    class TrainingTool:
        async def execute(self, payload):  # noqa: ARG002
            return [TrainingResult()]

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    monkeypatch.setattr(nodes, "_training_tool", TrainingTool())
    graph = build_agent_graph()
    config = {"configurable": {"thread_id": "fresh-turn-regression"}}

    first = await graph.ainvoke(
        {
            "user_input": "서울 데이터 분석 국비과정 찾아줘",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        },
        config=config,
    )
    assert first["training_results"]

    explanation = await graph.ainvoke(
        {"user_input": "국비지원 훈련을 받으면 뭐가 좋아?"},
        config=config,
    )
    greeting = await graph.ainvoke({"user_input": "안녕하세요"}, config=config)

    for result in (explanation, greeting):
        assert result["training_results"] == []
        assert result["response_revision_count"] == 0
        assert "이전 턴 데이터 분석 과정" not in result["final_response"]
        assert "최종 신청 가능 여부" not in result["final_response"]


async def test_explanation_conversation_sends_recent_history_to_llm(monkeypatch):
    llm = StubLLM("국비지원 훈련의 장점을 이어서 설명할게요.")
    monkeypatch.setattr(nodes, "_llm", llm)
    history = [{"role": "user", "content": "국비지원 훈련이 궁금해"}]

    await nodes.conversation_node(
        {"user_input": "어떤 점이 좋아?", "response_mode": "explain", "conversation_history": history}
    )

    assert "국비지원 훈련이 궁금해" in llm.calls[0]["messages"][1]["content"]


async def test_candidate_followup_uses_llm_with_allowlisted_snapshot(monkeypatch):
    llm = StubLLM(
        "직전 안내의 두 번째 과정에는 훈련장려금 정보가 없어요. "
        "두 번째 과정 공식 원문에서 확인해 주세요. https://example.com/two"
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    state = {
        "user_input": "방금 2번 과정의 훈련장려금은 얼마야?",
        "action": "RESPOND",
        "response_mode": "explain",
        "last_presented_candidates": [
            {"source": "training", "title": "첫 번째 과정"},
            {
                "source": "training",
                "title": "두 번째 과정",
                "detail_url": "https://example.com/two",
            },
        ],
    }
    result = await nodes.conversation_node(state)

    assert "두 번째 과정" in result["final_response"]
    assert "정보가 없" in result["final_response"]
    assert "https://example.com/two" in result["final_response"]
    assert "99만원" not in result["final_response"]
    assert len(llm.calls) == 1
    assert nodes.validate_response_state({**state, **result}) == []


async def test_candidate_followup_routes_without_llm_and_passes_full_graph(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    result = await build_agent_graph().ainvoke(
        {
            "user_input": "방금 2번 과정의 기간 알려줘",
            "last_presented_candidates": [
                {"source": "training", "title": "첫 번째 과정"},
                {
                    "source": "training",
                    "title": "두 번째 과정",
                    "start_date": "2026-08-01",
                    "end_date": "2026-09-30",
                    "detail_url": "https://example.com/two",
                },
            ],
        }
    )

    assert result["routing_source"] == "candidate_reference"
    assert result["response_validation_status"] == "passed"
    assert "두 번째 과정" in result["final_response"]
    assert "2026-08-01" in result["final_response"]
    assert "2026-09-30" in result["final_response"]


async def test_ungrounded_explanation_numbers_and_url_recover_to_safe_domain_guide(monkeypatch):
    llm = StubLLM(
        '{"action":"RESPOND","response_mode":"explain","request_kind":"general","search_query":null}',
        "2026년에는 월 50만원을 줍니다. https://invented.example/policy",
        "2026년에는 월 50만원을 줍니다. https://invented.example/policy",
    )
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await build_agent_graph().ainvoke({"user_input": "훈련장려금이 뭐야?"})

    assert result["response_revision_count"] == 1
    assert result["abstention_reason"] == "answer_verification_failed"
    assert "50만원" not in result["final_response"]
    assert "invented.example" not in result["final_response"]
    assert "국비지원 훈련" in result["final_response"]
    assert "고용24" in result["final_response"]


async def test_profile_extractor_preserves_llm_selected_request_kind(monkeypatch):
    llm = StubLLM('{"region":"서울","desired_job":"데이터 분석"}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.profile_extractor_node(
        {
            "user_input": "서울에서 데이터 분야 프로그램을 알아보고 있어",
            "request_kind": "training",
        }
    )

    assert result["request_kind"] == "training"
    assert result["profile"]["request_kind"] == "training"


async def test_startup_support_uses_llm_classification_then_fixed_scope_reply_without_tools(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"out_of_scope","request_kind":"general"}')

    class FailingTool:
        async def execute(self, payload):  # noqa: ARG002
            raise AssertionError("창업 안내는 외부 검색 Tool을 호출하면 안 됩니다.")

    monkeypatch.setattr(nodes, "_llm", llm)
    monkeypatch.setattr(nodes, "_youth_policy_tool", FailingTool())
    monkeypatch.setattr(nodes, "_training_tool", FailingTool())
    monkeypatch.setattr(nodes, "_recruitment_tool", FailingTool())

    result = await build_agent_graph().ainvoke(
        {
            "user_input": "서울에서 카페 창업 지원사업 찾아줘",
            "pending_request": {
                "request_kind": "youth_policy",
                "required_slots": ["region"],
            },
        },
        config={"configurable": {"thread_id": "startup-out-of-scope"}},
    )

    assert result["action"] == "RESPOND"
    assert result["response_mode"] == "out_of_scope"
    assert result["request_kind"] == "general"
    assert result["pending_request"] == {
        "request_kind": "youth_policy",
        "required_slots": ["region"],
    }
    assert "정책나침반" in result["final_response"]
    assert "현재 범위 밖의 요청에는 답변드리기 어려워요" in result["final_response"]
    assert "창업" not in result["final_response"]
    assert len(llm.calls) == 1
    assert result["youth_policy_results"] == []
    assert result["training_results"] == []
    assert result["recruitment_results"] == []


async def test_training_tool_prefers_llm_planned_search_query(monkeypatch):
    captured = {}

    class TrainingTool:
        async def execute(self, payload):
            captured["desired_job"] = payload.desired_job
            captured["keywords"] = payload.keywords
            return []

    monkeypatch.setattr(nodes, "_training_tool", TrainingTool())

    await nodes.policy_search_node(
        {
            "user_input": "무언가 새로운 기술을 배우고 싶어",
            "request_kind": "training",
            "search_query": "클라우드 엔지니어",
            "profile": {"region": "서울", "desired_job": "데이터 분석"},
        }
    )

    assert captured == {"desired_job": "클라우드 엔지니어", "keywords": "무언가 새로운 기술을 배우고 싶어"}


async def test_grounded_tool_response_uses_llm_with_source_evidence(monkeypatch):
    llm = StubLLM("조건에 맞는 훈련과정 카드 1건을 찾았어요. 아래 카드에서 자세히 확인해 주세요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.response_node(
        {
            "user_input": "데이터 분석 훈련과정 알려줘",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "training",
            "search_outcome": {"status": "success"},
            "profile": {"region": "서울"},
            "training_results": [{"title": "데이터 분석 과정", "detail_url": "https://example.com/course"}],
        }
    )

    assert "카드 1건" in result["final_response"]
    assert "데이터 분석 과정" not in result["final_response"]
    assert "https://example.com/course" not in result["final_response"]
    assert "최종 신청 가능 여부" in result["final_response"]
    assert len(llm.calls) == 1
    payload = llm.calls[0]["messages"][1]["content"]
    assert '"card_count": 1' in payload
    assert "데이터 분석 과정" not in payload
    assert "https://example.com/course" not in payload


async def test_grounded_revision_sends_validation_errors_to_llm(monkeypatch):
    llm = StubLLM("조건에 맞는 훈련과정 카드 1건을 다시 정리했어요. 아래 카드에서 확인해 주세요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    await nodes.response_node(
        {
            "user_input": "데이터 분석 훈련과정 알려줘",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "training",
            "search_outcome": {"status": "success"},
            "training_results": [{"title": "데이터 분석 과정", "detail_url": "https://example.com/course"}],
            "response_validation_errors": ["card_url_duplicated"],
            "final_response": "잘못된 초안 https://invented.example/course",
        }
    )

    payload = llm.calls[0]["messages"][1]["content"]
    assert "card_url_duplicated" in payload
    assert "invented.example" in payload
    assert "데이터 분석 과정" not in payload
    assert "example.com/course" not in payload


async def test_training_card_summary_does_not_repeat_institution_url():
    state = {
        "user_input": "서울 데이터 분석 과정 찾아줘",
        "action": "SEARCH",
        "response_mode": "recommend",
        "request_kind": "training",
        "search_outcome": {"status": "success"},
        "training_results": [
            {
                "course_id": "course-1",
                "title": "데이터 분석 과정",
                "region": "서울",
                "match_scope": "exact",
                "institution_url": "https://example.com/institution",
            }
        ],
    }

    rendered = await nodes.response_node(state)
    validation_errors = nodes.validate_response_state({**state, **rendered})

    assert "카드 1건" in rendered["final_response"]
    assert "데이터 분석 과정" not in rendered["final_response"]
    assert "https://example.com/institution" not in rendered["final_response"]
    assert validation_errors == []


def test_partial_search_reply_discloses_incomplete_source_without_internal_warning():
    text = nodes._prepare_search_response(
        {
            "action": "SEARCH",
            "search_outcome": {
                "status": "partial",
                "warnings": ["EMPLOYMENT24_JOB_API_KEY internal failure"],
            },
        },
        "서울 채용행사\nhttps://example.com/event",
    )

    assert "확인된 범위만" in text
    assert "EMPLOYMENT24_JOB_API_KEY" not in text


def test_unavailable_reply_never_exposes_internal_configuration_names():
    reply = compose_search_status_reply(
        status=SearchStatus.UNAVAILABLE,
        request_kind="training",
        profile={"region": "서울"},
        search_query="데이터",
        warnings=["EMPLOYMENT24_TRAINING_API_KEY 미설정"],
    )

    assert "검색 결과가 없다는 뜻은 아니" in reply
    assert "EMPLOYMENT24_TRAINING_API_KEY" not in reply


async def test_search_status_uses_llm_without_exposing_internal_warning(monkeypatch):
    llm = StubLLM("고용24 조회가 일시적으로 어려워요. 검색 결과가 없다는 뜻은 아니니 잠시 후 다시 시도해 주세요.")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.direct_response_node(
        {
            "user_input": "서울 데이터 분석 과정 찾아줘",
            "request_kind": "training",
            "search_outcome": {
                "status": "unavailable",
                "warnings": ["EMPLOYMENT24_TRAINING_API_KEY internal failure"],
            },
            "search_context": {"search_query": "데이터 분석"},
        }
    )

    assert "검색 결과가 없다는 뜻은 아니" in result["final_response"]
    assert "EMPLOYMENT24_TRAINING_API_KEY" not in result["final_response"]
    assert len(llm.calls) == 1


async def test_direct_scope_reply_runs_through_response_verification(monkeypatch):
    class OfflineLLM:
        is_configured = False

    monkeypatch.setattr(nodes, "_llm", OfflineLLM())
    result = await build_agent_graph().ainvoke({"user_input": "안녕하세요"})

    assert result["response_validation_status"] == "passed"
    assert "정책나침반" in result["final_response"]


def test_deadline_status_transitions():
    today = date(2026, 7, 9)
    assert deadline_status(None, today=today) == "일정 확인 필요"
    assert deadline_status("not-a-date", today=today) == "일정 확인 필요"
    assert deadline_status("2026-06-30", today=today) == "마감"
    assert deadline_status("2026-07-15", today=today) == "마감임박"
    assert deadline_status("2026-12-31", today=today) == "모집중"


def test_pre_verification_safety_softens_absolute_language_and_adds_disclaimer():
    state = {
        "action": "SEARCH",
        "final_response": "이 사업은 반드시 신청 가능합니다.",
        "youth_policy_results": [{"title": "서울 청년정책"}],
    }
    result = nodes._prepare_search_response(state, state["final_response"])

    assert "반드시" not in result
    assert "확인해 주세요" in result


def test_pre_verification_safety_removes_duplicate_and_unsupported_missing_info():
    state = {
        "action": "SEARCH",
        "final_response": (
            "추천 정책\n1. 서울 청년정책\n\n안내 사항:\n"
            "- 최종 자격 요건 및 신청 가능 여부는 공식 공고 확인이 필요합니다.\n"
            "- 누락된 신청 정보(예: 전화번호, 기관명)는 공식 링크를 참고하세요."
        ),
        "youth_policy_results": [{"title": "서울 청년정책"}],
    }

    result = nodes._prepare_search_response(state, state["final_response"])

    assert "추천 정책" not in result
    assert "안내 사항" not in result
    assert "누락된 신청 정보" not in result
    assert result.count("최종 신청 가능 여부") == 1
