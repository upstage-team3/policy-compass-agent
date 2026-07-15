from __future__ import annotations

import asyncio
import json
import uuid
from types import SimpleNamespace

import pytest

from app.api.routes import chat as chat_routes
from app.api.routes.chat import (
    _build_recommendations,
    _candidate_snapshot_update,
    _presented_candidate_snapshot,
    _profile_for_memory,
    _result_status_message,
    _sanitize_candidate_snapshot,
)
from app.core.session_control import SlidingWindowRateLimiter
from app.repositories.chat_memory import ChatMemoryContext


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"request_kind": "youth_policy"}, "청년정책 검색 결과를 확인했어요."),
        ({"request_kind": "training"}, "고용24 훈련과정 검색 결과를 확인했어요."),
        ({"request_kind": "recruitment"}, "채용 보조정보 검색 결과를 확인했어요."),
        ({"request_kind": "general", "intent": "EXPLAIN"}, "질문에 맞는 설명을 정리했어요."),
        ({"request_kind": "general", "intent": "OUT_OF_SCOPE"}, "지원 가능한 상담 범위를 확인했어요."),
    ],
)
def test_result_status_message_uses_router_result_and_missing_slots(result, expected):
    assert _result_status_message(result) == expected


def test_completed_turn_persists_only_durable_profile_fields():
    stored = _profile_for_memory(
        {
            "profile": {
                "age": 24,
                "region": "서울",
                "employment_status": "unemployed_seeking_job",
                "policy_topic": "금융·복지·문화",
                "preferred_support_type": "청년수당",
                "desired_job": "데이터 분석",
                "request_kind": "youth_policy",
            },
            "pending_request": {},
        }
    )

    assert stored == {
        "age": 24,
        "region": "서울",
        "employment_status": "unemployed_seeking_job",
    }


def test_pending_turn_keeps_active_profile_fields_until_resume():
    stored = _profile_for_memory(
        {
            "profile": {"region": "서울", "policy_topic": "주거", "request_kind": "youth_policy"},
            "pending_request": {"request_kind": "youth_policy", "required_slots": ["age"]},
        }
    )

    assert stored["policy_topic"] == "주거"


def test_recommendation_boundary_rejects_unfiltered_company_records():
    recommendations = _build_recommendations(
        {
            "action": "SEARCH",
            "response_validation_status": "passed",
            "search_outcome": {"status": "success"},
            "recruitment_results": [
                {"item_id": "company-1", "item_type": "company", "title": "무필터 기업정보"},
                {
                    "item_id": "event-1",
                    "item_type": "event",
                    "title": "서울 청년 채용행사",
                    "region": "서울",
                    "match_scope": "exact",
                },
            ],
        }
    )

    assert [item["policy"]["title"] for item in recommendations] == ["서울 청년 채용행사"]


def test_nearby_youth_policy_is_rendered_as_non_recommendable_reference_card():
    recommendations = _build_recommendations(
        {
            "action": "SEARCH",
            "response_validation_status": "passed",
            "search_outcome": {"status": "success"},
            "youth_policy_results": [
                {
                    "policy_id": "nearby-1",
                    "title": "인접 지역 청년정책",
                    "region": "인천",
                    "match_scope": "nearby",
                    "distance_km": 47.2,
                }
            ],
        }
    )

    assert [item["policy"]["title"] for item in recommendations] == ["인접 지역 청년정책"]
    assert recommendations[0]["is_recommendable"] is False
    assert recommendations[0]["recommendation_scope"] == "nearby_reference"


@pytest.mark.parametrize(
    ("result_key", "candidate"),
    [
        (
            "youth_policy_results",
            {
                "policy_id": "policy-unknown",
                "title": "연령 확인 필요 정책",
                "match_scope": "unknown",
                "evidence_status": "unverified",
                "unverified_reasons": ["age_unverified"],
            },
        ),
        (
            "training_results",
            {
                "course_id": "training-unknown",
                "title": "지역 확인 필요 과정",
                "match_scope": "unknown",
                "evidence_status": "unverified",
                "unverified_reasons": ["region_unverified"],
            },
        ),
        (
            "recruitment_results",
            {
                "item_id": "recruitment-unknown",
                "item_type": "event",
                "title": "경력 확인 필요 채용행사",
                "match_scope": "unknown",
                "evidence_status": "unverified",
                "unverified_reasons": ["career_unverified"],
            },
        ),
    ],
)
def test_unverified_candidates_are_returned_as_excluded_reference_cards(result_key, candidate):
    recommendations = _build_recommendations(
        {
            "action": "SEARCH",
            "response_validation_status": "passed",
            "search_outcome": {"status": "success"},
            result_key: [candidate],
        }
    )

    assert [item["policy"]["title"] for item in recommendations] == [candidate["title"]]
    assert recommendations[0]["is_recommendable"] is False
    assert recommendations[0]["recommendation_scope"] == "excluded"
    assert recommendations[0]["evidence_status"] == "unverified"
    assert recommendations[0]["unverified_reasons"] == candidate["unverified_reasons"]
    assert recommendations[0]["follow_up_checks"]
    if "career_unverified" in candidate["unverified_reasons"]:
        assert "경력 조건" in recommendations[0]["match_reasons"][0]


