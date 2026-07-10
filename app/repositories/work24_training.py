from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from datetime import date, timedelta
from typing import Any
from urllib.parse import quote_plus

import httpx

from app.core.config import get_settings
from app.tools.schemas import TrainingCourseItem, TrainingCourseSearchInput

logger = logging.getLogger(__name__)


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _node_text(node: ET.Element, name: str) -> str | None:
    child = node.find(name)
    return _compact_text(child.text if child is not None else None)


def default_training_period(today: date | None = None) -> tuple[str, str]:
    base = today or date.today()
    end = base + timedelta(days=183)
    return base.strftime("%Y%m%d"), end.strftime("%Y%m%d")


def normalize_training_courses(xml_text: str) -> list[TrainingCourseItem]:
    root = ET.fromstring(xml_text)
    records = root.findall(".//scn_list")
    courses: list[TrainingCourseItem] = []

    for node in records:
        title = _node_text(node, "title") or "훈련과정명 확인 필요"
        course_id = _node_text(node, "trprId") or title
        item = TrainingCourseItem(
            course_id=course_id,
            course_round=_node_text(node, "trprDegr"),
            title=title,
            institution=_node_text(node, "subTitle"),
            region=_node_text(node, "address"),
            address=_node_text(node, "address"),
            start_date=_node_text(node, "traStartDate"),
            end_date=_node_text(node, "traEndDate"),
            cost=_node_text(node, "courseMan"),
            actual_cost=_node_text(node, "realMan"),
            ncs_code=_node_text(node, "ncsCd"),
            target=_node_text(node, "trainTarget"),
            capacity=_node_text(node, "yardMan"),
            contact=_node_text(node, "telNo"),
            detail_url=_node_text(node, "titleLink"),
            institution_url=_node_text(node, "subTitleLink"),
            raw={child.tag: _compact_text(child.text) for child in list(node)},
        )
        courses.append(item)

    return courses


def _build_work24_training_search_url(query: TrainingCourseSearchInput) -> str:
    desired_job = query.desired_job or query.keywords or ""
    # Work24 changes deep links occasionally, so keep this anchored to the public entry point
    # while carrying the keyword in a query string users can copy from the answer.
    params = quote_plus(desired_job.strip())
    return f"https://www.work24.go.kr/cm/main.do?keyword={params}" if params else "https://www.work24.go.kr/cm/main.do"


def _compact_training_keyword(value: str | None) -> str | None:
    if not value:
        return None
    keyword_rules = [
        (("데이터", "분석"), "데이터 분석"),
        (("빅데이터",), "빅데이터"),
        (("인공지능",), "인공지능"),
        (("AI",), "AI"),
        (("개발",), "개발"),
        (("프로그래밍",), "프로그래밍"),
        (("마케팅",), "마케팅"),
        (("디자인",), "디자인"),
    ]
    for needles, keyword in keyword_rules:
        if all(needle in value for needle in needles):
            return keyword
    text = re.sub(
        r"(국비지원|국민내일배움카드|훈련과정|훈련|과정|찾아줘|추천|취업|준비|중이야|쪽으로|에서)",
        " ",
        value,
    )
    text = re.sub(r"[^\w가-힣+# ]+", " ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text or None


def training_fallback_guide(reason: str, query: TrainingCourseSearchInput) -> TrainingCourseItem:
    desired_job = _compact_training_keyword(query.desired_job) or _compact_training_keyword(query.keywords)
    desired_job = desired_job or "관심 직무"
    region = query.training_region or "희망 지역"
    return TrainingCourseItem(
        course_id="work24-training-guide",
        title="고용24 훈련과정 검색 결과를 바로 찾지 못했어요",
        institution="고용24",
        region=query.training_region,
        detail_url=_build_work24_training_search_url(query),
        fallback_reason=(
            f"{reason}. 고용24 국민내일배움카드 훈련과정 화면에서 "
            f"검색어 '{desired_job}', 지역 '{region}', 훈련 시작일 6개월 범위로 다시 확인해보세요."
        ),
        raw={"search_keyword": desired_job, "search_region": region},
    )


class Work24TrainingRepository:
    """고용24 국민내일배움카드 훈련과정 API 접근 계층."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(self, query: TrainingCourseSearchInput) -> list[TrainingCourseItem]:
        if not self._settings.employment24_training_api_key:
            return [training_fallback_guide("EMPLOYMENT24_TRAINING_API_KEY 미설정", query)]

        start, end = default_training_period()
        params: dict[str, Any] = {
            "authKey": self._settings.employment24_training_api_key,
            "returnType": "XML",
            "outType": "1",
            "pageNum": str(query.page),
            "pageSize": str(query.page_size),
            "srchTraStDt": query.training_start_date_from or start,
            "srchTraEndDt": query.training_start_date_to or end,
            "sort": "ASC",
            "sortCol": "2",
        }
        if query.training_region_code:
            params["srchTraArea1"] = query.training_region_code
        search_keyword = _compact_training_keyword(query.desired_job) or _compact_training_keyword(query.keywords)
        if search_keyword:
            params["srchTraProcessNm"] = search_keyword

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._settings.employment24_training_api_url, params=params)
                response.raise_for_status()
        except Exception:  # noqa: BLE001
            logger.warning("고용24 훈련과정 API 호출 실패", exc_info=True)
            return [training_fallback_guide("고용24 훈련과정 API 호출 실패", query)]

        try:
            items = normalize_training_courses(response.text)
        except ET.ParseError:
            logger.warning("고용24 훈련과정 XML 파싱 실패", exc_info=True)
            return [training_fallback_guide("고용24 훈련과정 응답 파싱 실패", query)]

        if items:
            return items

        fallback_query = query.model_copy(update={"desired_job": search_keyword})
        return [training_fallback_guide("고용24 훈련과정 검색 결과 없음", fallback_query)]
