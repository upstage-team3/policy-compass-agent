from __future__ import annotations

import pytest

from app.graph import edges, nodes
from app.graph.response_composer import compose_card_summary_reply
from app.graph.validators import validate_response_state


class StubLLM:
    is_configured = True

    def __init__(self, *responses: str) -> None:
        self.responses = list(responses)
        self.calls: list[str] = []

    async def complete(self, messages, **kwargs):  # noqa: ARG002
        self.calls.append(kwargs.get("operation_name", ""))
        return self.responses.pop(0)


def test_first_greeting_rejects_invented_history_and_empty_redirect():
    invented_history = validate_response_state(
        {
            "user_input": "안녕",
            "action": "RESPOND",
            "response_mode": "general",
            "conversation_history": [],
            "final_response": "안녕하세요! 다시 연락 주셔서 감사해요. 청년정책을 편하게 물어보세요.",
        }
    )
    empty_redirect = validate_response_state(
        {
            "user_input": "안녕",
            "action": "RESPOND",
            "response_mode": "general",
            "conversation_history": [],
            "final_response": "안녕하세요.",
        }
    )

    assert "unsupported_conversation_history" in invented_history
    assert "greeting_scope_missing" in empty_redirect
    assert "greeting_invitation_missing" in empty_redirect


def test_ungrounded_general_reply_rejects_spaced_money_age_range_and_duration():
    errors = validate_response_state(
        {
            "user_input": "1번 자세히 알려줘",
            "action": "RESPOND",
            "response_mode": "general",
            "final_response": "만 19~34세에게 월 50만 원을 지원하며 2년 유지해야 해요.",
        }
    )

    assert "ungrounded_general_fact" in errors


async def test_repeated_bad_greeting_ends_in_policy_greeting_template(monkeypatch):
    unsafe = "안녕하세요! 다시 연락 주셔서 감사해요. 청년정책을 편하게 물어보세요."
    llm = StubLLM(unsafe, unsafe)
    monkeypatch.setattr(nodes, "_llm", llm)
    state = {
        "user_input": "안녕",
        "action": "RESPOND",
        "response_mode": "general",
        "conversation_history": [],
    }

    first = await nodes.conversation_node(state)
    first_validation = await nodes.response_validator_node({**state, **first})
    second_state = {**state, **first, **first_validation}
    second = await nodes.conversation_node(second_state)
    second_validation = await nodes.response_validator_node({**second_state, **second})
    failed_state = {**second_state, **second, **second_validation}
    fallback = await nodes.direct_response_node(failed_state)
    final_validation = await nodes.response_validator_node({**failed_state, **fallback})

    assert first_validation["response_validation_status"] == "retry"
    assert second_validation["response_validation_status"] == "failed"
    assert final_validation["response_validation_status"] == "passed"
    assert "정책나침반" in fallback["final_response"]
    assert "언제든지 말씀해 주세요" in fallback["final_response"]
    assert "다시" not in fallback["final_response"]


def test_search_bubble_rejects_profile_and_card_field_commentary():
    errors = validate_response_state(
        {
            "user_input": "금융 정책 찾아줘",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "youth_policy",
            "search_outcome": {"status": "success"},
            "youth_policy_results": [
                {
                    "policy_id": "P1",
                    "title": "정책 A",
                    "match_scope": "nationwide",
                }
            ],
            "final_response": (
                "경기 성남시에 거주하는 24세 청년을 위한 정책 카드 1건을 찾았어요. "
                "지원 내용, 자격 조건과 신청 방법을 아래 카드에서 확인하세요. "
                "전국 단위 정책이므로 신청 가능합니다.\n\n"
                "최종 신청 가능 여부는 공식 공고나 담당 기관에서 한 번 더 확인해 주세요."
            ),
        }
    )

    assert "card_detail_language_exposed" in errors


def test_unverified_card_summary_does_not_claim_a_condition_match():
    reply = compose_card_summary_reply(
        request_kind="training",
        source_status="success",
        candidates=[
            {
                "course_id": "T1",
                "title": "지역 확인 필요 과정",
                "match_scope": "unknown",
                "evidence_status": "unverified",
                "unverified_reasons": ["region_unverified"],
            }
        ],
    )

    assert "조건에 맞는" not in reply
    assert "참고 카드 1건" in reply
    assert "공식 원문" in reply


def test_unverified_card_validator_rejects_condition_match_overclaim():
    errors = validate_response_state(
        {
            "user_input": "서울 데이터 과정 찾아줘",
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "training",
            "search_outcome": {"status": "success"},
            "training_results": [
                {
                    "course_id": "T1",
                    "title": "지역 확인 필요 과정",
                    "match_scope": "unknown",
                    "evidence_status": "unverified",
                }
            ],
            "final_response": "조건에 맞는 훈련과정 카드 1건을 찾았어요. 아래 카드에서 확인해 주세요.",
        }
    )

    assert "unverified_card_overclaimed" in errors