def test_unverified_candidate_snapshot_is_preserved_for_grounded_follow_up():
    snapshot = _presented_candidate_snapshot(
        {
            "action": "SEARCH",
            "response_validation_status": "passed",
            "search_outcome": {"status": "success"},
            "training_results": [
                {
                    "course_id": "course-unknown",
                    "title": "지역 확인 필요 과정",
                    "match_scope": "unknown",
                    "evidence_status": "unverified",
                    "unverified_reasons": ["region_unverified"],
                }
            ],
        }
    )

    assert snapshot == [
        {
            "source": "training",
            "course_id": "course-unknown",
            "title": "지역 확인 필요 과정",
            "match_scope": "unknown",
            "evidence_status": "unverified",
            "unverified_reasons": ["region_unverified"],
        }
    ]
    assert _sanitize_candidate_snapshot(snapshot) == snapshot


def test_candidate_snapshot_is_allowlisted_and_excludes_raw_payload():
    snapshot = _presented_candidate_snapshot(
        {
            "action": "SEARCH",
            "response_validation_status": "passed",
            "search_outcome": {"status": "success"},
            "search_context": {"search_query": "데이터 분석"},
            "training_results": [
                {
                    "course_id": "course-1",
                    "title": "데이터 분석 과정",
                    "region": "서울",
                    "match_scope": "exact",
                    "detail_url": "https://example.com/course-1",
                    "raw": {"internal": "payload"},
                    "unexpected": "do not persist",
                }
            ],
        }
    )

    assert snapshot == [
        {
            "source": "training",
            "search_query": "데이터 분석",
            "course_id": "course-1",
            "title": "데이터 분석 과정",
            "region": "서울",
            "detail_url": "https://example.com/course-1",
            "match_scope": "exact",
        }
    ]


def test_loaded_candidate_snapshot_rejects_legacy_guides_and_company_records():
    snapshot = _sanitize_candidate_snapshot(
        [
            {
                "source": "training",
                "course_id": "work24-training-guide",
                "title": "검색 안내",
                "match_scope": "exact",
            },
            {
                "source": "recruitment",
                "item_id": "company-1",
                "item_type": "company",
                "title": "무필터 기업정보",
                "match_scope": "exact",
            },
            {
                "source": "training",
                "course_id": "T1",
                "title": "데이터 분석 과정",
                "region": "서울",
                "match_scope": "exact",
                "detail_url": "https://example.com/T1",
                "raw": {"secret": "drop"},
            },
        ]
    )

    assert snapshot == [
        {
            "source": "training",
            "course_id": "T1",
            "title": "데이터 분석 과정",
            "region": "서울",
            "detail_url": "https://example.com/T1",
            "match_scope": "exact",
        }
    ]


def test_failed_answer_verification_never_exposes_cards_or_candidate_snapshot():
    result = {
        "action": "SEARCH",
        "response_validation_status": "failed",
        "search_outcome": {"status": "success"},
        "training_results": [
            {
                "course_id": "unsafe-1",
                "title": "검증 실패 과정",
                "region": "서울",
                "match_scope": "exact",
            }
        ],
    }

    assert _build_recommendations(result) == []
    assert _presented_candidate_snapshot(result) is None
    assert _candidate_snapshot_update(result) == []


def test_non_search_turn_preserves_previous_candidate_snapshot():
    assert _candidate_snapshot_update({"action": "RESPOND", "search_outcome": {}}) is None


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_chat_asks_for_missing_slots_first(client):
    session_id = str(uuid.uuid4())
    res = client.post("/api/chat", json={"session_id": session_id, "message": "지원사업 추천해줘"})
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "RECOMMEND"
    assert "region" in body["missing_slots"]
    assert body["recommendations"] == []


