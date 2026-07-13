from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from collections.abc import Sequence
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.http import log_external_api_error
from app.tools.schemas import RecruitmentInfoItem, RecruitmentInfoSearchInput

logger = logging.getLogger(__name__)

_PERSONAL_KEY_LIMIT_MESSAGE = "개인회원은 사용할 수 없는 OPEN-API"
_WORK24_HOME = "https://www.work24.go.kr/"
_EVENT_AREA_CODES = {
    "서울": "51",
    "강원": "51",
    "부산": "52",
    "경남": "52",
    "대구": "53",
    "경북": "53",
    "경기": "54",
    "인천": "54",
    "광주": "55",
    "전남": "55",
    "전북": "55",
    "제주": "55",
    "대전": "56",
    "충남": "56",
    "충북": "56",
    "세종": "56",
}


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _record_values(node: ET.Element) -> dict[str, str | None]:
    return {_local_name(child.tag): _compact_text(child.text) for child in list(node)}


def _first(values: dict[str, str | None], *keys: str) -> str | None:
    return next((values[key] for key in keys if values.get(key)), None)


def _normalize_date(value: str | None) -> str | None:
    if not value:
        return None
    compact = re.sub(r"\D", "", value)
    if len(compact) == 8:
        return f"{compact[:4]}-{compact[4:6]}-{compact[6:]}"
    return value


def _event_end_date(event_term: str | None) -> str | None:
    dates = re.findall(r"\d{4}[-./]?\d{2}[-./]?\d{2}", event_term or "")
    return _normalize_date(dates[-1]) if dates else None


def is_personal_key_limited_response(text: str) -> bool:
    return _PERSONAL_KEY_LIMIT_MESSAGE in text


def recruitment_fallback_guide(reason: str, query: RecruitmentInfoSearchInput) -> RecruitmentInfoItem:
    desired_job = query.desired_job or query.keywords or "관심 직무"
    region = query.preferred_work_region or "희망 지역"
    summary = (
        "현재 개인회원 API 권한으로 채용정보목록/상세를 직접 조회하기 어렵습니다. "
        "대신 허용된 채용행사·공채속보·공채기업정보 API를 조회합니다. "
        f"결과가 없으면 고용24에서 '{desired_job}', '{region}', 신입/인턴/공채 조건으로 확인해보세요."
    )
    return RecruitmentInfoItem(
        item_id="work24-recruitment-guide",
        item_type="guide",
        title="고용24 채용 탐색 가이드",
        region=query.preferred_work_region,
        summary=summary,
        detail_url=_WORK24_HOME,
        fallback_reason=reason,
    )


def normalize_recruitment_items(
    xml_text: str,
    item_type: str | None = None,
) -> list[RecruitmentInfoItem]:
    if is_personal_key_limited_response(xml_text):
        return []

    root = ET.fromstring(xml_text)
    record_specs = {
        "event": {"empEvent"},
        "open_recruitment": {"dhsOpenEmpInfo", "item"},
        "company": {"dhsOpenEmpHireInfo"},
    }
    allowed_tags = record_specs.get(item_type, set().union(*record_specs.values()))
    records = [node for node in root.iter() if _local_name(node.tag) in allowed_tags]
    items: list[RecruitmentInfoItem] = []

    for idx, node in enumerate(records, start=1):
        values = _record_values(node)
        resolved_type = item_type or _infer_item_type(node)
        if resolved_type == "event":
            items.append(_normalize_event(values, idx))
        elif resolved_type == "company":
            items.append(_normalize_company(values, idx))
        else:
            items.append(_normalize_open_recruitment(values, idx))
    return items


def _infer_item_type(node: ET.Element) -> str:
    tag = _local_name(node.tag)
    if tag == "empEvent":
        return "event"
    if tag == "dhsOpenEmpHireInfo":
        return "company"
    return "open_recruitment"


def _normalize_event(values: dict[str, str | None], idx: int) -> RecruitmentInfoItem:
    event_term = values.get("eventTerm")
    return RecruitmentInfoItem(
        item_id=values.get("eventNo") or f"event-{idx}",
        item_type="event",
        title=values.get("eventNm") or "채용행사명 확인 필요",
        region=values.get("area"),
        start_date=_normalize_date(values.get("startDt")),
        end_date=_event_end_date(event_term),
        summary=event_term,
        detail_url=_WORK24_HOME,
        raw=values,
    )


