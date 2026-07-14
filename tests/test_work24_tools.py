from __future__ import annotations

from datetime import date
from types import SimpleNamespace

import httpx
import pytest

from app.graph import nodes
from app.repositories.work24_recruitment import (
    Work24RecruitmentRepository,
    is_personal_key_limited_response,
    normalize_recruitment_items,
    recruitment_fallback_guide,
)
from app.repositories.work24_training import (
    default_training_period,
    normalize_training_courses,
    training_fallback_guide,
)
from app.repositories.youthcenter import (
    YouthCenterAPIUnavailableError,
    YouthCenterRepository,
    _build_youth_search_terms,
    _filter_active_youth_policies,
    _filter_youth_policies_by_region,
    is_generic_youth_policy_query,
    normalize_youth_policy_items,
    normalize_youth_policy_json,
)
from app.tools.schemas import (
    RecruitmentInfoSearchInput,
    TrainingCourseSearchInput,
    YouthPolicyItem,
    YouthPolicySearchInput,
)


def test_default_training_period_uses_six_month_window():
    start, end = default_training_period(date(2026, 7, 10))

    assert start == "20260710"
    assert end == "20270109"


def test_generic_youth_policy_query_recognizes_natural_broad_request_but_not_topic_request():
    assert is_generic_youth_policy_query("청년 지원 정책에 대한 정보를 얻고 싶어")
    assert not is_generic_youth_policy_query("청년 주거 지원 정책에 대한 정보를 얻고 싶어")


def test_normalize_training_courses_maps_core_fields():
    xml = """
    <HRDNet>
      <srchList>
        <scn_list>
          <trprId>AIG001</trprId>
          <trprDegr>1</trprDegr>
          <title>데이터 분석 실무</title>
          <subTitle>서울AI직업학교</subTitle>
          <address>서울 강남구</address>
          <traStartDate>2026-08-01</traStartDate>
          <traEndDate>2026-10-31</traEndDate>
          <courseMan>1200000</courseMan>
          <realMan>200000</realMan>
          <ncsCd>20010105</ncsCd>
          <trainTarget>국민내일배움카드</trainTarget>
          <yardMan>25</yardMan>
          <telNo>02-0000-0000</telNo>
          <titleLink>https://example.com/course</titleLink>
        </scn_list>
      </srchList>
    </HRDNet>
    """

    courses = normalize_training_courses(xml)

    assert len(courses) == 1
    assert courses[0].course_id == "AIG001"
    assert courses[0].title == "데이터 분석 실무"
    assert courses[0].institution == "서울AI직업학교"
    assert courses[0].detail_url == "https://example.com/course"


def test_training_fallback_guide_does_not_invent_course():
    guide = training_fallback_guide(
        "고용24 훈련과정 검색 결과 없음",
        TrainingCourseSearchInput(desired_job="데이터 분석", training_region="서울"),
    )

    assert guide.course_id == "work24-training-guide"
    assert guide.fallback_reason is not None
    assert "국민내일배움카드 훈련과정 화면" in guide.fallback_reason
    assert guide.raw["search_keyword"] == "데이터 분석"


def test_recruitment_personal_key_limit_detection_and_guide():
    text = "<GO24><message>개인회원은 사용할 수 없는 OPEN-API입니다.</message></GO24>"
    query = RecruitmentInfoSearchInput(desired_job="데이터 분석", preferred_work_region="서울")

    assert is_personal_key_limited_response(text)
    guide = recruitment_fallback_guide("개인회원 API 권한 제한", query)

    assert guide.item_type == "guide"
    assert "직접 조회하기 어렵습니다" in (guide.summary or "")
    assert guide.detail_url == "https://www.work24.go.kr/"


def test_normalize_recruitment_items_maps_optional_fields():
    xml = """
    <GO24>
      <item>
        <wantedAuthNo>R001</wantedAuthNo>
        <empWantedTitle>신입 데이터 분석가 채용</empWantedTitle>
        <company>테스트회사</company>
        <region>서울</region>
        <closeDt>2026-08-31</closeDt>
        <wantedInfoUrl>https://example.com/job</wantedInfoUrl>
      </item>
    </GO24>
    """

    items = normalize_recruitment_items(xml)

    assert items[0].item_id == "R001"
    assert items[0].title == "신입 데이터 분석가 채용"
    assert items[0].company == "테스트회사"