def test_chat_rejects_unsafe_session_id(client):
    res = client.post("/api/chat", json={"session_id": "../../another-session", "message": "안녕하세요"})

    assert res.status_code == 422

    predictable = client.post(
        "/api/chat",
        json={"session_id": "00000000-0000-0000-0000-000000000000", "message": "안녕하세요"},
    )
    assert predictable.status_code == 422


def test_chat_rate_limit_returns_429_with_retry_after(client, monkeypatch):
    monkeypatch.setattr(chat_routes, "_chat_rate_limiter", SlidingWindowRateLimiter())
    monkeypatch.setattr(
        chat_routes,
        "get_settings",
        lambda: SimpleNamespace(
            agent_turn_timeout_seconds=20,
            chat_session_rate_limit_per_minute=1,
            chat_ip_rate_limit_per_minute=100,
        ),
    )
    session_id = str(uuid.uuid4())

    first = client.post("/api/chat", json={"session_id": session_id, "message": "안녕하세요"})
    second = client.post("/api/chat", json={"session_id": session_id, "message": "다시 안녕하세요"})

    assert first.status_code == 200
    assert second.status_code == 429
    assert int(second.headers["retry-after"]) >= 1


def test_chat_job_seeking_question_asks_region_before_recommending(client):
    session_id = str(uuid.uuid4())
    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "취업 준비 중인데 받을 수 있는 지원금 있어?"}
    )
    assert res.status_code == 200
    body = res.json()
    assert "region" in body["missing_slots"]
    assert body["recommendations"] == []
    assert "거주 지역" in body["reply"]


def test_chat_returns_no_recommendations_without_policy_source(client):
    session_id = str(uuid.uuid4())
    message = "만 25세이고 대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"

    res = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert res.status_code == 200
    body = res.json()

    assert body["missing_slots"] == []
    assert body["recommendations"] == []
    assert body["reply"]


def test_chat_persists_profile_across_turns(client):
    session_id = str(uuid.uuid4())
    client.post("/api/chat", json={"session_id": session_id, "message": "서울에 살고 취업 준비 중이야"})
    res = client.post("/api/chat", json={"session_id": session_id, "message": "만 25세고 지원금에 관심 있어"})
    body = res.json()

    assert body["profile"]["region"] == "서울"
    assert body["missing_slots"] == []


def test_chat_explicitly_clears_a_saved_profile_field(client):
    session_id = str(uuid.uuid4())
    client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "서울에 사는 만 25세고 주거 정책이 궁금해"},
    )

    cleared = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "내 나이는 저장하지 마"},
    ).json()

    assert cleared["profile"]["age"] is None
    assert cleared["profile"]["region"] == "서울"


def test_chat_turn_timeout_returns_deterministic_response_without_cards(client, monkeypatch):
    saved: dict = {}

    class Memory:
        async def load(self, session_id):
            del session_id
            return ChatMemoryContext(profile={"region": "서울"})

        async def save_turn(self, **kwargs):
            saved.update(kwargs)

    class SlowGraph:
        async def ainvoke(self, state, config):
            del state, config
            await asyncio.sleep(1)
            raise AssertionError("timeout should cancel the graph")

    monkeypatch.setattr(chat_routes, "_chat_memory", Memory())
    monkeypatch.setattr(chat_routes, "get_agent_graph", lambda: SlowGraph())
    monkeypatch.setattr(
        chat_routes,
        "get_settings",
        lambda: SimpleNamespace(
            agent_turn_timeout_seconds=0.001,
            chat_session_rate_limit_per_minute=20,
            chat_ip_rate_limit_per_minute=120,
        ),
    )

    response = client.post(
        "/api/chat",
        json={"session_id": str(uuid.uuid4()), "message": "서울 청년정책을 찾아줘"},
    )
    body = response.json()

    assert response.status_code == 200
    assert "안전하게 중단" in body["reply"]
    assert body["recommendations"] == []
    assert saved["assistant_message"] == body["reply"]


def test_chat_uses_browser_profile_defaults_in_a_new_session(client):
    res = client.post(
        "/api/chat",
        json={
            "session_id": str(uuid.uuid4()),
            "message": "청년 주거 지원 정책에 대해 알려줘",
            "profile_defaults": {"region": "경기", "age": 24},
        },
    )
    body = res.json()

    assert res.status_code == 200
    assert body["profile"]["region"] == "경기"
    assert body["profile"]["age"] == 24
    assert body["missing_slots"] == []


