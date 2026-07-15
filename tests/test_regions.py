from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.administrative_regions import MUNICIPALITY_ROWS
from app.core.regions import (
    SIDO_CODE_PREFIXES,
    region_distance_km,
    region_match_scope,
    resolve_region,
    user_region_reference,
    youth_policy_region_scope,
)
from app.graph import nodes
from app.graph.fallbacks import heuristic_extract_profile
from app.graph.response_composer import compose_card_summary_reply
from app.repositories.youthcenter import (
    YouthCenterRepository,
    _filter_active_youth_policies,
    _filter_youth_policies_by_region,
    normalize_youth_policy_json,
)
from app.tools.schemas import YouthPolicyItem, YouthPolicySearchInput


def test_resolve_sigungu_to_sido_and_official_code():
    resolved = resolve_region("성남시")

    assert resolved is not None
    assert resolved.sido == "경기"
    assert resolved.sigungu == "성남시"
    assert resolved.youth_code == "41130"


def test_region_correction_prefers_replacement_target():
    assert user_region_reference("경기도 말고 서울로") == "서울"
    assert user_region_reference("서울이 아니라 부산으로") == "부산"


@pytest.mark.parametrize(
    "query",
    ["성남 거주", "성남거주", "성남 거주 만 24세", "성남에 살아요", "성남 만 24세"],
)
def test_suffix_omitted_municipality_is_recognized_inside_user_sentence(query):
    assert user_region_reference(query) == "경기 성남시"


def test_ambiguous_suffix_omitted_municipality_is_not_guessed_inside_sentence():
    assert user_region_reference("고성 거주") == "고성"
    assert resolve_region(user_region_reference("고성 거주")) is None


@pytest.mark.parametrize(
    "query",
    [
        "창의성 교육 정책",
        "창의성 거주 공간 지원",
        "창의성 거주지원 정책",
        "고령 청년 지원 정책",
        "예산 지원 정책",
        "진도율 개선 교육",
        "화성 탐사 교육",
        "구리 가격 지원",
        "부여하는 지원금",
    ],
)
def test_suffix_omitted_municipality_does_not_match_ordinary_korean_substrings(query):
    assert user_region_reference(query) is None


@pytest.mark.parametrize(
    ("query", "sido", "code"),
    [
        ("해운대구", "부산", "26350"),
        ("부산광역시 해운대구", "부산", "26350"),
        ("강원특별자치도 고성군", "강원", "51820"),
        ("경상남도 고성군", "경남", "48820"),
        ("전주시", "전북", "52110"),
        ("청주시 흥덕구", "충북", "43113"),
        ("인천광역시 서해구", "인천", "28275"),
        ("전남광주통합특별시 순천시", "전남광주", "12150"),
        ("세종시", "세종", "36110"),
    ],
)
def test_resolve_official_municipalities_nationwide(query, sido, code):
    resolved = resolve_region(query)

    assert resolved is not None
    assert resolved.sido == sido
    assert resolved.youth_code == code


def test_official_municipality_snapshot_is_complete_and_ambiguous_names_are_not_guessed():
    assert len(MUNICIPALITY_ROWS) == 300
    assert len({code for _, code, _ in MUNICIPALITY_ROWS}) == 300
    assert resolve_region("고성군") is None
    assert resolve_region("중구") is None


def test_every_official_municipality_resolves_with_its_sido_context():
    for sido, code, name in MUNICIPALITY_ROWS:
        resolved = resolve_region(f"{sido} {name}")

        assert resolved is not None, (sido, code, name)
        assert resolved.sido == sido, (sido, code, name, resolved)
        assert resolved.youth_code == code, (sido, code, name, resolved)


def test_region_matching_understands_city_to_province_and_nearby_distance():
    assert region_match_scope("성남시", ["경기"]) == "exact"
    assert region_match_scope("성남시", ["전국"]) == "nationwide"
    assert region_match_scope("성남시", ["인천"]) == "mismatch"

    distances = [
        region_distance_km("성남시", ["인천"]),
        region_distance_km("성남시", ["충남"]),
        region_distance_km("성남시", ["부산"]),
    ]
    assert all(distance is not None for distance in distances)
    assert distances == sorted(distances)
    assert region_match_scope("순천시", ["광주"]) == "exact"


