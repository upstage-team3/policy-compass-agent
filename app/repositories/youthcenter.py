from __future__ import annotations

import logging
import re
import xml.etree.ElementTree as ET
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.http import log_external_api_error
from app.tools.schemas import YouthPolicyItem, YouthPolicySearchInput

logger = logging.getLogger(__name__)

# 설정값(.env의 YOUTHCENTER_POLICY_API_URL)이 없을 때를 위한 공식 문서 기준 기본 엔드포인트.
OFFICIAL_YOUTH_POLICY_API_URL = "https://www.youthcenter.go.kr/go/ythip/getPlcy"


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


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _record_values(node: ET.Element) -> dict[str, str | None]:
    return {
        _local_name(child.tag): _compact_text(child.text)
        for child in node.iter()
        if child is not node and len(child) == 0
    }


def normalize_youth_policy_items(xml_text: str) -> list[YouthPolicyItem]:
    root = ET.fromstring(xml_text)
    record_tags = {"youthPolicy", "policy", "item", "plcy"}
    records = [node for node in root.iter() if _local_name(node.tag) in record_tags]
    items: list[YouthPolicyItem] = []

    for idx, node in enumerate(records, start=1):
        values = _record_values(node)
        title = _first(values, "polyBizSjnm", "plcyNm", "policyName", "title") or "청년정책명 확인 필요"
        item = YouthPolicyItem(
            policy_id=_first(values, "bizId", "plcyNo", "policyId", "id") or str(idx),
            title=title,
            organization=_first(values, "cnsgNmor", "sprvsnInstCdNm", "operInstCdNm", "operOrgan", "organization"),
            region=_first(values, "polyBizSecd", "zipCd", "regionNm", "region"),
            target_summary=_first(values, "ageInfo", "plcySprtTrgtCn", "target", "rqutPrdCn"),
            support_summary=_first(values, "sporCn", "plcySprtCn", "support", "content"),
            application_period=_first(values, "rqutPrdCn", "aplyYmd", "applicationPeriod"),
            application_method=_first(values, "rqutProcCn", "plcyAplyMthdCn", "applicationMethod"),
            detail_url=_first(values, "rfcSiteUrla1", "aplyUrlAddr", "detailUrl", "url"),
            raw=values,
        )
        items.append(item)

    return items


def normalize_youth_policy_json(payload: dict[str, Any]) -> list[YouthPolicyItem]:
    result = payload.get("result") or {}
    records = result.get("youthPolicyList") if isinstance(result, dict) else []
    if not isinstance(records, list):
        return []

    items: list[YouthPolicyItem] = []
    for idx, record in enumerate(records, start=1):
        if not isinstance(record, dict):
            continue
        values = {key: _compact_text(str(value)) for key, value in record.items() if value is not None}
        target_parts = [
            _first(values, "ptcpPrpTrgtCn", "addAplyQlfcCndCn"),
            _age_summary(values),
        ]
        items.append(
            YouthPolicyItem(
                policy_id=_first(values, "plcyNo", "bizId", "id") or str(idx),
                title=_first(values, "plcyNm", "polyBizSjnm", "title") or "청년정책명 확인 필요",
                organization=_first(
                    values,
                    "operInstCdNm",
                    "sprvsnInstCdNm",
                    "rgtrInstCdNm",
                    "rgtrHghrkInstCdNm",
                ),
                region=_first(values, "zipCd", "regionNm", "region"),
                target_summary=" / ".join(part for part in target_parts if part) or None,
                support_summary=_first(values, "plcySprtCn", "plcyExplnCn", "support"),
                application_period=_first(values, "aplyYmd", "rqutPrdCn", "applicationPeriod"),
                application_method=_first(values, "plcyAplyMthdCn", "rqutProcCn", "applicationMethod"),
                detail_url=_first(values, "aplyUrlAddr", "refUrlAddr1", "refUrlAddr2", "url"),
                raw=values,
            )
        )
    return items


def _age_summary(values: dict[str, str | None]) -> str | None:
    if values.get("sprtTrgtAgeLmtYn") == "N":
        return "연령 제한 없음"
    minimum = values.get("sprtTrgtMinAge")
    maximum = values.get("sprtTrgtMaxAge")
    if minimum and maximum:
        return f"만 {minimum}~{maximum}세"
    return None


class YouthCenterRepository:
    """온통청년 청년정책 Open API 접근 계층."""

    def __init__(self, fallback_repository: object | None = None) -> None:
        self._settings = get_settings()
        self._fallback_repository = fallback_repository

    async def search(self, query: YouthPolicySearchInput) -> list[YouthPolicyItem]:
        if not self._settings.youthcenter_policy_api_key:
            logger.warning("YOUTHCENTER_POLICY_API_KEY is not configured; returning no youth policy results.")
            return []

        search_terms = [query.keywords, *query.support_types, *query.interest_fields]
        search_query = " ".join(term.strip() for term in search_terms if term and term.strip())
        params = {
            "apiKeyNm": self._settings.youthcenter_policy_api_key,
            "pageNum": str(query.page),
            "pageSize": str(query.page_size),
        }
        if search_query:
            params["plcyNm"] = search_query

        api_url = self._settings.youthcenter_policy_api_url or OFFICIAL_YOUTH_POLICY_API_URL
        headers = {
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
            ),
            "Accept": "application/json,*/*",
            "Accept-Language": "ko-KR,ko;q=0.9,en;q=0.8",
        }

        try:
            async with httpx.AsyncClient(timeout=10, follow_redirects=False, headers=headers) as client:
                response = await client.get(api_url, params=params)
                response.raise_for_status()
        except Exception as exc:  # noqa: BLE001
            log_external_api_error(logger, "온통청년 API", exc)
            return []

        if "json" in response.headers.get("content-type", "").lower() or response.text.lstrip().startswith("{"):
            try:
                payload = response.json()
            except ValueError:
                logger.warning("온통청년 JSON 파싱 실패")
                return []
            if str(payload.get("resultCode")) != "200":
                logger.warning("온통청년 API 비정상 응답 (result_code=%s)", payload.get("resultCode"))
                return []
            return normalize_youth_policy_json(payload)

        try:
            return normalize_youth_policy_items(response.text)
        except ET.ParseError:
            logger.warning("온통청년 XML 파싱 실패")
            return []
