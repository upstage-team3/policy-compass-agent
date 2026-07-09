from __future__ import annotations

from app.repositories.policy import PolicyRepository
from app.schemas.policy import PolicyItem


class RagRepository:
    """정책 공고 RAG 검색 계층.

    MVP에서는 Supabase + pgvector 임베딩 검색 대신 키워드 매칭 기반의
    경량 검색("RAG-lite")을 사용한다. 인터페이스(search)는 그대로 유지한 채,
    추후 `data/supabase_schema.sql` 에 정의된 pgvector 테이블을 사용하는
    임베딩 검색으로 내부 구현만 교체할 수 있도록 설계했다.
    """

    def __init__(self, policy_repository: PolicyRepository | None = None) -> None:
        self._policy_repository = policy_repository or PolicyRepository()

    async def search(self, query: str, *, top_k: int = 5) -> list[PolicyItem]:
        policies = await self._policy_repository.list_all()
        tokens = [tok for tok in query.replace(",", " ").split() if len(tok) > 1]

        scored: list[tuple[float, PolicyItem]] = []
        for policy in policies:
            haystack = f"{policy.title} {policy.target_description} {policy.support_content}"
            hits = sum(1 for tok in tokens if tok in haystack)
            if hits:
                scored.append((hits / max(len(tokens), 1), policy))

        scored.sort(key=lambda pair: pair[0], reverse=True)
        return [policy for _, policy in scored[:top_k]] or policies[:top_k]