def _normalize_open_recruitment(values: dict[str, str | None], idx: int) -> RecruitmentInfoItem:
    summary_parts = [values.get("coClcdNm"), values.get("empWantedTypeNm")]
    summary = " / ".join(part for part in summary_parts if part)
    return RecruitmentInfoItem(
        item_id=_first(values, "wantedAuthNo", "empSeqno", "id") or f"open-{idx}",
        item_type="open_recruitment",
        title=_first(values, "empWantedTitle", "wantedTitle", "title", "empNm") or "공채속보 제목 확인 필요",
        company=_first(values, "company", "corpNm", "empBusiNm"),
        region=_first(values, "region", "workRegion"),
        start_date=_normalize_date(_first(values, "empWantedStdt", "startDate", "receiptSdt")),
        end_date=_normalize_date(_first(values, "empWantedEndt", "endDate", "receiptEdt", "closeDt")),
        summary=_first(values, "jobCont", "summary") or summary or None,
        detail_url=_first(
            values,
            "empWantedHomepgDetail",
            "empWantedMobileUrl",
            "wantedInfoUrl",
            "url",
        ),
        raw=values,
    )


def _normalize_company(values: dict[str, str | None], idx: int) -> RecruitmentInfoItem:
    return RecruitmentInfoItem(
        item_id=values.get("empCoNo") or f"company-{idx}",
        item_type="company",
        title=values.get("coNm") or "공채기업명 확인 필요",
        company=values.get("coNm"),
        summary=_first(values, "coIntroSummaryCont", "coIntroCont", "mainBusiCont", "coClcdNm"),
        detail_url=values.get("homepg") or _WORK24_HOME,
        raw=values,
    )


def _round_robin(groups: Sequence[list[RecruitmentInfoItem]], limit: int) -> list[RecruitmentInfoItem]:
    result: list[RecruitmentInfoItem] = []
    for index in range(max((len(group) for group in groups), default=0)):
        for group in groups:
            if index < len(group):
                result.append(group[index])
                if len(result) >= limit:
                    return result
    return result


class Work24RecruitmentRepository:
    """고용24 개인회원에 허용된 채용 보조 정보 API 접근 계층."""

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(self, query: RecruitmentInfoSearchInput) -> list[RecruitmentInfoItem]:
        if not self._settings.employment24_job_api_key:
            return [recruitment_fallback_guide("EMPLOYMENT24_JOB_API_KEY 미설정", query)]

        common_params: dict[str, Any] = {
            "authKey": self._settings.employment24_job_api_key,
            "callTp": "L",
            "returnType": "XML",
            "startPage": str(query.page),
            "display": str(query.page_size),
        }
        keyword = query.desired_job or query.keywords
        groups: list[list[RecruitmentInfoItem]] = []

        async with httpx.AsyncClient(timeout=20) as client:
            if query.include_open_recruitments:
                params = dict(common_params)
                if keyword:
                    params["empWantedTitle"] = keyword
                if query.career_level and "신입" in query.career_level:
                    params["empWantedCareerCd"] = "30"
                elif query.career_level and "인턴" in query.career_level:
                    params["empWantedCareerCd"] = "40"
                groups.append(
                    await self._fetch(
                        client,
                        self._settings.employment24_open_recruitment_api_url,
                        params,
                        "open_recruitment",
                        "공채속보",
                    )
                )

            if query.include_events:
                params = dict(common_params)
                if keyword:
                    params["keyword"] = keyword
                area_code = _EVENT_AREA_CODES.get(query.preferred_work_region or "")
                if area_code:
                    params["areaCd"] = area_code
                groups.append(
                    await self._fetch(
                        client,
                        self._settings.employment24_job_event_api_url,
                        params,
                        "event",
                        "채용행사",
                    )
                )

            if query.include_company_info:
                groups.append(
                    await self._fetch(
                        client,
                        self._settings.employment24_company_api_url,
                        common_params,
                        "company",
                        "공채기업정보",
                    )
                )

        items = _round_robin(groups, query.page_size)
        if items:
            return items
        return [recruitment_fallback_guide("허용된 고용24 채용 API 결과 없음", query)]

    async def _fetch(
        self,
        client: httpx.AsyncClient,
        url: str,
        params: dict[str, Any],
        item_type: str,
        label: str,
    ) -> list[RecruitmentInfoItem]:
        try:
            response = await client.get(url, params=params)
            response.raise_for_status()
        except Exception as exc:  # noqa: BLE001 - one endpoint must not block the others
            log_external_api_error(logger, f"고용24 {label} API", exc)
            return []

        try:
            return normalize_recruitment_items(response.text, item_type)
        except ET.ParseError:
            logger.warning("고용24 %s XML 파싱 실패", label)
            return []
