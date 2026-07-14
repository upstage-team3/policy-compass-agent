from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.http import log_external_api_error
from app.core.regions import (
    bizinfo_effective_regions,
    bizinfo_region_tag,
    nearest_sidos,
    region_distance_km,
    region_match_scope,
)
from app.core.relevance import policy_matches_interest
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

_NEARBY_RESULT_LIMIT = 3


def _filter_business_profile(
    policies: list[dict[str, Any]],
    query: PolicySearchInput,
) -> list[dict[str, Any]]:
    filtered = policies
    if query.is_entrepreneur:
        filtered = [policy for policy in filtered if policy["category"] in ("창업", "경영/기술")]
    elif query.employment_status == "unemployed_seeking_job":
        filtered = [policy for policy in filtered if policy["category"] == "구직창업"]

    if query.has_registered_business is not None:
        filtered = [
            policy
            for policy in filtered
            if policy.get("requires_business_registration") in {None, query.has_registered_business}
        ]
    return filtered


def _rank_business_relevance(
    policies: list[dict[str, Any]],
    query: PolicySearchInput,
) -> list[dict[str, Any]]:
    if not query.interest_fields:
        return policies
    return sorted(
        policies,
        key=lambda policy: policy_matches_interest(
            query.interest_fields,
            title=policy.get("title", ""),
            category=policy.get("category", ""),
            support_content=policy.get("support_content", ""),
        ),
        reverse=True,
    )


def _primary_region_policies(
    policies: list[dict[str, Any]],
    user_region: str | None,
) -> list[dict[str, Any]]:
    primary: list[dict[str, Any]] = []
    for policy in policies:
        scope = region_match_scope(user_region, policy.get("region"))
        if scope not in {"exact", "nationwide"}:
            continue
        primary.append({**policy, "match_scope": scope, "distance_km": None})
    return primary


class PolicyRepository:
    """정책 공고 데이터 접근 계층.

    기업마당 Open API 연동을 시도하고 실제 응답을 PolicyItem 스키마로
    정규화한다. API 키가 없거나 호출이 실패하면 빈 결과를 반환한다.
    """

    def __init__(self) -> None:
        self._settings = get_settings()

    async def _fetch_remote(self, query: PolicySearchInput | None = None) -> list[dict[str, Any]] | None:
        if not self._settings.bizinfo_api_key:
            return None
        try:
            async with httpx.AsyncClient(timeout=10) as client:
                response = await client.get(
                    self._settings.bizinfo_base_url,
                    params=self._build_params(query),
                )
                response.raise_for_status()
                payload = response.json()
        except Exception as exc:  # noqa: BLE001 - 외부 API 장애 시 빈 결과 반환
            log_external_api_error(logger, "기업마당 API", exc)
            return None

        return [_normalize_bizinfo_item(item) for item in _normalize_bizinfo_items(payload)]

    def _build_params(self, query: PolicySearchInput | None) -> dict[str, str]:
        limit = min(max(query.limit * 5, 20), 100) if query else 20
        params = {
            "crtfcKey": self._settings.bizinfo_api_key or "",
            "dataType": "json",
            "searchCnt": str(limit),
            "pageUnit": str(limit),
            "pageIndex": "1",
        }
        if query and (query.is_entrepreneur or "창업" in query.keywords):
            params["searchLclasId"] = FIELD_CODES["창업"]
        hashtags = []
        if query and (region_tag := bizinfo_region_tag(query.region)):
            hashtags.append(region_tag)
        if query:
            hashtags.extend(query.interest_fields)
        if hashtags:
            params["hashtags"] = ",".join(dict.fromkeys(hashtags))
        return params

    async def _all_policies(self, query: PolicySearchInput | None = None) -> list[dict[str, Any]]:
        remote = await self._fetch_remote(query)
        return remote if remote is not None else []

    async def search(self, query: PolicySearchInput) -> list[PolicyItem]:
        policies = _rank_business_relevance(
            _filter_business_profile(await self._all_policies(query), query),
            query,
        )
        primary = _primary_region_policies(policies, query.region)
        if primary:
            return [PolicyItem(**policy) for policy in primary[: query.limit]]

        if not query.region:
            return []

        nearby: dict[str, dict[str, Any]] = {}
        # 외부 API를 시·도 전체에 순차 호출하지 않도록 가장 가까운 5개만 탐색한다.
        for nearby_sido, _ in nearest_sidos(query.region)[:5]:
            nearby_query = query.model_copy(update={"region": nearby_sido})
            nearby_policies = _rank_business_relevance(
                _filter_business_profile(await self._all_policies(nearby_query), query),
                query,
            )

            nationwide = _primary_region_policies(nearby_policies, query.region)
            if nationwide:
                return [PolicyItem(**policy) for policy in nationwide[: query.limit]]

            for policy in nearby_policies:
                if region_match_scope(nearby_sido, policy.get("region")) != "exact":
                    continue
                distance = region_distance_km(query.region, policy.get("region"))
                if distance is None:
                    continue
                nearby.setdefault(
                    policy["id"],
                    {**policy, "match_scope": "nearby", "distance_km": distance},
                )
            if len(nearby) >= _NEARBY_RESULT_LIMIT:
                break

        ordered = sorted(nearby.values(), key=lambda policy: policy["distance_km"])
        return [PolicyItem(**policy) for policy in ordered[:_NEARBY_RESULT_LIMIT]]

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
            policies = [
                policy
                for policy in policies
                if region_match_scope(region, policy.get("region")) in {"exact", "nationwide"}
            ]
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
    if isinstance(root, list):
        return [item for item in root if isinstance(item, dict)]
    while isinstance(root, dict) and "body" in root:
        root = root["body"]
    if isinstance(root, dict) and "items" in root and isinstance(root["items"], dict):
        root = root["items"]
    items = root.get("item", []) if isinstance(root, dict) else []
    if isinstance(items, dict):
        items = [items]
    return items if isinstance(items, list) else []