async def test_repeated_verbose_card_summary_uses_deterministic_card_fallback(monkeypatch):
    verbose = (
        "경기 성남시에 거주하는 24세 청년을 위한 정책 카드 1건을 찾았어요. "
        "지원 내용과 신청 방법은 아래 카드에서 확인하세요."
    )
    llm = StubLLM(verbose, verbose)
    monkeypatch.setattr(nodes, "_llm", llm)
    state = {
        "user_input": "금융 정책 찾아줘",
        "action": "SEARCH",
        "response_mode": "recommend",
        "request_kind": "youth_policy",
        "search_outcome": {"status": "success"},
        "youth_policy_results": [
            {
                "policy_id": "P1",
                "title": "정책 A",
                "match_scope": "nationwide",
            }
        ],
    }

    first = await nodes.response_node(state)
    first_validation = await nodes.response_validator_node({**state, **first})
    second_state = {**state, **first, **first_validation}
    second = await nodes.response_node(second_state)
    second_validation = await nodes.response_validator_node({**second_state, **second})
    failed_state = {**second_state, **second, **second_validation}
    fallback = await nodes.direct_response_node(failed_state)
    final_validation = await nodes.response_validator_node({**failed_state, **fallback})

    assert first_validation["response_validation_status"] == "retry"
    assert second_validation["response_validation_status"] == "failed"
    assert fallback["direct_response_reason"] == "card_summary_fallback"
    assert final_validation["response_validation_status"] == "passed"
    assert "카드 1건" in fallback["final_response"]
    assert "거주" not in fallback["final_response"]
    assert "지원 내용" not in fallback["final_response"]
    assert "정책 A" not in fallback["final_response"]
    assert llm.calls == ["grounded-answer-youth_policy", "grounded-answer-youth_policy"]


async def test_repeated_bad_candidate_followup_uses_allowlisted_snapshot_fallback(monkeypatch):
    unsafe = "정책 A는 999만원을 지급해요. https://fake.example/policy"
    llm = StubLLM(unsafe, unsafe)
    monkeypatch.setattr(nodes, "_llm", llm)
    state = {
        "user_input": "1번 자세히 알려줘",
        "action": "RESPOND",
        "response_mode": "explain",
        "request_kind": "general",
        "last_presented_candidates": [
            {
                "source": "youth_policy",
                "policy_id": "P1",
                "title": "정책 A",
                "organization": "공식 기관",
                "region": "전국",
                "support_summary": "대출 한도 최대 5백만원, 금리 연 4.5% 이내",
                "detail_url": "https://official.example/policy/P1",
                "match_scope": "nationwide",
            }
        ],
    }

    first = await nodes.conversation_node(state)
    first_validation = await nodes.response_validator_node({**state, **first})
    second_state = {**state, **first, **first_validation}
    second = await nodes.conversation_node(second_state)
    second_validation = await nodes.response_validator_node({**second_state, **second})
    failed_state = {**second_state, **second, **second_validation}
    fallback = await nodes.direct_response_node(failed_state)
    final_validation = await nodes.response_validator_node({**failed_state, **fallback})

    assert first_validation["response_validation_status"] == "retry"
    assert second_validation["response_validation_status"] == "failed"
    assert fallback["direct_response_reason"] == "candidate_followup_fallback"
    assert final_validation["response_validation_status"] == "passed"
    assert "정책 A" in fallback["final_response"]
    assert "최대 5백만원" in fallback["final_response"]
    assert "https://official.example/policy/P1" in fallback["final_response"]
    assert "999만원" not in fallback["final_response"]
    assert "fake.example" not in fallback["final_response"]
    assert llm.calls == ["candidate-followup", "candidate-followup"]


@pytest.mark.parametrize(
    ("status", "prefix"),
    [
        ("no_match", "공식 조회는 완료됐지만 현재 조건에 맞는 결과는 없어요."),
        ("unavailable", "현재 조회가 어려워 검색 결과가 없다는 뜻은 아니에요."),
        ("partial", "일부 조회가 완료되지 않아 전체 결과를 단정할 수 없어요."),
    ],
)
def test_candidate_free_status_rejects_hallucinated_fact_url_and_internal_detail(status, prefix):
    errors = validate_response_state(
        {
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "training",
            "search_outcome": {"status": status, "items": []},
            "training_results": [],
            "final_response": (
                f"{prefix} 대신 월 50만원 과정을 신청하세요. https://fake.example/course EMPLOYMENT24_TRAINING_API_KEY"
            ),
        }
    )

    assert "unsupported_status_fact" in errors
    assert "unsupported_status_url" in errors
    assert "internal_status_detail_exposed" in errors


