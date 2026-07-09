from __future__ import annotations

import logging

from app.repositories.policy import PolicyRepository
from app.schemas.policy import PolicyItem
from app.tools.schemas import PolicySearchInput

logger = logging.getLogger(__name__)


class PolicySearchTool:
    """LangGraph 노드가 사용하는 정책 검색 Tool.

    Repository 호출을 감싸서 입력을 검증하고, 외부 데이터 소스 장애 시에도
    Agent 실행 흐름이 끊기지 않도록 빈 결과로 안전하게 폴백한다.
    """

    name = "policy_search"
    description = "사용자 조건(지역/취업상태/창업여부/관심분야)에 맞는 정부 지원 정책을 검색한다."

    def __init__(self, repository: PolicyRepository) -> None:
        self._repository = repository

    async def execute(self, payload: PolicySearchInput) -> list[PolicyItem]:
        try:
            return await self._repository.search(payload)
        except Exception:  # noqa: BLE001 - 외부 데이터 소스 장애 시에도 흐름 유지
            logger.exception("정책 검색 Tool 실행 중 오류가 발생하여 빈 결과를 반환합니다.")
            return []
