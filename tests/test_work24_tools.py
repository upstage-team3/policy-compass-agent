from __future__ import annotations

from datetime import date

from app.graph import nodes
from app.repositories.work24_recruitment import (
    is_personal_key_limited_response,
    normalize_recruitment_items,
    recruitment_fallback_guide,
)
from app.repositories.work24_training import (
    default_training_period,
    normalize_training_courses,
    training_fallback_guide,
)
from app.repositories.youthcenter import normalize_youth_policy_items
from app.tools.schemas import RecruitmentInfoSearchInput, TrainingCourseSearchInput


def test_default_training_period_uses_six_month_window():
    start, end = default_training_period(date(2026, 7, 10))

    assert start == "20260710"
    assert end == "20270109"


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


def test_heuristic_route_treats_training_and_recruitment_as_recommend():
    assert nodes._heuristic_route("국비지원 훈련과정 찾아줘") == "RECOMMEND"
    assert nodes._classify_request_kind("국비지원 훈련과정 찾아줘", {}) == "training"
    assert nodes._heuristic_route("신입 채용공고 찾아줘") == "RECOMMEND"
    assert nodes._classify_request_kind("신입 채용공고 찾아줘", {}) == "recruitment"