def test_chat_out_of_scope_request(client):
    session_id = str(uuid.uuid4())
    res = client.post("/api/chat", json={"session_id": session_id, "message": "세무 상담 좀 해줄 수 있어?"})
    body = res.json()
    assert body["intent"] == "OUT_OF_SCOPE"
    assert "현재 범위 밖의 요청에는 답변드리기 어려워요." in body["reply"]
    assert "세무" not in body["reply"]
    assert "법률" not in body["reply"]


def test_chat_treats_startup_support_as_out_of_scope_without_external_links(client):
    res = client.post(
        "/api/chat",
        json={
            "session_id": str(uuid.uuid4()),
            "message": "서울에서 카페 창업 지원사업을 찾아줘",
        },
    )
    body = res.json()

    assert res.status_code == 200
    assert body["intent"] == "OUT_OF_SCOPE"
    assert body["missing_slots"] == []
    assert body["recommendations"] == []
    assert "현재 범위 밖의 요청에는 답변드리기 어려워요." in body["reply"]
    assert "bizinfo" not in body["reply"]
    assert "k-startup" not in body["reply"]


def test_chat_redirects_everyday_conversation_to_policy_scope(client):
    session_id = str(uuid.uuid4())
    res = client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "지금 내가 우울하다는 얘기야? 왜 나한테 우울증 상담 받아보래?",
        },
    )
    body = res.json()

    assert res.status_code == 200
    assert body["intent"] == "GENERAL"
    assert body["reply"].startswith("정책나침반은 갓 사회에 진입한 청년")
    assert "현재 범위 밖의 요청에는 답변드리기 어려워요." in body["reply"]
    assert body["reply"].endswith("이 범위에서 필요한 정보를 말씀해 주세요.")


def test_search_then_greeting_does_not_reuse_previous_results_or_disclaimer(client):
    session_id = str(uuid.uuid4())
    client.post(
        "/api/chat",
        json={
            "session_id": session_id,
            "message": "서울에서 데이터 분석 국비지원 훈련과정 찾아줘",
        },
    )

    body = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "안녕하세요"},
    ).json()

    assert body["intent"] == "GENERAL"
    assert body["recommendations"] == []
    assert body["reply"].startswith("안녕하세요!")
    assert body["reply"].endswith("언제든지 말씀해 주세요.")
    assert "청년 정책이 아닌 다른 분야" not in body["reply"]
    assert "최종 신청 가능 여부" not in body["reply"]


def test_pending_search_ignores_greeting_then_resumes_for_required_slots(client):
    session_id = str(uuid.uuid4())
    first = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "주거 정책을 찾아줘"},
    ).json()
    assert {"region", "age"}.issubset(first["missing_slots"])

    greeting = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "안녕하세요"},
    ).json()
    assert greeting["intent"] == "GENERAL"
    assert greeting["missing_slots"] == []

    resumed = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "서울에 사는 만 25세야"},
    ).json()
    assert resumed["intent"] == "RECOMMEND"
    assert resumed["missing_slots"] == []
    assert resumed["profile"]["region"] == "서울"


def test_pending_policy_search_accepts_suffix_omitted_city_and_age_in_one_turn(client):
    session_id = str(uuid.uuid4())
    first = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "금융관련 지원 정책이 있어?"},
    ).json()
    assert {"region", "age"}.issubset(first["missing_slots"])

    resumed = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "성남 거주 만 24세"},
    ).json()

    assert resumed["intent"] == "RECOMMEND"
    assert resumed["missing_slots"] == []
    assert resumed["profile"]["region"] == "경기 성남시"
    assert resumed["profile"]["age"] == 24
    assert "청년 정책이 아닌 다른 분야" not in resumed["reply"]


def test_pending_policy_search_accepts_city_then_asks_only_for_age(client):
    session_id = str(uuid.uuid4())
    client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "금융관련 지원 정책이 있어?"},
    )

    region_only = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "성남 거주"},
    ).json()

    assert region_only["intent"] == "RECOMMEND"
    assert region_only["missing_slots"] == ["age"]
    assert region_only["profile"]["region"] == "경기 성남시"
    assert "청년 정책이 아닌 다른 분야" not in region_only["reply"]


