from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.repositories.policy import PolicyRepository
from app.repositories.rag import RagRepository
from app.schemas.policy import PolicyItem, PolicySearchRequest

router = APIRouter(prefix="/policies", tags=["policies"])

_policy_repo = PolicyRepository()
_rag_repo = RagRepository(_policy_repo)


@router.get("", response_model=list[PolicyItem])
async def list_policies(
    region: str | None = Query(default=None),
    category: str | None = Query(default=None),
) -> list[PolicyItem]:
    """조건(지역/카테고리) 기반 정책 목록 조회."""
    return await _policy_repo.list_all(region=region, category=category)


@router.post("/search", response_model=list[PolicyItem])
async def search_policies(body: PolicySearchRequest) -> list[PolicyItem]:
    """RAG(경량 키워드 검색) 기반 최신 공고 검색."""
    return await _rag_repo.search(body.query, top_k=body.top_k)


@router.get("/{policy_id}", response_model=PolicyItem)
async def get_policy(policy_id: str) -> PolicyItem:
    policy = await _policy_repo.get_by_id(policy_id)
    if policy is None:
        raise HTTPException(status_code=404, detail="정책을 찾을 수 없습니다.")
    return policy