def _period_dates(period: str | None) -> tuple[str | None, str | None]:
    dates = re.findall(r"\d{4}[-./]?\d{2}[-./]?\d{2}", period or "")
    if not dates:
        return None, None
    start = None
    end = None
    try:
        start = _parse_date(dates[0])
    except ValueError:
        start = None
    if len(dates) >= 2:
        try:
            end = _parse_date(dates[-1])
        except ValueError:
            end = None
    return start, end


def _parse_date(value: str) -> str:
    compact = re.sub(r"\D", "", value)
    return datetime.strptime(compact, "%Y%m%d").date().isoformat()


def _normalize_category(raw_category: str) -> str:
    if "창업" in raw_category:
        return "창업"
    if any(word in raw_category for word in ("경영", "기술", "인력", "금융", "내수", "수출")):
        return "경영/기술"
    return "구직창업"


def _infer_business_registration_requirement(*values: str) -> bool | None:
    """공고 본문에 명시된 예비창업/기창업 조건만 구조화한다."""

    text = _strip_html(" ".join(value for value in values if value))
    has_pre_entrepreneur = bool(re.search(r"예비\s*창업|창업\s*예정", text))
    explicitly_unregistered = bool(
        re.search(r"사업자\s*등록(?:증)?(?:을|이)?\s*(?:하지\s*않은|하지\s*않고|없는|전|미등록)", text)
    )
    has_registered_business = any(
        (
            bool(re.search(r"창업\s*(?:약\s*)?\d+\s*년\s*(?:이내|미만)", text)),
            bool(re.search(r"\d+\s*년\s*(?:이내|미만)\s*(?:기업|업체|스타트업)", text)),
            "업력" in text,
            "사업자등록" in text,
            "등록업체" in text,
            "등록기업" in text,
            "창업기업" in text,
        )
    )
    if has_pre_entrepreneur and explicitly_unregistered:
        return False
    if has_pre_entrepreneur and not has_registered_business:
        return False
    if has_registered_business and not has_pre_entrepreneur:
        return True
    return None


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
    agency = _first_non_empty(item, "jrsdInsttNm", "author", "agency", "organNm") or "기업마당"
    regions = bizinfo_effective_regions(
        hashtags,
        title=title,
        summary=summary,
        agency=agency,
    )
    requires_business_registration = _infer_business_registration_requirement(title, summary)

    return {
        "id": _first_non_empty(item, "pblancId", "seq", "id") or title,
        "title": title,
        "agency": agency,
        "category": _normalize_category(category),
        "target_description": target or "대상 조건은 기업마당 공고 원문에서 확인이 필요합니다.",
        "region": regions,
        "min_age": None,
        "max_age": None,
        "target_employment_status": [],
        "target_entrepreneur": True if "창업" in category or "창업" in title else None,
        "requires_business_registration": requires_business_registration,
        "apply_start": apply_start,
        "apply_end": apply_end,
        "apply_method": apply_method or "신청 방법은 기업마당 공고 원문에서 확인이 필요합니다.",
        "support_content": summary or "지원 내용은 원문에서 확인이 필요합니다.",
        "source_url": source_url or "https://www.bizinfo.go.kr/",
        "match_scope": "unknown",
        "distance_km": None,
    }
