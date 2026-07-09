from __future__ import annotations

import json
import uuid


def test_health(client):
    res = client.get("/api/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_list_policies_returns_mock_data(client):
    res = client.get("/api/policies")
    assert res.status_code == 200
    body = res.json()
    assert len(body) > 0
    assert {"id", "title", "agency"}.issubset(body[0].keys())


def test_list_policies_filtered_by_region(client):
    res = client.get("/api/policies", params={"region": "서울"})
    assert res.status_code == 200
    for policy in res.json():
        assert "전국" in policy["region"] or "서울" in policy["region"]


def test_get_policy_by_id(client):
    all_policies = client.get("/api/policies").json()
    target_id = all_policies[0]["id"]

    res = client.get(f"/api/policies/{target_id}")
    assert res.status_code == 200
    assert res.json()["id"] == target_id


def test_get_policy_not_found(client):
    res = client.get("/api/policies/does-not-exist")
    assert res.status_code == 404


def test_search_policies_rag_lite(client):
    res = client.post("/api/policies/search", json={"query": "청년 창업 지원", "top_k": 3})
    assert res.status_code == 200
    assert len(res.json()) <= 3


def test_chat_asks_for_missing_slots_first(client):
    session_id = str(uuid.uuid4())
    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "지원사업 추천해줘"}
    )
    assert res.status_code == 200
    body = res.json()
    assert body["intent"] == "RECOMMEND"
    assert "region" in body["missing_slots"]
    assert body["recommendations"] == []


def test_chat_recommends_after_profile_complete(client):
    session_id = str(uuid.uuid4())
    message = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"

    res = client.post("/api/chat", json={"session_id": session_id, "message": message})
    assert res.status_code == 200
    body = res.json()

    assert body["missing_slots"] == []
    assert len(body["recommendations"]) > 0
    assert "반드시" not in body["reply"] or "가능성이 높아요" in body["reply"]
    assert "확인해주세요" in body["reply"]


def test_chat_persists_profile_across_turns(client):
    session_id = str(uuid.uuid4())
    client.post(
        "/api/chat", json={"session_id": session_id, "message": "서울에 살고 취업 준비 중이야"}
    )
    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "지원금 추천해줘"}
    )
    body = res.json()

    assert body["profile"]["region"] == "서울"
    assert body["missing_slots"] == []


def test_chat_out_of_scope_request(client):
    session_id = str(uuid.uuid4())
    res = client.post(
        "/api/chat", json={"session_id": session_id, "message": "세무 상담 좀 해줄 수 있어?"}
    )
    body = res.json()
    assert body["intent"] == "OUT_OF_SCOPE"


def test_chat_stream_emits_sse_events(client):
    session_id = str(uuid.uuid4())
    message = "대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?"

    with client.stream(
        "POST", "/api/chat/stream", json={"session_id": session_id, "message": message}
    ) as res:
        assert res.status_code == 200
        assert res.headers["content-type"].startswith("text/event-stream")
        body = "".join(res.iter_text())

    assert "event: token" in body
    assert "event: done" in body

    done_line = [line for line in body.splitlines() if line.startswith("data:")][-1]
    done_payload = json.loads(done_line.removeprefix("data:").strip())
    assert done_payload["type"] == "done"
    assert len(done_payload["recommendations"]) > 0
