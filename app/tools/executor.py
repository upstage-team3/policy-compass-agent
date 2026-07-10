from __future__ import annotations

import logging

from app.repositories.policy import PolicyRepository
from app.repositories.work24_recruitment import Work24RecruitmentRepository
from app.repositories.work24_training import Work24TrainingRepository
from app.repositories.youthcenter import YouthCenterRepository
from app.schemas.policy import PolicyItem
from app.tools.schemas import (
    PolicySearchInput,
    RecruitmentInfoItem,
    RecruitmentInfoSearchInput,
    TrainingCourseItem,
    TrainingCourseSearchInput,
    YouthPolicyItem,
    YouthPolicySearchInput,
)

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


class YouthPolicySearchTool:
    """온통청년 청년정책 또는 내부 fallback 정책을 검색한다."""

    name = "youth_policy_search"
    description = "청년지원사업/취업지원정책을 검색한다. 온통청년 키가 없으면 내부 정책 데이터로 폴백한다."

    def __init__(self, repository: YouthCenterRepository) -> None:
        self._repository = repository

    async def execute(self, payload: YouthPolicySearchInput) -> list[YouthPolicyItem]:
        try:
            return await self._repository.search(payload)
        except Exception:  # noqa: BLE001
            logger.exception("청년정책 검색 Tool 실행 중 오류가 발생하여 빈 결과를 반환합니다.")
            return []


class TrainingCourseSearchTool:
    """고용24 국민내일배움카드 훈련과정 검색 Tool."""

    name = "training_course_search"
    description = "관심 직무와 훈련지역을 기준으로 고용24 훈련과정을 검색한다."

    def __init__(self, repository: Work24TrainingRepository) -> None:
        self._repository = repository

    async def execute(self, payload: TrainingCourseSearchInput) -> list[TrainingCourseItem]:
        try:
            return await self._repository.search(payload)
        except Exception:  # noqa: BLE001
            logger.exception("훈련과정 검색 Tool 실행 중 오류가 발생하여 빈 결과를 반환합니다.")
            return []


class RecruitmentInfoTool:
    """고용24 채용 보조 정보 검색 Tool.

    채용정보목록/상세 권한 제한은 안내형 결과로 변환한다.
    """

    name = "recruitment_info"
    description = "고용24 채용행사/공채속보/기업정보 또는 채용 탐색 가이드를 제공한다."

    def __init__(self, repository: Work24RecruitmentRepository) -> None:
        self._repository = repository

    async def execute(self, payload: RecruitmentInfoSearchInput) -> list[RecruitmentInfoItem]:
        try:
            return await self._repository.search(payload)
        except Exception:  # noqa: BLE001
            logger.exception("채용정보 Tool 실행 중 오류가 발생하여 안내 fallback을 반환합니다.")
            return []