def test_youth_region_filter_does_not_restore_other_regions_for_sigungu():
    items = [
        YouthPolicyItem(policy_id="seongnam", title="성남 정책", region="경기", raw={"zipCd": "41130"}),
        YouthPolicyItem(policy_id="incheon", title="인천 정책", region="인천", raw={"zipCd": "28237"}),
        YouthPolicyItem(policy_id="all", title="전국 정책", region="전국", raw={"zipCd": "11110,41130"}),
    ]

    filtered = _filter_youth_policies_by_region(items, "성남시")

    assert [item.policy_id for item in filtered] == ["seongnam", "all"]


def test_youth_region_scope_does_not_treat_municipal_policy_as_province_wide():
    assert youth_policy_region_scope("경기", "41220", "평택시") == "unknown"
    assert youth_policy_region_scope("평택시", "41220", "평택시") == "exact"


def test_youth_region_scope_distinguishes_municipalities_in_the_same_province():
    assert youth_policy_region_scope("성남시", "41110", "수원시") == "mismatch"
    assert youth_policy_region_scope("성남시", "41135", "성남시 분당구") == "exact"


async def test_missing_slot_requests_sido_when_municipality_name_is_ambiguous():
    result = await nodes.missing_slot_node(
        {
            "request_kind": "youth_policy",
            "response_mode": "recommend",
            "profile": {
                "region": "고성군",
                "age": 25,
                "policy_topic": "주거",
            },
        }
    )

    assert result["missing_slots"] == ["region_detail"]


async def test_profile_extractor_does_not_accept_llm_inferred_sido_for_ambiguous_region(monkeypatch):
    class FakeLLM:
        is_configured = True

        async def complete(self, *args, **kwargs):
            del args, kwargs
            return '{"age":25,"region":"강원 고성군","policy_topic":"주거"}'

    monkeypatch.setattr(nodes, "_llm", FakeLLM())

    result = await nodes.profile_extractor_node(
        {
            "user_input": "고성군에 사는 만 25세 청년이야. 주거 정책 찾아줘",
            "profile": {},
            "request_kind": "youth_policy",
            "conversation_history": [],
        }
    )

    assert result["profile"]["region"] == "고성군"
    missing = await nodes.missing_slot_node(
        {
            "request_kind": "youth_policy",
            "response_mode": "recommend",
            "profile": result["profile"],
            "search_query": "주거",
        }
    )
    assert missing["missing_slots"] == ["region_detail"]


def test_fallback_profile_extractor_supports_official_municipalities_nationwide():
    profile = heuristic_extract_profile("부산 해운대구에 사는 만 25세 청년")

    assert profile["region"] == "부산 해운대구"


def test_youth_normalizer_does_not_treat_local_government_policy_as_nationwide():
    nationwide_codes = ",".join(f"{prefix}110" for prefix in SIDO_CODE_PREFIXES.values())
    payload = {
        "result": {
            "youthPolicyList": [
                {
                    "plcyNo": "local",
                    "plcyNm": "청년단기주거공간 운영",
                    "zipCd": nationwide_codes,
                    "sprvsnInstCdNm": "경상북도 의성군 관광복지국",
                    "rgtrInstCdNm": "경상북도 의성군 관광복지국",
                    "rgtrHghrkInstCdNm": "경상북도",
                },
                {
                    "plcyNo": "national",
                    "plcyNm": "주거포털 개선",
                    "zipCd": nationwide_codes,
                    "sprvsnInstCdNm": "국토교통부",
                    "rgtrInstCdNm": "국토교통부",
                    "sprtTrgtAgeLmtYn": "Y",
                    "sprtTrgtMinAge": "0",
                    "sprtTrgtMaxAge": "0",
                },
            ]
        }
    }

    local, national = normalize_youth_policy_json(payload)

    assert local.region == "경북"
    assert youth_policy_region_scope("성남시", str(local.raw["zipCd"]), local.region) == "mismatch"
    assert national.region == "전국"
    assert youth_policy_region_scope("성남시", str(national.raw["zipCd"]), national.region) == "nationwide"
    assert national.target_summary == "연령 제한 없음"


