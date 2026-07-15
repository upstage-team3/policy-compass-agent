from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import pytest

from app.core.administrative_regions import MUNICIPALITY_ROWS
from app.core.regions import (
    BIZINFO_REGION_TAGS,
    SIDO_CODE_PREFIXES,
    bizinfo_effective_regions,
    bizinfo_region_tag,
    normalize_bizinfo_regions,
    region_distance_km,
    region_match_scope,
    resolve_region,
    user_region_reference,
    youth_policy_region_scope,
)
from app.graph import nodes
from app.graph.fallbacks import heuristic_extract_profile
from app.graph.response_composer import compose_scored_template, compose_youth_policy_response
from app.graph.scoring import score_policy
from app.repositories.policy import (
    PolicyRepository,
    _infer_business_registration_requirement,
    _normalize_bizinfo_item,
)
from app.repositories.youthcenter import (
    YouthCenterRepository,
    _filter_active_youth_policies,
    _filter_youth_policies_by_region,
    normalize_youth_policy_json,
)
from app.tools.schemas import PolicySearchInput, YouthPolicyItem, YouthPolicySearchInput


def _business_policy(*, region: list[str], match_scope: str = "exact") -> dict:
    return {
        "id": "biz-1",
        "title": "창업 지원사업",
        "agency": "테스트 기관",
        "category": "창업",
        "target_description": "예비창업자",
        "region": region,
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": True,
        "requires_business_registration": None,
        "apply_start": None,
        "apply_end": None,
        "apply_method": "공고 확인",
        "support_content": "사업화 지원",
        "source_url": "https://example.com",
        "match_scope": match_scope,
        "distance_km": 20.0 if match_scope == "nearby" else None,
    }


def test_resolve_sigungu_to_sido_and_official_code():
    resolved = resolve_region("성남시")

    assert resolved is not None
    assert resolved.sido == "경기"
    assert resolved.sigungu == "성남시"
    assert resolved.youth_code == "41130"
    assert bizinfo_region_tag("성남시") == "경기"


def test_region_correction_prefers_replacement_target():
    assert user_region_reference("경기도 말고 서울로") == "서울"
    assert user_region_reference("서울이 아니라 부산으로") == "부산"


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


def test_bizinfo_combined_and_nationwide_tags_are_normalized_without_guessing():
    assert normalize_bizinfo_regions("전남광주,창업") == ["광주", "전남"]
    assert normalize_bizinfo_regions(",".join(BIZINFO_REGION_TAGS)) == ["전국"]
    assert normalize_bizinfo_regions(
        "서울,부산,대구,인천,광주,대전,울산,세종,경기,강원,충북,충남,전북,전남,경북,경남,제주"
    ) == ["전국"]
    assert normalize_bizinfo_regions("2026,창업,AI") == []
    assert bizinfo_region_tag("해운대구") == "부산"
    assert bizinfo_region_tag("전주시") == "전북"
    assert bizinfo_region_tag("전남광주통합특별시 순천시") == "전남광주"


def test_bizinfo_nationwide_tags_are_overridden_by_explicit_local_eligibility():
    all_tags = ",".join(BIZINFO_REGION_TAGS)

    assert bizinfo_effective_regions(
        all_tags,
        title="구미시 New Venture 창업지원사업",
        summary="구미 소재 또는 구미로 본사 이전 예정인 창업기업",
        agency="경상북도",
    ) == ["경북"]
    assert bizinfo_effective_regions(
        all_tags,
        title="서울 TIPS 투자 연계 컨설팅",
        summary="서울 소재 창업 7년 미만 기업 또는 서울로 본사 이전이 가능한 기업",
        agency="서울특별시",
    ) == ["서울"]
    assert bizinfo_effective_regions(
        all_tags,
        title="부산 창업투자경진대회",
        summary="부산광역시가 주최하며 창업 5년 이내 업체는 지역제한 없음",
        agency="부산광역시",
    ) == ["전국"]
    assert bizinfo_effective_regions(
        "부산",
        title="부산 창업투자경진대회",
        summary="창업 5년 이내 업체(지역제한 없음)",
        agency="부산광역시",
    ) == ["전국"]


