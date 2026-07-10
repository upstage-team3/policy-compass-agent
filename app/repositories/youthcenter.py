from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET

import httpx

from app.core.config import get_settings
from app.tools.schemas import YouthPolicyItem, YouthPolicySearchInput

logger = logging.getLogger(__name__)


def _compact_text(value: str | None) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", value).strip()
    return text or None


def _first(values: dict[str, str | None], *keys: str) -> str | None:
    for key in keys:
        value = values.get(key)
        if value:
            return value
    return None


def normalize_youth_policy_items(xml_text: str) -> list[YouthPolicyItem]:
    root = ET.fromstring(xml_text)
    records = root.findall(".//youthPolicy") or root.findall(".//policy") or root.findall(".//item")
    items: list[YouthPolicyItem] = []

    for idx, node in enumerate(records, start=1):
        values = {child.tag: _compact_text(child.text) for child in list(node)}
        title = _first(values, "polyBizSjnm", "policyName", "title") or "청년정책명 확인 필요"
        item = YouthPolicyItem(
            policy_id=_first(values, "bizId", "policyId", "id") or str(idx),
            title=title,
            organization=_first(values, "cnsgNmor", "operOrgan", "organization"),
            region=_first(values, "polyBizSecd", "region"),
            target_summary=_first(values, "ageInfo", "target", "rqutPrdCn"),
            support_summary=_first(values, "sporCn", "support", "content"),
            application_period=_first(values, "rqutPrdCn", "applicationPeriod"),
            application_method=_first(values, "rqutProcCn", "applicationMethod"),
            detail_url=_first(values, "rfcSiteUrla1", "detailUrl", "url"),
            raw=values,
        )
        items.append(item)

    return items


class YouthCenterRepository:
    """온통청년 청년정책 API 접근 계층.

    현재 키가 없으면 내부 정책 데이터를 청년정책 fallback으로 변환한다.
    """

    def __init__(self, fallback_repository: object | None = None) -> None:
        self._settings = get_settings()
        self._fallback_repository = fallback_repository

    async def search(self, query: YouthPolicySearchInput) -> list[YouthPolicyItem]:
        if not self._settings.youthcenter_policy_api_key:
            logger.warning("YOUTHCENTER_POLICY_API_KEY is not configured; returning no youth policy results.")
            return []

        params = {
            "openApiVlak": self._settings.youthcenter_policy_api_key,
            "pageIndex": str(query.page),
            "display": str(query.page_size),
            "query": query.keywords,
            "keyword": query.keywords,
        }

        try:
            async with httpx.AsyncClient(timeout=15) as client:
                response = await client.get(self._settings.youthcenter_policy_api_url, params=params)
                response.raise_for_status()
        except Exception:  # noqa: BLE001
            logger.warning("온통청년 API 호출 실패", exc_info=True)
            return []

        try:
            items = normalize_youth_policy_items(response.text)
        except ET.ParseError:
            logger.warning("온통청년 XML 파싱 실패", exc_info=True)
            return []

        return items