def test_youth_active_filter_rejects_closed_application_period_without_business_end_date():
    items = [
        YouthPolicyItem(
            policy_id="closed",
            title="접수 종료 정책",
            application_period="20250523 ~ 20250623",
        ),
        YouthPolicyItem(
            policy_id="ongoing",
            title="상시 정책",
            business_period="연중",
        ),
    ]

    active = _filter_active_youth_policies(items, today=date(2026, 7, 14))

    assert [item.policy_id for item in active] == ["ongoing"]


async def test_youth_search_returns_nearby_references_in_distance_order(monkeypatch):
    repository = YouthCenterRepository()
    repository._settings = SimpleNamespace(
        youthcenter_policy_api_key="test-key",
        youthcenter_policy_api_url="https://example.com/youth",
    )
    calls: list[dict[str, str]] = []

    async def fake_fetch(client, api_url, params):
        del client, api_url
        calls.append(params)
        if params.get("zipCd") == "41130":
            return []
        return [
            YouthPolicyItem(policy_id="busan", title="부산 정책", region="부산", raw={"zipCd": "26110"}),
            YouthPolicyItem(policy_id="chungnam", title="충남 정책", region="충남", raw={"zipCd": "44270"}),
            YouthPolicyItem(policy_id="incheon", title="인천 정책", region="인천", raw={"zipCd": "28237"}),
        ]

    monkeypatch.setattr(repository, "_fetch", fake_fetch)

    results = await repository.search(YouthPolicySearchInput(region="성남시", keywords="주거", page_size=10))

    assert calls[0]["zipCd"] == "41130"
    assert [item.policy_id for item in results] == ["incheon", "chungnam", "busan"]
    assert all(item.match_scope == "nearby" for item in results)
    assert [item.distance_km for item in results] == sorted(item.distance_km for item in results)


async def test_youth_narrow_search_does_not_return_other_region_references(monkeypatch):
    repository = YouthCenterRepository()
    repository._settings = SimpleNamespace(
        youthcenter_policy_api_key="test-key",
        youthcenter_policy_api_url="https://example.com/youth",
    )

    async def fake_fetch(client, api_url, params):
        del client, api_url, params
        return [
            YouthPolicyItem(
                policy_id="gwangju-rent",
                title="광주 청년 월세 지원",
                region="광주",
                raw={"zipCd": "29110"},
            )
        ]

    monkeypatch.setattr(repository, "_fetch", fake_fetch)

    results = await repository.search(YouthPolicySearchInput(region="경기", keywords="월세", page_size=10))

    assert results == []


async def test_youth_search_uses_official_code_for_non_gyeonggi_municipality(monkeypatch):
    repository = YouthCenterRepository()
    repository._settings = SimpleNamespace(
        youthcenter_policy_api_key="test-key",
        youthcenter_policy_api_url="https://example.com/youth",
    )
    calls: list[dict[str, str]] = []

    async def fake_fetch(client, api_url, params):
        del client, api_url
        calls.append(params)
        if params.get("zipCd") == "26350":
            return [
                YouthPolicyItem(
                    policy_id="haeundae",
                    title="해운대 청년정책",
                    region="해운대구",
                    raw={"zipCd": "26350"},
                )
            ]
        return []

    monkeypatch.setattr(repository, "_fetch", fake_fetch)

    results = await repository.search(YouthPolicySearchInput(region="해운대구", keywords="주거", page_size=10))

    assert calls[0]["zipCd"] == "26350"
    assert [item.policy_id for item in results] == ["haeundae"]
    assert results[0].match_scope == "exact"


def test_youth_nearby_card_summary_labels_results_as_reference():
    response = compose_card_summary_reply(
        request_kind="youth_policy",
        source_status="success",
        candidates=[
            YouthPolicyItem(
                policy_id="incheon",
                title="인천 정책",
                region="인천",
                match_scope="nearby",
                distance_km=47.2,
            ).model_dump()
        ],
    )

    assert "가까운 지역" in response
    assert "참고 카드 1건" in response
    assert "거주 요건" in response
    assert "인천 정책" not in response