def test_bizinfo_institution_names_alone_do_not_create_local_restriction():
    all_tags = ",".join(BIZINFO_REGION_TAGS)

    assert bizinfo_effective_regions(
        all_tags,
        title="딥테크 특화 창업중심대학",
        summary="광주과학기술원, 대구경북과학기술원, 울산과학기술원 소속 창업기업을 지원",
        agency="중소벤처기업부",
    ) == ["전국"]


def test_bizinfo_registration_requirement_is_inferred_only_from_explicit_target_text():
    assert _infer_business_registration_requirement("창업 5년 이내 업체") is True
    assert _infer_business_registration_requirement("업력 7년 이내 딥테크 스타트업") is True
    assert _infer_business_registration_requirement("사업자등록을 하지 않은 예비창업자") is False
    assert _infer_business_registration_requirement("예비창업자 또는 창업 7년 이내 기업") is None
    assert _infer_business_registration_requirement("창업 아이디어를 보유한 청년") is None


def test_bizinfo_normalization_exposes_registration_requirement_to_scorer():
    normalized = _normalize_bizinfo_item(
        {
            "pblancId": "registered-only",
            "pblancNm": "창업기업 지원",
            "bsnsSumryCn": "공고일 기준 창업 5년 이내 업체를 지원합니다.",
            "hashtags": ",".join(BIZINFO_REGION_TAGS),
        }
    )

    assert normalized["requires_business_registration"] is True


@pytest.mark.parametrize(
    ("query", "expected_tag"),
    [
        ("서울 강남구", "서울"),
        ("부산 해운대구", "부산"),
        ("대구 달서구", "대구"),
        ("인천 연수구", "인천"),
        ("전남광주 순천시", "전남광주"),
        ("대전 유성구", "대전"),
        ("울산 남구", "울산"),
        ("세종시", "세종"),
        ("경기 성남시", "경기"),
        ("강원 춘천시", "강원"),
        ("충북 청주시", "충북"),
        ("충남 천안시", "충남"),
        ("전북 전주시", "전북"),
        ("경북 포항시", "경북"),
        ("경남 창원시", "경남"),
        ("제주 제주시", "제주"),
    ],
)
def test_bizinfo_region_labels_cover_every_supported_api_tag(query, expected_tag):
    repository = PolicyRepository()

    params = repository._build_params(PolicySearchInput(region=query))

    assert params["hashtags"] == expected_tag


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


def test_bizinfo_params_use_supported_region_tag_and_unknown_is_not_nationwide():
    repository = PolicyRepository()

    seongnam = repository._build_params(PolicySearchInput(region="성남시", keywords="창업"))
    gwangju = repository._build_params(PolicySearchInput(region="광주광역시", keywords="창업"))
    normalized = _normalize_bizinfo_item({"pblancId": "unknown", "pblancNm": "지역 확인 사업", "hashTags": "2026,창업"})

    assert seongnam["hashtags"] == "경기"
    assert gwangju["hashtags"] == "전남광주"
    assert normalized["region"] == []
    assert repository._build_params(PolicySearchInput(region="해운대구"))["hashtags"] == "부산"
    assert repository._build_params(PolicySearchInput(region="전주시"))["hashtags"] == "전북"
    assert repository._build_params(PolicySearchInput(region="해운대구", limit=10))["searchCnt"] == "50"


