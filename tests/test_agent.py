from __future__ import annotations

from datetime import date

from app.graph import nodes
from app.graph.scoring import deadline_status, score_policy
from app.repositories.policy import _normalize_bizinfo_item, _normalize_bizinfo_items


def test_heuristic_route_recommend():
    assert nodes._heuristic_route("취업 준비 중인데 받을 수 있는 지원금 있어?") == "RECOMMEND"


def test_heuristic_route_eligibility_check():
    assert nodes._heuristic_route("이 사업 자격 되나요?") == "ELIGIBILITY_CHECK"


def test_heuristic_route_out_of_scope():
    assert nodes._heuristic_route("세무 상담 좀 해줄 수 있어?") == "OUT_OF_SCOPE"


def test_heuristic_route_general():
    assert nodes._heuristic_route("안녕하세요") == "GENERAL"


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


async def test_missing_slot_node_flags_missing_region():
    state = {"profile": {"employment_status": "unemployed_seeking_job"}}
    result = await nodes.missing_slot_node(state)
    assert "region" in result["missing_slots"]
    assert "status" not in result["missing_slots"]


async def test_missing_slot_node_no_missing_when_complete():
    state = {"profile": {"region": "서울", "employment_status": "unemployed_seeking_job"}}
    result = await nodes.missing_slot_node(state)
    assert result["missing_slots"] == []


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
    assert "확인해주세요" in result["final_response"]
    assert result["guardrail_notes"]


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