def test_chat_blocks_sensitive_identifier_before_graph_and_tracing(client, monkeypatch):
    saved: dict = {}

    class CapturingMemory:
        async def load(self, session_id):
            del session_id
            return ChatMemoryContext(profile={"region": "서울"})

        async def save_turn(self, **kwargs):
            saved.update(kwargs)

    def fail_if_called():
        raise AssertionError("민감정보 입력은 LangGraph를 실행하면 안 됩니다.")

    monkeypatch.setattr(chat_routes, "_chat_memory", CapturingMemory())
    monkeypatch.setattr(chat_routes, "get_agent_graph", fail_if_called)
    monkeypatch.setattr(chat_routes, "create_langfuse_handler", fail_if_called)

    sensitive = "991332-1234567"
    res = client.post(
        "/api/chat",
        json={"session_id": str(uuid.uuid4()), "message": sensitive},
    )
    body = res.json()

    assert res.status_code == 200
    assert body["intent"] == "PRIVACY_BLOCKED"
    assert body["recommendations"] == []
    assert "정책 검색을 중단" in body["reply"]
    assert sensitive not in body["reply"]
    assert sensitive not in saved["user_message"]
    assert saved["user_message"] == "[민감정보 삭제]"


def test_chat_stream_reports_privacy_guard_instead_of_previous_search(client):
    sensitive = "991332-1234567"

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": str(uuid.uuid4()), "message": sensitive},
    ) as res:
        body = "".join(res.iter_text())

    assert res.status_code == 200
    assert "민감정보를 감지해 입력을 보호 처리했어요." in body
    assert "정책 검색을 중단" in body
    assert sensitive not in body
    assert "평택" not in body


def test_chat_stream_emits_sse_events(client):
    session_id = str(uuid.uuid4())
    message = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"

    with client.stream("POST", "/api/chat/stream", json={"session_id": session_id, "message": message}) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        assert res.headers["cache-control"] == "no-cache, no-transform"
        assert res.headers["x-accel-buffering"] == "no"
        body = "".join(res.iter_text())

    assert "event: token" in body
    assert "event: status" in body
    assert "event: done" in body
    assert '"stage": "prepare_request"' in body
    assert '"stage": "direct_response"' in body
    assert '"stage": "verify_answer"' in body
    assert '"stage": "finalize"' in body
    assert body.index('"stage": "prepare_request"') < body.index('"stage": "finalize"')
    assert body.index('"stage": "finalize"') < body.index("event: token")

    done_line = [line for line in body.splitlines() if line.startswith("data:")][-1]
    done_payload = json.loads(done_line.removeprefix("data:").strip())
    assert done_payload["type"] == "done"
    assert done_payload["recommendations"] == []
    assert done_payload["profile_defaults"]["region"] == "서울"
    assert done_payload["profile_defaults"]["age"] is None


def test_chat_stream_emits_safe_error_event_when_agent_fails(client, monkeypatch):
    async def fail_agent(_payload):
        if False:  # pragma: no cover - make this an async generator
            yield {}
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(chat_routes, "_stream_agent", fail_agent)

    with client.stream(
        "POST",
        "/api/chat/stream",
        json={"session_id": str(uuid.uuid4()), "message": "서울 청년정책 찾아줘"},
    ) as res:
        body = "".join(res.iter_text())

    assert res.status_code == 200
    assert "event: error" in body
    assert "일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요." in body
    assert "simulated failure" not in body