def test_normalize_allowed_recruitment_event_and_company_shapes():
    event_xml = """
    <empEvList><empEvent><eventNo>E001</eventNo><eventNm>청년 채용박람회</eventNm>
    <area>서울</area><eventTerm>2026-07-20 ~ 2026-07-21</eventTerm><startDt>20260720</startDt>
    </empEvent></empEvList>
    """
    company_xml = """
    <dhsOpenEmpHireInfoList><dhsOpenEmpHireInfo><empCoNo>C001</empCoNo><coNm>테스트기업</coNm>
    <coIntroSummaryCont>AI 서비스 기업</coIntroSummaryCont><homepg>https://example.com</homepg>
    </dhsOpenEmpHireInfo></dhsOpenEmpHireInfoList>
    """

    event = normalize_recruitment_items(event_xml, "event")[0]
    company = normalize_recruitment_items(company_xml, "company")[0]

    assert event.item_type == "event"
    assert event.start_date == "2026-07-20"
    assert event.end_date == "2026-07-21"
    assert company.item_type == "company"
    assert company.company == "테스트기업"


async def test_recruitment_repository_calls_only_personal_member_allowed_endpoints(monkeypatch):
    called_urls: list[str] = []
    payloads = {
        "210L21": "<dhsOpenEmpInfoList />",
        "210L11": "<empEvList />",
        "210L31": "<dhsOpenEmpHireInfoList />",
    }

    class FakeClient:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *args):
            return None

        async def get(self, url, params):
            called_urls.append(url)
            endpoint = next(code for code in payloads if code in url)
            return httpx.Response(200, text=payloads[endpoint], request=httpx.Request("GET", url))

    monkeypatch.setattr("app.repositories.work24_recruitment.httpx.AsyncClient", FakeClient)
    repository = Work24RecruitmentRepository()
    repository._settings = SimpleNamespace(
        employment24_job_api_key="test-key",
        employment24_open_recruitment_api_url="https://example.com/210L21.do",
        employment24_job_event_api_url="https://example.com/210L11.do",
        employment24_company_api_url="https://example.com/210L31.do",
    )

    await repository.search(RecruitmentInfoSearchInput())

    assert {url.rsplit("/", 1)[-1] for url in called_urls} == {
        "210L11.do",
        "210L21.do",
        "210L31.do",
    }
    assert all("210L01" not in url for url in called_urls)


def test_normalize_youth_policy_items_maps_expected_xml_shape():
    xml = """
    <response>
      <item>
        <bizId>Y001</bizId>
        <polyBizSjnm>서울 청년 취업 지원</polyBizSjnm>
        <cnsgNmor>서울시</cnsgNmor>
        <ageInfo>만 19세~34세</ageInfo>
        <sporCn>취업 준비 지원</sporCn>
        <rqutPrdCn>상시</rqutPrdCn>
        <rqutProcCn>온라인 신청</rqutProcCn>
        <rfcSiteUrla1>https://example.com/youth</rfcSiteUrla1>
      </item>
    </response>
    """

    items = normalize_youth_policy_items(xml)

    assert items[0].policy_id == "Y001"
    assert items[0].title == "서울 청년 취업 지원"
    assert items[0].application_method == "온라인 신청"


def test_normalize_youth_policy_items_supports_current_field_names_and_namespace():
    xml = """
    <response xmlns="urn:youth"><youthPolicy><plcyNo>Y002</plcyNo><plcyNm>AI 일경험 지원</plcyNm>
    <sprvsnInstCdNm>고용노동부</sprvsnInstCdNm><plcySprtCn>직무 경험 제공</plcySprtCn>
    <plcyAplyMthdCn>온라인</plcyAplyMthdCn></youthPolicy></response>
    """

    item = normalize_youth_policy_items(xml)[0]

    assert item.policy_id == "Y002"
    assert item.title == "AI 일경험 지원"
    assert item.organization == "고용노동부"


