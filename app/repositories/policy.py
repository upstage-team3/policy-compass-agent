from __future__ import annotations

import json
import logging
from functools import lru_cache
from typing import Any

import httpx

from app.core.config import get_settings
from app.schemas.policy import PolicyItem
from app.tools.schemas import PolicySearchInput

logger = logging.getLogger(__name__)


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
                    params={"crtfcKey": self._settings.bizinfo_api_key, "dataType": "json"},
                )
                response.raise_for_status()
        except Exception:  # noqa: BLE001 - 외부 API 장애 시 mock 데이터로 폴백
            logger.warning("기업마당 API 호출 실패, mock 데이터로 폴백합니다.", exc_info=True)
            return None
        else:
            logger.info(
                "기업마당 API 응답 정규화는 data/scripts/ingest_data.py 에서 처리됩니다. "
                "정규화된 캐시가 없어 mock 데이터로 폴백합니다."
            )
            return None

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