async def test_bizinfo_search_combines_registration_filter_and_interest_ranking(monkeypatch):
    repository = PolicyRepository()
    registered_only = {
        **_business_policy(region=["부산"]),
        "id": "registered",
        "requires_business_registration": True,
    }
    generic = {
        **_business_policy(region=["전국"]),
        "id": "generic",
        "support_content": "일반 창업 교육",
        "requires_business_registration": None,
    }
    food = {
        **_business_policy(region=["전국"]),
        "id": "food",
        "support_content": "농식품 분야 사업화 지원",
        "requires_business_registration": None,
    }

    async def fake_all_policies(query):
        return [registered_only, generic, food]

    monkeypatch.setattr(repository, "_all_policies", fake_all_policies)

    results = await repository.search(
        PolicySearchInput(
            region="해운대구",
            is_entrepreneur=True,
            has_registered_business=False,
            interest_fields=["요식업"],
            limit=5,
        )
    )

    assert [item.id for item in results] == ["food", "generic"]


async def test_bizinfo_search_uses_nearby_regions_only_after_exact_scope_is_empty(monkeypatch):
    repository = PolicyRepository()
    calls: list[str | None] = []

    async def fake_all_policies(query):
        calls.append(query.region)
        if query.region == "성남시":
            return []
        return [{**_business_policy(region=[query.region]), "id": f"biz-{query.region}"}]

    monkeypatch.setattr(repository, "_all_policies", fake_all_policies)

    results = await repository.search(
        PolicySearchInput(region="성남시", is_entrepreneur=True, keywords="창업", limit=5)
    )

    assert calls[0] == "성남시"
    assert len(results) == 3
    assert all(item.match_scope == "nearby" for item in results)
    assert [item.distance_km for item in results] == sorted(item.distance_km for item in results)


async def test_bizinfo_search_removes_mismatched_and_unknown_regions_from_primary_results(monkeypatch):
    repository = PolicyRepository()
    calls: list[str | None] = []

    async def fake_all_policies(query):
        calls.append(query.region)
        return [
            {**_business_policy(region=["경기"]), "id": "exact"},
            {**_business_policy(region=["전국"]), "id": "nationwide"},
            {**_business_policy(region=["부산"]), "id": "mismatch"},
            {**_business_policy(region=[]), "id": "unknown"},
        ]

    monkeypatch.setattr(repository, "_all_policies", fake_all_policies)

    results = await repository.search(
        PolicySearchInput(region="성남시", is_entrepreneur=True, keywords="창업", limit=5)
    )

    assert calls == ["성남시"]
    assert [(item.id, item.match_scope) for item in results] == [
        ("exact", "exact"),
        ("nationwide", "nationwide"),
    ]


def test_scoring_uses_canonical_region_and_rejects_unknown_or_nearby_as_recommendation():
    profile = {"region": "성남시", "is_entrepreneur": True}
    exact = score_policy(profile, _business_policy(region=["경기"]))
    unknown = score_policy(profile, _business_policy(region=[]))
    nearby = score_policy(profile, _business_policy(region=["인천"], match_scope="nearby"))

    assert exact["is_recommendable"] is True
    assert exact["match_score"] > 0
    assert unknown["is_recommendable"] is False
    assert unknown["match_score"] == 0
    assert nearby["is_recommendable"] is False
    assert nearby["recommendation_scope"] == "nearby_reference"


def test_scoring_does_not_inflate_sparse_policy_to_full_score():
    profile = {"region": "성남시", "is_entrepreneur": True}

    result = score_policy(profile, _business_policy(region=["경기"]))

    assert result["match_score"] == 0.4
    assert result["evidence_coverage"] == 0.4
    assert result["match_score"] < 1.0