def test_normalize_youth_policy_json_maps_current_api_shape():
    payload = {
        "resultCode": 200,
        "result": {
            "youthPolicyList": [
                {
                    "plcyNo": "Y003",
                    "plcyNm": "국민취업지원제도",
                    "operInstCdNm": "고용노동부",
                    "ptcpPrpTrgtCn": "취업을 원하는 청년",
                    "sprtTrgtAgeLmtYn": "Y",
                    "sprtTrgtMinAge": 19,
                    "sprtTrgtMaxAge": 34,
                    "plcySprtCn": "취업지원 서비스",
                    "bizPrdBgngYmd": "20260101",
                    "bizPrdEndYmd": "20261231",
                    "aplyYmd": "상시",
                    "plcyAplyMthdCn": "온라인 신청",
                    "aplyUrlAddr": "https://example.com/apply",
                }
            ]
        },
    }

    item = normalize_youth_policy_json(payload)[0]

    assert item.policy_id == "Y003"
    assert item.title == "국민취업지원제도"
    assert item.organization == "고용노동부"
    assert "만 19~34세" in (item.target_summary or "")
    assert item.business_period == "2026-01-01 ~ 2026-12-31"
    assert item.business_end_date == "2026-12-31"
    assert item.detail_url == "https://example.com/apply"


def test_youth_search_terms_relax_broad_employment_phrase():
    terms = _build_youth_search_terms(
        YouthPolicySearchInput(
            keywords="청년 취업 지원",
            employment_status="unemployed_seeking_job",
        )
    )

    assert terms == ["청년 취업 지원", "취업"]


def test_youth_search_terms_normalize_housing_request():
    terms = _build_youth_search_terms(
        YouthPolicySearchInput(
            keywords="거주지원을 받고 싶은데 관련 정책있어?",
            employment_status="unemployed_seeking_job",
        )
    )

    assert terms == ["거주지원을 받고 싶은데 관련 정책있어?", "주거"]


def test_youth_search_terms_keep_specific_housing_and_finance_scope():
    rent_terms = _build_youth_search_terms(YouthPolicySearchInput(keywords="월세"))
    finance_terms = _build_youth_search_terms(YouthPolicySearchInput(keywords="금융"))

    assert rent_terms == ["월세"]
    assert finance_terms == ["금융"]


def test_youth_search_terms_use_profile_for_generic_request():
    terms = _build_youth_search_terms(
        YouthPolicySearchInput(
            keywords="정책 검색 요청",
            employment_status="unemployed_seeking_job",
        )
    )

    assert terms == ["취업"]


def test_youth_search_terms_use_official_policy_topic_for_generic_request():
    terms = _build_youth_search_terms(
        YouthPolicySearchInput(
            keywords="청년 지원 정책",
            support_types=["금융·복지·문화"],
        )
    )

    assert terms == ["금융·복지·문화", "복지"]


def test_youth_search_terms_do_not_replace_specific_query_with_broad_profile_topic():
    terms = _build_youth_search_terms(
        YouthPolicySearchInput(
            keywords="고립 은둔",
            support_types=["금융·복지·문화"],
        )
    )

    assert terms == ["고립 은둔"]


async def test_youth_fetch_retries_once_after_server_error():
    repository = YouthCenterRepository()

    class RetryClient:
        def __init__(self):
            self.calls = 0

        async def get(self, api_url, params):
            del api_url, params
            self.calls += 1
            if self.calls == 1:
                return httpx.Response(500, request=httpx.Request("GET", "https://example.com"))
            return httpx.Response(
                200,
                request=httpx.Request("GET", "https://example.com"),
                headers={"content-type": "application/json"},
                json={"resultCode": 200, "result": {"youthPolicyList": []}},
            )

    client = RetryClient()
    result = await repository._fetch(client, "https://example.com", {"pageNum": "1"})

    assert result == []
    assert client.calls == 2


