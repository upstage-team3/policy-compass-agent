from __future__ import annotations

from datetime import date

from app.graph import edges, nodes
from app.graph.response_composer import (
    _compact_candidates,
    clarification_template,
    clean_response_text,
    compose_no_results_reply,
    compose_youth_policy_response,
)
from app.graph.scoring import deadline_status, score_policy
from app.repositories.policy import _normalize_bizinfo_item, _normalize_bizinfo_items


class StubLLM:
    is_configured = True

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[dict] = []

    async def complete(self, messages, **kwargs):
        self.calls.append({"messages": messages, "kwargs": kwargs})
        return self.responses.pop(0)


def test_heuristic_route_recommend():
    assert nodes._heuristic_route("취업 준비 중인데 받을 수 있는 지원금 있어?") == "RECOMMEND"


def test_heuristic_route_eligibility_check():
    assert nodes._heuristic_route("이 사업 자격 되나요?") == "ELIGIBILITY_CHECK"


def test_heuristic_route_out_of_scope():
    assert nodes._heuristic_route("세무 상담 좀 해줄 수 있어?") == "OUT_OF_SCOPE"


def test_heuristic_route_general():
    assert nodes._heuristic_route("안녕하세요") == "GENERAL"


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


def test_clarification_template_avoids_broken_korean_particle():
    reply = clarification_template(["거주 지역", "만 나이"])

    assert reply == "정확한 결과를 찾으려면 다음 정보가 필요해요: 거주 지역, 만 나이."
    assert "나이을" not in reply


async def test_youth_no_results_reply_does_not_recommend_other_projects():
    reply = await compose_no_results_reply(
        nodes._llm,
        user_input="청년 월세 지원 정책은 없어?",
        profile={"region": "경기", "age": 24},
        source_type="youthcenter_policy",
        search_query="월세",
    )

    assert "검색 결과를 찾지 못했어요" in reply
    assert "안내할 정책이 없습니다" in reply
    assert "넓히" not in reply


def test_youth_policy_template_groups_truly_missing_application_fields():
    """세부 내용은 프론트 카드로 표시되므로, 템플릿 응답은 짧은 안내 멘트만 담아야 한다."""

    response = compose_youth_policy_response(
        [
            {
                "title": "서울 청년정책",
                "business_period": "2026-01-01 ~ 2026-12-31",
                "target_summary": "서울 거주 청년",
                "support_summary": "상담 지원",
            }
        ]
    )

    assert "카드" in response
    assert "사업 기간: 2026-01-01 ~ 2026-12-31" not in response
    assert "application_period" not in response


def test_youth_policy_template_distinguishes_api_failure_from_no_results():
    response = compose_youth_policy_response(
        [
            {
                "policy_id": "youthcenter-guide",
                "title": "온통청년 청년정책 조회 안내",
                "fallback_reason": "온통청년 API가 일시적으로 응답하지 않았어요.",
            }
        ]
    )

    assert "정책이 없다고 판단한 것은 아니" in response
    assert "API가 일시적으로 응답하지 않았어요" in response


def test_compact_youth_candidates_expose_only_actual_missing_information():
    compact = _compact_candidates(
        [
            {
                "source": "youthcenter",
                "title": "서울 청년정책",
                "application_period": None,
                "application_method": "온라인 신청",
                "detail_url": None,
            }
        ]
    )[0]

    assert "application_period" not in compact
    assert compact["application_method"] == "온라인 신청"
    assert compact["data_notice"] == "온통청년 API에 신청 기간·상세 링크 정보가 등록되어 있지 않아요."


async def test_router_uses_llm_semantics_without_keyword_override(monkeypatch):
    llm = StubLLM('{"action":"RESPOND","response_mode":"general","request_kind":"general","search_query":null}')
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.router_node({"user_input": "요즘 개발 교육을 듣고 있어"})

    assert result == {
        "intent": "GENERAL",
        "action": "RESPOND",
        "response_mode": "general",
        "request_kind": "general",
        "search_query": None,
        "routing_source": "llm",
        "resumed_pending": False,
    }
    assert llm.calls[0]["kwargs"]["response_format_json"] is True


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


