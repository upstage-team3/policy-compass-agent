from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.core.config import get_settings
from app.tools.schemas import RecruitmentInfoItem, RecruitmentInfoSearchInput

logger = logging.getLogger(__name__)

_PERSONAL_KEY_LIMIT_MESSAGE = "개인회원은 사용할 수 없는 OPEN-API"


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def is_personal_key_limited_response(text: str) -> bool:
    return _PERSONAL_KEY_LIMIT_MESSAGE in text


def recruitment_fallback_guide(reason: str, query: RecruitmentInfoSearchInput) -> RecruitmentInfoItem:
    desired_job = query.desired_job or query.keywords or "관심 직무"
    region = query.preferred_work_region or "희망 지역"
    summary = (
        "현재 개인회원 API 권한으로는 채용정보목록/상세를 직접 조회하기 어렵습니다. "
        f"고용24에서 '{desired_job}', '{region}', 신입/인턴/공채 조건을 함께 넣어 검색해보세요. "
        "확인할 때는 마감일, 근무지역, 고용형태, 신입 지원 가능 여부, 원문 공고 URL을 우선 보시면 좋아요."
    )
    return RecruitmentInfoItem(
        item_id="work24-recruitment-guide",
        item_type="guide",
        title="고용24 채용 탐색 가이드",
        region=query.preferred_work_region,
        summary=summary,
        detail_url="https://www.work24.go.kr/",
        fallback_reason=reason,
    )


def normalize_recruitment_items(xml_text: str) -> list[RecruitmentInfoItem]:
    if is_personal_key_limited_response(xml_text):
        return []

    root = ET.fromstring(xml_text)
    records = root.findall(".//item") or root.findall(".//dhsOpenEmpInfo")
    items: list[RecruitmentInfoItem] = []

    for idx, node in enumerate(records, start=1):
        values = {child.tag: _compact_text(child.text) for child in list(node)}
        title = (
            values.get("empWantedTitle")
            or values.get("wantedTitle")
            or values.get("title")
            or values.get("empNm")
            or "채용 정보 제목 확인 필요"
        )
        item = RecruitmentInfoItem(
            item_id=values.get("wantedAuthNo") or values.get("empSeqno") or values.get("id") or str(idx),
            item_type="open_recruitment",
            title=title,
            company=values.get("company") or values.get("corpNm") or values.get("empBusiNm"),
            region=values.get("region") or values.get("workRegion"),
            start_date=values.get("startDate") or values.get("receiptSdt"),
            end_date=values.get("endDate") or values.get("receiptEdt") or values.get("closeDt"),
            summary=values.get("jobCont") or values.get("summary"),
            detail_url=values.get("wantedInfoUrl") or values.get("url"),
            raw=values,
        )
        items.append(item)

    return items


class Work24RecruitmentRepository:
    """고용24 채용정보 API 접근 계층.

    개인회원 키로 채용정보목록/상세가 제한되는 경우를 정상 fallback으로 다룬다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def search(self, query: RecruitmentInfoSearchInput) -> list[RecruitmentInfoItem]:
        if not self._settings.employment24_job_api_key:
            return [recruitment_fallback_guide("EMPLOYMENT24_JOB_API_KEY 미설정", query)]

        params: dict[str, Any] = {
            "authKey": self._settings.employment24_job_api_key,
            "callTp": "L",
            "returnType": "XML",
            "startPage": str(query.page),
            "display": str(query.page_size),
        }
        if query.occupation_codes:
            params["occupation"] = "|".join(query.occupation_codes)

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._settings.employment24_job_api_url, params=params)
                response.raise_for_status()
        except Exception:  # noqa: BLE001
            logger.warning("고용24 채용정보 API 호출 실패", exc_info=True)
            return [recruitment_fallback_guide("고용24 채용정보 API 호출 실패", query)]

        if is_personal_key_limited_response(response.text):
            return [recruitment_fallback_guide("개인회원 API 권한 제한", query)]

        try:
            items = normalize_recruitment_items(response.text)
        except ET.ParseError:
            logger.warning("고용24 채용정보 XML 파싱 실패", exc_info=True)
            return [recruitment_fallback_guide("고용24 채용정보 응답 파싱 실패", query)]

        return items or [recruitment_fallback_guide("채용정보 결과 없음", query)]