async def test_youth_fetch_raises_after_repeated_server_errors():
    repository = YouthCenterRepository()

    class FailingClient:
        def __init__(self):
            self.calls = 0

        async def get(self, api_url, params):
            del api_url, params
            self.calls += 1
            return httpx.Response(500, request=httpx.Request("GET", "https://example.com"))

    client = FailingClient()
    with pytest.raises(YouthCenterAPIUnavailableError):
        await repository._fetch(client, "https://example.com", {"pageNum": "1"})

    assert client.calls == 2


async def test_youth_search_returns_availability_guide_when_every_fetch_fails(monkeypatch):
    repository = YouthCenterRepository()
    repository._settings = SimpleNamespace(
        youthcenter_policy_api_key="test-key",
        youthcenter_policy_api_url="https://example.com/youth",
    )

    async def fail_fetch(client, api_url, params):
        del client, api_url, params
        raise YouthCenterAPIUnavailableError

    monkeypatch.setattr(repository, "_fetch", fail_fetch)
    result = await repository.search(YouthPolicySearchInput(keywords="주거"))

    assert len(result) == 1
    assert result[0].policy_id == "youthcenter-guide"
    assert "정책 유무를 확인하지 못했어요" in (result[0].fallback_reason or "")


def test_youth_policy_region_filter_keeps_matching_and_nationwide_items():
    items = [
        YouthPolicyItem(policy_id="seoul", title="서울 정책", region="서울", raw={"zipCd": "11110"}),
        YouthPolicyItem(policy_id="incheon", title="인천 정책", region="인천", raw={"zipCd": "28237"}),
        YouthPolicyItem(policy_id="all", title="전국 정책", region="전국", raw={"zipCd": "11110,26110,28237"}),
    ]

    filtered = _filter_youth_policies_by_region(items, "서울")

    assert [item.policy_id for item in filtered] == ["seoul", "all"]


def test_youth_policy_active_filter_excludes_ended_business_period():
    items = [
        YouthPolicyItem(policy_id="expired", title="지난 정책", business_end_date="2025-12-31"),
        YouthPolicyItem(policy_id="active", title="현재 정책", business_end_date="2026-12-31"),
        YouthPolicyItem(policy_id="unknown", title="기간 미등록 정책"),
    ]

    filtered = _filter_active_youth_policies(items, today=date(2026, 7, 13))

    assert [item.policy_id for item in filtered] == ["active", "unknown"]


async def test_missing_slot_node_for_training_requires_job_and_region():
    result = await nodes.missing_slot_node({"request_kind": "training", "profile": {}})

    assert result["missing_slots"] == ["desired_job", "training_region"]


async def test_training_profile_extracts_request_kind_and_desired_job():
    result = await nodes.profile_extractor_node(
        {"user_input": "서울에서 데이터 분석 쪽으로 취업 준비 중인데 국비지원 훈련과정 찾아줘"}
    )

    assert result["request_kind"] == "training"
    assert result["profile"]["region"] == "서울"
    assert result["profile"]["desired_job"] == "데이터 분석"


async def test_training_profile_extracts_cloud_job_without_reasking():
    result = await nodes.profile_extractor_node(
        {"user_input": "서울에서 클라우드 엔지니어 국비과정 찾아줘", "request_kind": "training"}
    )

    assert result["profile"]["region"] == "서울"
    assert result["profile"]["desired_job"] == "클라우드 엔지니어"
    missing = await nodes.missing_slot_node({"request_kind": "training", "profile": result["profile"]})
    assert missing["missing_slots"] == []


def test_heuristic_route_treats_training_and_recruitment_as_recommend():
    assert nodes._heuristic_route("국비지원 훈련과정 찾아줘") == "RECOMMEND"
    assert nodes._classify_request_kind("국비지원 훈련과정 찾아줘", {}) == "training"
    assert nodes._heuristic_route("신입 채용공고 찾아줘") == "RECOMMEND"
    assert nodes._classify_request_kind("신입 채용공고 찾아줘", {}) == "recruitment"