async def test_conversation_node_uses_llm_for_general_response(monkeypatch):
    llm = StubLLM("반가워요. 오늘 어떤 고민부터 이야기해볼까요?")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.conversation_node({"user_input": "안녕하세요", "response_mode": "general"})

    assert result["final_response"] == "반가워요. 오늘 어떤 고민부터 이야기해볼까요?"
    assert len(llm.calls) == 1


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


def test_route_after_router_uses_action_only():
    assert edges.route_after_router({"action": "RESPOND", "intent": "EXPLAIN"}) == "conversation"
    assert edges.route_after_router({"action": "SEARCH", "intent": "GENERAL"}) == "extract_profile"


def test_heuristic_extract_profile_job_seeking_youth():
    text = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"
    profile = nodes._heuristic_extract_profile(text)

    assert profile["region"] == "서울"
    assert profile["employment_status"] == "unemployed_seeking_job"
    assert profile["graduation_status"] == "graduated_within_2y"


def test_heuristic_extract_profile_entrepreneur():
    text = "부산에서 IT 창업 준비 중인데 지원사업 추천해줘"
    profile = nodes._heuristic_extract_profile(text)

    assert profile["region"] == "부산"
    assert profile["is_entrepreneur"] is True
    assert "IT" in profile["interest_fields"]


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
    router_payload = llm.calls[0]["messages"][1]["content"]
    assert "pending_request" in router_payload
    assert "recent_history" in router_payload


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


async def test_conversation_node_sends_recent_history_to_llm(monkeypatch):
    llm = StubLLM("그 고민부터 이어서 이야기해볼게요.")
    monkeypatch.setattr(nodes, "_llm", llm)
    history = [{"role": "user", "content": "취업 준비가 막막해"}]

    await nodes.conversation_node(
        {"user_input": "어디서부터 시작할까?", "response_mode": "general", "conversation_history": history}
    )

    assert "취업 준비가 막막해" in llm.calls[0]["messages"][1]["content"]


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


async def test_business_request_calls_only_bizinfo_tool(monkeypatch):
    calls = {"bizinfo": 0, "youth": 0}

    class BizinfoTool:
        async def execute(self, payload):  # noqa: ARG002
            calls["bizinfo"] += 1
            return []

    class YouthTool:
        async def execute(self, payload):  # noqa: ARG002
            calls["youth"] += 1
            return []

    monkeypatch.setattr(nodes, "_search_tool", BizinfoTool())
    monkeypatch.setattr(nodes, "_youth_policy_tool", YouthTool())

    await nodes.policy_search_node(
        {
            "user_input": "서울 청년 창업 지원사업 찾아줘",
            "request_kind": "business",
            "profile": {"region": "서울", "is_entrepreneur": True},
        }
    )

    assert calls == {"bizinfo": 1, "youth": 0}


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


async def test_grounded_tool_response_uses_llm_when_configured(monkeypatch):
    llm = StubLLM("검색 결과를 바탕으로 정리한 답변")
    monkeypatch.setattr(nodes, "_llm", llm)

    result = await nodes.response_node(
        {
            "user_input": "데이터 분석 훈련과정 알려줘",
            "profile": {"region": "서울"},
            "training_results": [{"title": "데이터 분석 과정", "detail_url": "https://example.com/course"}],
        }
    )

    assert result["final_response"] == "검색 결과를 바탕으로 정리한 답변"
    assert len(llm.calls) == 1


def test_score_policy_region_match_scores_higher_than_mismatch():
    policy = {
        "title": "서울 청년 사업",
        "category": "구직창업",
        "region": ["서울"],
        "min_age": 19,
        "max_age": 29,
        "target_employment_status": ["unemployed_seeking_job"],
        "target_entrepreneur": None,
        "requires_business_registration": None,
        "support_content": "",
        "apply_end": None,
    }
    matching_profile = {"region": "서울", "age": 25, "employment_status": "unemployed_seeking_job"}
    mismatched_profile = {"region": "부산", "age": 25, "employment_status": "unemployed_seeking_job"}

    match_score = score_policy(matching_profile, policy)["match_score"]
    mismatch_score = score_policy(mismatched_profile, policy)["match_score"]

    assert match_score > mismatch_score


