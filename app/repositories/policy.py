from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.policy import PolicyItem
from app.tools.schemas import PolicySearchInput

logger = logging.getLogger(__name__)

FIELD_CODES = {
    "금융": "01",
    "기술": "02",
    "인력": "03",
    "수출": "04",
    "내수": "05",
    "창업": "06",
    "경영": "07",
    "기타": "09",
}

_REGION_NAMES = {
    "서울",
    "부산",
    "대구",
    "인천",
    "광주",
    "대전",
    "울산",
    "세종",
    "경기",
    "강원",
    "충북",
    "충남",
    "전북",
    "전남",
    "경북",
    "경남",
    "제주",
}


class PolicyRepository:
    """정책 공고 데이터 접근 계층.

    기업마당 Open API 연동을 시도하고 실제 응답을 PolicyItem 스키마로
    정규화한다. API 키가 없거나 호출이 실패하면 빈 결과를 반환한다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def _fetch_remote(self) -> list[dict[str, Any]] | None:
        if not self._settings.bizinfo_api_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self._settings.bizinfo_base_url,
                    params={
                        "crtfcKey": self._settings.bizinfo_api_key,
                        "dataType": "json",
                        "pageUnit": "20",
                        "pageIndex": "1",
                    },
                )
                response.raise_for_status()
                payload = response.json()
        except Exception:  # noqa: BLE001 - 외부 API 장애 시 빈 결과 반환
            logger.warning("기업마당 API 호출 실패, 빈 결과를 반환합니다.", exc_info=True)
            return None

        records = [_normalize_bizinfo_item(item) for item in _normalize_bizinfo_items(payload)]
        return records or None

    async def _all_policies(self) -> list[dict[str, Any]]:
        remote = await self._fetch_remote()
        return remote if remote is not None else []

    async def search(self, query: PolicySearchInput) -> list[PolicyItem]:
        policies = await self._all_policies()
        candidates = policies

        if query.is_entrepreneur:
            candidates = [p for p in policies if p["category"] in ("창업", "경영/기술")]
        elif query.employment_status == "unemployed_seeking_job":
            candidates = [p for p in policies if p["category"] == "구직창업"]
        elif query.has_registered_business:
            candidates = [p for p in policies if p["category"] == "경영/기술"]

        if not candidates:
            candidates = policies

        return [PolicyItem(**p) for p in candidates[: query.limit]]

    async def get_by_id(self, policy_id: str) -> PolicyItem | None:
        for policy in await self._all_policies():
            if policy["id"] == policy_id:
                return PolicyItem(**policy)
        return None

    async def find_best_title_match(self, text: str) -> dict[str, Any] | None:
        for policy in await self._all_policies():
            title = policy["title"]
            tokens = [tok for tok in title.split() if len(tok) > 1]
            if title in text or any(tok in text for tok in tokens):
                return policy
        return None

    async def list_all(self, *, region: str | None = None, category: str | None = None) -> list[PolicyItem]:
        policies = await self._all_policies()
        if region:
            policies = [p for p in policies if "전국" in p["region"] or region in p["region"]]
        if category:
            policies = [p for p in policies if p["category"] == category]
        return [PolicyItem(**p) for p in policies]


def _strip_html(value: str | None) -> str:
    if not value:
        return ""
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", " ", value)).strip()


def _first_non_empty(item: dict[str, Any], *keys: str) -> str:
    for key in keys:
        value = item.get(key)
        if value is None:
            continue
        text = _strip_html(str(value))
        if text:
            return text
    return ""


def _normalize_bizinfo_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    root = payload.get("jsonArray") or payload.get("response") or payload.get("body") or payload
    while isinstance(root, dict) and "body" in root:
        root = root["body"]
    if isinstance(root, dict) and "items" in root and isinstance(root["items"], dict):
        root = root["items"]
    items = root.get("item", []) if isinstance(root, dict) else []
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def _period_dates(period: str | None) -> tuple[str | None, str | None]:
    dates = re.findall(r"\d{8}", period or "")
    if not dates:
        return None, None
    start = None
    end = None
    try:
        start = datetime.strptime(dates[0], "%Y%m%d").date().isoformat()
    except ValueError:
        start = None
    if len(dates) >= 2:
        try:
            end = datetime.strptime(dates[-1], "%Y%m%d").date().isoformat()
        except ValueError:
            end = None
    return start, end


def _normalize_category(raw_category: str) -> str:
    if "창업" in raw_category:
        return "창업"
    if any(word in raw_category for word in ("경영", "기술", "인력", "금융", "내수", "수출")):
        return "경영/기술"
    return "구직창업"


def _normalize_bizinfo_item(item: dict[str, Any]) -> dict[str, Any]:
    title = _first_non_empty(item, "pblancNm", "title", "businessName", "bizPbancNm") or "제목 없음"
    period = _first_non_empty(item, "reqstBeginEndDe", "reqstDt", "applicationPeriod")
    apply_start, apply_end = _period_dates(period)
    category = _first_non_empty(item, "pldirSportRealmLclasCodeNm", "lcategory", "supportField", "realmName") or "기타"
    summary = _first_non_empty(item, "bsnsSumryCn", "description", "supportContent", "cn")
    target = _first_non_empty(item, "trgetNm", "target", "supportTarget", "trgtNm")
    apply_method = _first_non_empty(item, "reqstMthPapersCn", "applyMethod", "rceptEngnHmpgUrl", "submitMethod")
    source_url = _first_non_empty(item, "pblancUrl", "link", "url", "detailUrl")
    hashtags = _first_non_empty(item, "hashTags", "hashtags")
    regions = [tag.strip() for tag in hashtags.split(",") if tag.strip() in _REGION_NAMES]

    return {
        "id": _first_non_empty(item, "pblancId", "seq", "id") or title,
        "title": title,
        "agency": _first_non_empty(item, "jrsdInsttNm", "author", "agency", "organNm") or "기업마당",
        "category": _normalize_category(category),
        "target_description": target or "대상 조건은 기업마당 공고 원문에서 확인이 필요합니다.",
        "region": regions or ["전국"],
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": True if "창업" in category or "창업" in title else None,
        "requires_business_registration": None,
        "apply_start": apply_start,
        "apply_end": apply_end,
        "apply_method": apply_method or "신청 방법은 기업마당 공고 원문에서 확인이 필요합니다.",
        "support_content": summary or "지원 내용은 원문에서 확인이 필요합니다.",
        "source_url": source_url or "https://www.bizinfo.go.kr/",
    }