@pytest.mark.asyncio
async def test_node_status_arrives_before_graph_finishes_and_hides_unverified_draft(monkeypatch):
    release_graph = asyncio.Event()
    saved: dict = {}

    class Memory:
        async def load(self, session_id):
            del session_id
            return ChatMemoryContext()

        async def save_turn(self, **kwargs):
            saved.update(kwargs)

    class DelayedGraph:
        async def ainvoke(self, state, config):
            del state, config
            raise AssertionError("SSE path must use astream, not ainvoke")

        async def astream(self, state, config, *, stream_mode):
            assert config["run_name"] == "policy-compass-chat"
            assert stream_mode == ["updates", "values"]
            current = dict(state)
            yield "values", current

            route_update = {
                "intent": "GENERAL",
                "action": "RESPOND",
                "response_mode": "general",
                "request_kind": "general",
                "missing_slots": [],
            }
            current.update(route_update)
            yield "updates", {"prepare_request": route_update}
            yield "values", dict(current)

            await release_graph.wait()

            draft_update = {"final_response": "검증 전 비공개 초안"}
            current.update(draft_update)
            yield "updates", {"direct_response": draft_update}
            yield "values", dict(current)

            validation_update = {
                "response_validation_status": "passed",
                "response_validation_errors": [],
            }
            current.update(validation_update)
            yield "updates", {"verify_answer": validation_update}
            yield "values", dict(current)

            final_update = {
                "final_response": "검증된 최종 답변",
                "conversation_history": [
                    {"role": "user", "content": "안녕하세요"},
                    {"role": "assistant", "content": "검증된 최종 답변"},
                ],
            }
            current.update(final_update)
            yield "updates", {"finalize": final_update}
            yield "values", dict(current)

    monkeypatch.setattr(chat_routes, "_chat_memory", Memory())
    monkeypatch.setattr(chat_routes, "get_agent_graph", lambda: DelayedGraph())
    monkeypatch.setattr(chat_routes, "get_langfuse_client", lambda: None)
    monkeypatch.setattr(chat_routes, "create_langfuse_handler", lambda **_kwargs: None)

    payload = chat_routes.ChatRequest(session_id=str(uuid.uuid4()), message="안녕하세요")
    stream = chat_routes._stream_agent(payload)

    first_event = await anext(stream)
    assert first_event == {
        "type": "status",
        "stage": "prepare_request",
        "message": "질문 의도와 대화 맥락을 확인했어요.",
    }

    pending_event = asyncio.create_task(anext(stream))
    await asyncio.sleep(0)
    assert not pending_event.done()

    release_graph.set()
    events = [await pending_event]
    events.extend([event async for event in stream])

    assert [event["stage"] for event in events if event["type"] == "status"] == [
        "direct_response",
        "verify_answer",
        "finalize",
    ]
    serialized_events = json.dumps([first_event, *events], ensure_ascii=False)
    assert "검증 전 비공개 초안" not in serialized_events
    assert events[-1]["type"] == "result"
    assert events[-1]["result"]["final_response"] == "검증된 최종 답변"
    assert saved["assistant_message"] == "검증된 최종 답변"


def test_chat_training_question_returns_training_fallback(client):
    session_id = str(uuid.uuid4())
    message = "서울에서 데이터 분석 쪽으로 취업 준비 중인데 국비지원 훈련과정 찾아줘"

    res = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert res.status_code == 200
    body = res.json()

    assert body["intent"] == "RECOMMEND"
    assert body["missing_slots"] == []
    assert "고용24" in body["reply"]
    assert "훈련과정" in body["reply"]


def test_chat_training_benefit_question_uses_explanation_not_search(client):
    session_id = str(uuid.uuid4())
    message = "국비지원 훈련을 받으면 뭐가 좋아?"

    res = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert res.status_code == 200
    body = res.json()

    assert body["intent"] == "EXPLAIN"
    assert body["missing_slots"] == []
    assert "장점" in body["reply"]
    assert "상세 URL" not in body["reply"]


def test_chat_recruitment_question_returns_permission_fallback(client):
    session_id = str(uuid.uuid4())
    message = "고용24에서 신입 채용공고 바로 찾아줄 수 있어?"

    res = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert res.status_code == 200
    body = res.json()

    assert body["intent"] == "RECOMMEND"
    assert "desired_job" not in body["reply"]
    assert "고용24 채용행사·공채속보" in body["reply"]
    assert "관심 직무" not in body["reply"]
    assert "근무를 희망하는 지역" not in body["reply"]


def test_chat_resumes_original_policy_request_after_slot_answer(client):
    session_id = str(uuid.uuid4())
    first = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "거주지원을 받고 싶은데 관련 정책 있어?"},
    ).json()
    assert {"region", "age"}.issubset(first["missing_slots"])
    assert "status" not in first["missing_slots"]

    second = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "서울에 사는 만 25세 취업 준비생이야"},
    ).json()

    assert second["missing_slots"] == []
    assert second["profile"]["region"] == "서울"
    assert "입력하신 조건에 맞는 지원사업" not in second["reply"]


def test_chat_broad_policy_request_then_housing_topic_never_requires_job_or_startup_status(client):
    session_id = str(uuid.uuid4())
    first = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "청년 지원 정책에 대한 정보를 얻고 싶어"},
    ).json()

    assert {"region", "age", "policy_topic"}.issubset(first["missing_slots"])
    assert "status" not in first["missing_slots"]

    second = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "서울 만 24세"},
    ).json()

    assert second["missing_slots"] == ["policy_topic"]
    assert "취업 준비" not in second["reply"]
    assert "창업" not in second["reply"]

    third = client.post(
        "/api/chat",
        json={"session_id": session_id, "message": "거주지원 정책 정보를 원해"},
    ).json()

    assert third["missing_slots"] == []
    assert third["profile"]["policy_topic"] == "주거"