def test_deadline_status_transitions():
    today = date(2026, 7, 9)
    assert deadline_status(None, today=today) == "상시"
    assert deadline_status("2026-06-30", today=today) == "마감"
    assert deadline_status("2026-07-15", today=today) == "마감임박"
    assert deadline_status("2026-12-31", today=today) == "모집중"


def test_score_policy_expired_deadline_reduces_score():
    policy = {
        "title": "마감된 사업",
        "category": "구직창업",
        "region": ["전국"],
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": None,
        "requires_business_registration": None,
        "support_content": "",
        "apply_end": "2026-06-30",
    }
    result = score_policy({"region": "서울"}, policy, today=date(2026, 7, 9))
    assert result["deadline_status"] == "마감"
    assert any("마감" in note for note in result["follow_up_checks"])


async def test_guardrail_node_softens_absolute_language_and_adds_disclaimer():
    state = {
        "final_response": "이 사업은 반드시 신청 가능합니다.",
        "scored_results": [{"policy": {}, "match_score": 0.5}],
    }
    result = await nodes.guardrail_node(state)

    assert "반드시" not in result["final_response"] or "신청 가능성이 높아요" in result["final_response"]
    assert "확인해 주세요" in result["final_response"]
    assert result["guardrail_notes"]


async def test_guardrail_removes_generated_duplicate_and_unsupported_missing_info():
    state = {
        "final_response": (
            "추천 정책\n1. 서울 청년정책\n\n안내 사항:\n"
            "- 최종 자격 요건 및 신청 가능 여부는 공식 공고 확인이 필요합니다.\n"
            "- 누락된 신청 정보(예: 전화번호, 기관명)는 공식 링크를 참고하세요."
        ),
        "youth_policy_results": [{"title": "서울 청년정책"}],
    }

    result = await nodes.guardrail_node(state)

    assert "추천 정책" not in result["final_response"]
    assert "안내 사항" not in result["final_response"]
    assert "누락된 신청 정보" not in result["final_response"]
    assert result["final_response"].count("최종 신청 가능 여부") == 1


def test_normalize_bizinfo_item_handles_empty_optional_fields():
    item = {
        "pblancId": "BIZ-1",
        "pblancNm": "AI 창업 지원사업",
        "reqstBeginEndDe": "20260701 ~ 20260731",
        "pldirSportRealmLclasCodeNm": "창업",
        "hashTags": "서울,AI",
    }

    normalized = _normalize_bizinfo_item(item)

    assert normalized["id"] == "BIZ-1"
    assert normalized["category"] == "창업"
    assert normalized["region"] == ["서울"]
    assert normalized["apply_start"] == "2026-07-01"
    assert normalized["apply_end"] == "2026-07-31"
    assert "확인이 필요" in normalized["target_description"]
    assert normalized["source_url"] == "https://www.bizinfo.go.kr/"


def test_normalize_bizinfo_items_accepts_nested_items_shape():
    payload = {"response": {"body": {"items": {"item": {"pblancId": "BIZ-1"}}}}}

    assert _normalize_bizinfo_items(payload) == [{"pblancId": "BIZ-1"}]


def test_normalize_bizinfo_live_json_shape_and_dashed_period():
    payload = {
        "jsonArray": [
            {
                "pblancId": "BIZ-2",
                "pblancNm": "청년창업 지원",
                "reqstBeginEndDe": "2026-07-08 ~ 2026-07-21",
                "pldirSportRealmLclasCodeNm": "창업",
                "hashtags": "서울,AI",
            }
        ]
    }

    items = _normalize_bizinfo_items(payload)
    normalized = _normalize_bizinfo_item(items[0])

    assert normalized["region"] == ["서울"]
    assert normalized["apply_start"] == "2026-07-08"
    assert normalized["apply_end"] == "2026-07-21"