def test_scoring_rewards_more_verified_matching_evidence():
    sparse_policy = _business_policy(region=["경기"])
    detailed_policy = {
        **sparse_policy,
        "min_age": 19,
        "max_age": 39,
        "target_employment_status": ["unemployed_seeking_job"],
        "requires_business_registration": False,
        "apply_end": "2026-12-31",
    }
    profile = {
        "region": "성남시",
        "age": 25,
        "employment_status": "unemployed_seeking_job",
        "is_entrepreneur": True,
        "has_registered_business": False,
        "interest_fields": ["사업화"],
    }

    sparse = score_policy(profile, sparse_policy, today=date(2026, 7, 14))
    detailed = score_policy(profile, detailed_policy, today=date(2026, 7, 14))

    assert sparse["match_score"] == 0.6
    assert sparse["evidence_coverage"] == 0.6
    assert detailed["match_score"] == 1.0
    assert detailed["evidence_coverage"] == 1.0
    assert detailed["match_score"] > sparse["match_score"]


def test_scoring_recognizes_interest_synonyms_and_ranks_relevant_policy_first():
    profile = {"region": "해운대구", "is_entrepreneur": True, "interest_fields": ["요식업"]}
    relevant_policy = {**_business_policy(region=["전국"]), "support_content": "농식품 사업화 자금 지원"}
    unrelated_policy = {**_business_policy(region=["전국"]), "support_content": "AI 반도체 기술 지원"}

    relevant = score_policy(profile, relevant_policy)
    unrelated = score_policy(profile, unrelated_policy)

    assert any("관심 분야" in reason for reason in relevant["match_reasons"])
    assert relevant["match_score"] > unrelated["match_score"]


def test_scoring_uses_nationwide_region_resolution_outside_gyeonggi():
    profile = {"region": "해운대구", "is_entrepreneur": True}
    exact = score_policy(profile, _business_policy(region=["부산"]))
    mismatch = score_policy(profile, _business_policy(region=["전북"]))

    assert exact["is_recommendable"] is True
    assert exact["recommendation_scope"] == "exact"
    assert exact["match_score"] > 0
    assert mismatch["is_recommendable"] is False
    assert mismatch["match_score"] == 0
    assert mismatch["hard_mismatches"] == ["요청 지역과 사업 대상 지역이 일치하지 않아요."]


async def test_eligibility_scorer_prefers_exact_and_uses_nearby_only_when_no_exact():
    profile = {"region": "성남시", "is_entrepreneur": True}
    exact_policy = _business_policy(region=["경기"])
    nearby_policy = _business_policy(region=["인천"], match_scope="nearby")

    exact_result = await nodes.eligibility_scorer_node(
        {"profile": profile, "search_results": [nearby_policy, exact_policy]}
    )
    nearby_result = await nodes.eligibility_scorer_node({"profile": profile, "search_results": [nearby_policy]})

    assert [item["recommendation_scope"] for item in exact_result["scored_results"]] == ["exact"]
    assert [item["recommendation_scope"] for item in nearby_result["scored_results"]] == ["nearby_reference"]


def test_nearby_templates_label_results_as_reference_with_distance_warning():
    youth = compose_youth_policy_response(
        [
            YouthPolicyItem(
                policy_id="incheon",
                title="인천 정책",
                region="인천",
                match_scope="nearby",
                distance_km=47.2,
            ).model_dump()
        ]
    )
    scored = score_policy(
        {"region": "성남시", "is_entrepreneur": True},
        _business_policy(region=["인천"], match_scope="nearby"),
    )
    business = compose_scored_template([scored])

    for response in (youth, business):
        assert "정확히 일치" in response
        assert "가까운 지역 참고" in response
        assert "거주 요건" in response


def test_scored_template_labels_scope_and_separates_score_from_evidence_coverage():
    """세부 내용(추천 범위/적합도/근거 확인률 등)은 프론트 카드로 표시되므로,
    템플릿 응답에는 개별 항목 수치가 아니라 짧은 안내 멘트만 담겨야 한다."""

    scored = score_policy(
        {"region": "성남시", "is_entrepreneur": True},
        _business_policy(region=["경기"]),
    )

    response = compose_scored_template([scored])

    assert "카드" in response
    assert "추천 범위" not in response
    assert "추천 적합도" not in response
    assert "근거 확인률" not in response
