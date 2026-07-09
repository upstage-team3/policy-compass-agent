from __future__ import annotations

import json
import logging
import re
from datetime import date, datetime
from functools import lru_cache
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


@lru_cache
def _load_mock_policies() -> list[dict[str, Any]]:
    settings = get_settings()
    path = settings.data_dir / "mock_policies.json"
    with path.open(encoding="utf-8") as fp:
        return json.load(fp)


class PolicyRepository:
    """정책 공고 데이터 접근 계층.

    1차로 기업마당 Open API 연동을 시도하고, API 키가 없거나 호출이
    실패하면 data/mock_policies.json 으로 폴백한다. 실제 기업마당 응답의
    정규화 매핑은 data/scripts/ingest_data.py 배치 작업에서 처리하며,
    이 계층은 이미 정규화된 정책 레코드만 다룬다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def _fetch_remote(self) -> list[dict[str, Any]] | None:
        if self._settings.use_mock_policy_data or not self._settings.bizinfo_api_key:
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
        except Exception:  # noqa: BLE001 - 외부 API 장애 시 mock 데이터로 폴백
            logger.warning("기업마당 API 호출 실패, mock 데이터로 폴백합니다.", exc_info=True)
            return None

        records = [_normalize_bizinfo_item(item) for item in _normalize_bizinfo_items(payload)]
        return records or None

    async def _all_policies(self) -> list[dict[str, Any]]:
        remote = await self._fetch_remote()
        return remote if remote is not None else _load_mock_policies()

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

    async def list_all(
        self, *, region: str | None = None, category: str | None = None
    ) -> list[PolicyItem]:
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


def _normalize_bizinfo_items(payload: dict[str, Any]) -> list[dict[str, Any]]:
    root = payload.get("jsonArray", payload)
    items = root.get("item", [])
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def _is_open_end_date(period: str | None) -> str | None:
    dates = re.findall(r"\d{8}", period or "")
    if len(dates) < 2:
        return None
    try:
        end = datetime.strptime(dates[-1], "%Y%m%d").date()
    except ValueError:
        return None
    return end.isoformat() if end >= date.today() else end.isoformat()


def _normalize_category(raw_category: str) -> str:
    if "창업" in raw_category:
        return "창업"
    if any(word in raw_category for word in ("경영", "기술", "인력", "금융", "내수", "수출")):
        return "경영/기술"
    return "구직창업"


def _normalize_bizinfo_item(item: dict[str, Any]) -> dict[str, Any]:
    title = item.get("pblancNm") or item.get("title") or "제목 없음"
    period = item.get("reqstBeginEndDe") or item.get("reqstDt") or ""
    category = item.get("pldirSportRealmLclasCodeNm") or item.get("lcategory") or "기타"
    summary = _strip_html(item.get("bsnsSumryCn") or item.get("description"))
    hashtags = item.get("hashTags") or ""
    regions = [tag.strip() for tag in hashtags.split(",") if tag.strip() in _REGION_NAMES]

    return {
        "id": str(item.get("pblancId") or item.get("seq") or title),
        "title": title,
        "agency": item.get("jrsdInsttNm") or item.get("author") or "기업마당",
        "category": _normalize_category(category),
        "target_description": item.get("trgetNm") or "중소기업, 소상공인 또는 예비창업자 등 공고별 대상",
        "region": regions or ["전국"],
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": True if "창업" in category or "창업" in title else None,
        "requires_business_registration": None,
        "apply_start": None,
        "apply_end": _is_open_end_date(period),
        "apply_method": item.get("reqstMthPapersCn")
        or item.get("rceptEngnHmpgUrl")
        or "기업마당 공고 원문에서 신청 방법 확인",
        "support_content": summary or "지원 내용은 원문에서 확인이 필요합니다.",
        "source_url": item.get("pblancUrl") or item.get("link") or "https://www.bizinfo.go.kr/",
    }
