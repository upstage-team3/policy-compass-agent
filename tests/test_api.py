from __future__ import annotations

import json
import uuid

import pytest

from app.api.routes import chat as chat_routes
from app.api.routes.chat import _result_status_message


@pytest.mark.parametrize(
    ("result", "expected"),
    [
        ({"request_kind": "youth_policy"}, "청년정책 검색 결과를 확인했어요."),
        ({"request_kind": "training"}, "고용24 훈련과정 검색 결과를 확인했어요."),
        ({"request_kind": "recruitment"}, "채용 보조정보 검색 결과를 확인했어요."),
        (
            {"request_kind": "business", "missing_slots": ["region"]},
            "기업마당 지원사업 추천에 필요한 조건을 정리했어요.",
        ),
        ({"request_kind": "general", "intent": "EXPLAIN"}, "질문에 맞는 설명을 정리했어요."),
        ({"request_kind": "general", "intent": "OUT_OF_SCOPE"}, "지원 가능한 상담 범위를 확인했어요."),
    ],
)
def test_result_status_message_uses_router_result_and_missing_slots(result, expected):
    assert _result_status_message(result) == expected


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_policies_returns_empty_without_real_source(client):
    res = client.get("/api/policies")
    assert res.status_code == 200
    assert res.json() == []


def test_list_policies_filtered_by_region(client):
    res = client.get("/api/policies", params={"region": "서울"})
    assert res.status_code == 200
    for policy in res.json():
        assert "전국" in policy["region"] or "서울" in policy["region"]


def test_get_policy_not_found(client):
    res = client.get("/api/policies/does-not-exist")
    assert res.status_code == 404


def test_search_policies_rag_lite(client):
    res = client.post("/api/policies/search", json={"query": "청년 창업 지원", "top_k": 3})
    assert res.status_code == 200
    assert len(res.json()) <= 3


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


def test_chat_stream_emits_sse_events(client):
    session_id = str(uuid.uuid4())
    message = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"

    with client.stream("POST", "/api/chat/stream", json={"session_id": session_id, "message": message}) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        body = "".join(res.iter_text())

    assert "event: token" in body
    assert "event: status" in body
    assert "event: done" in body
    assert "청년정책 추천에 필요한 조건을 정리했어요." in body

    done_line = [line for line in body.splitlines() if line.startswith("data:")][-1]
    done_payload = json.loads(done_line.removeprefix("data:").strip())
    assert done_payload["type"] == "done"
    assert done_payload["recommendations"] == []
    assert done_payload["profile_defaults"]["region"] == "서울"


def test_chat_stream_emits_safe_error_event_when_agent_fails(client, monkeypatch):
    async def fail_agent(_payload):
        raise RuntimeError("simulated failure")

    monkeypatch.setattr(chat_routes, "_run_agent", fail_agent)

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
    assert "관심 직무" in body["reply"]
    assert "근무를 희망하는 지역" in body["reply"]


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