def test_candidate_free_status_rejects_internal_exclusion_counts():
    errors = validate_response_state(
        {
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "recruitment",
            "search_outcome": {"status": "no_match", "items": []},
            "recruitment_results": [],
            "final_response": "공식 조회는 완료됐지만 15건이 내부 조건에서 필터링됐어요.",
        }
    )

    assert "internal_status_detail_exposed" in errors


@pytest.mark.parametrize("status", ["no_match", "unavailable", "partial"])
async def test_repeated_unsafe_status_generation_ends_in_deterministic_fallback(monkeypatch, status):
    unsafe = {
        "no_match": "대신 월 50만원 과정을 신청하세요. https://fake.example/course API_KEY",
        "unavailable": (
            "현재 조회가 어려워 검색 결과가 없다는 뜻은 아니에요. 월 50만원 과정: https://fake.example/course API_KEY"
        ),
        "partial": (
            "일부 조회가 실패해 전체 결과를 단정할 수 없어요. 월 50만원 과정: https://fake.example/course API_KEY"
        ),
    }[status]
    llm = StubLLM(unsafe, unsafe)
    monkeypatch.setattr(nodes, "_llm", llm)
    state = {
        "user_input": "서울 데이터 과정 찾아줘",
        "action": "SEARCH",
        "response_mode": "recommend",
        "request_kind": "training",
        "search_outcome": {"status": status, "items": []},
        "search_context": {"search_query": "데이터"},
        "training_results": [],
    }

    first = await nodes.direct_response_node(state)
    first_validation = await nodes.response_validator_node({**state, **first})
    assert first_validation["response_validation_status"] == "retry"
    assert edges.route_after_verification({**state, **first, **first_validation}) == "direct_response"

    second_state = {**state, **first, **first_validation}
    second = await nodes.direct_response_node(second_state)
    second_validation = await nodes.response_validator_node({**second_state, **second})
    assert second_validation["response_validation_status"] == "failed"
    assert edges.route_after_verification({**second_state, **second, **second_validation}) == "direct_response"

    failed_state = {**second_state, **second, **second_validation}
    fallback = await nodes.direct_response_node(failed_state)
    final_validation = await nodes.response_validator_node({**failed_state, **fallback})

    assert final_validation["response_validation_status"] == "passed"
    assert fallback["direct_response_reason"] == "validation_fatal"
    assert fallback["abstention_reason"] == "answer_verification_failed"
    assert "fake.example" not in fallback["final_response"]
    assert "50만원" not in fallback["final_response"]
    assert "API_KEY" not in fallback["final_response"]
    assert llm.calls == ["search-status", "search-status"]


@pytest.mark.parametrize(
    "unsafe_reply",
    [
        "거주 지역과 만 나이, 주민등록번호를 알려주세요.",
        "거주 지역과 만 나이를 확인하려면 상세주소를 제공해 주세요.",
        "거주 지역과 만 나이 외에 계좌번호를 입력해 주세요.",
        "거주 지역과 만 나이, 전화번호 연락처가 필요해요.",
    ],
)
def test_clarification_rejects_sensitive_information_request(unsafe_reply):
    errors = validate_response_state(
        {
            "action": "SEARCH",
            "response_mode": "recommend",
            "request_kind": "youth_policy",
            "missing_slots": ["region", "age"],
            "final_response": unsafe_reply,
        }
    )

    assert "sensitive_information_requested" in errors


async def test_repeated_sensitive_clarification_ends_in_safe_template(monkeypatch):
    unsafe = "거주 지역과 만 나이, 주민등록번호와 상세주소를 알려주세요."
    llm = StubLLM(unsafe, unsafe)
    monkeypatch.setattr(nodes, "_llm", llm)
    state = {
        "user_input": "주거 정책 찾아줘",
        "action": "SEARCH",
        "response_mode": "recommend",
        "request_kind": "youth_policy",
        "missing_slots": ["region", "age"],
        "profile": {},
    }

    first = await nodes.direct_response_node(state)
    first_validation = await nodes.response_validator_node({**state, **first})
    assert first_validation["response_validation_status"] == "retry"

    second_state = {**state, **first, **first_validation}
    second = await nodes.direct_response_node(second_state)
    second_validation = await nodes.response_validator_node({**second_state, **second})
    assert second_validation["response_validation_status"] == "failed"

    failed_state = {**second_state, **second, **second_validation}
    fallback = await nodes.direct_response_node(failed_state)
    final_validation = await nodes.response_validator_node({**failed_state, **fallback})

    assert final_validation["response_validation_status"] == "passed"
    assert fallback["direct_response_reason"] == "validation_fatal"
    assert "정확한 결과를 찾으려면" in fallback["final_response"]
    assert "거주 지역" in fallback["final_response"]
    assert "만 나이" in fallback["final_response"]
    assert "주민등록번호" not in fallback["final_response"]
    assert "상세주소" not in fallback["final_response"]
    assert llm.calls == ["clarification", "clarification"]
