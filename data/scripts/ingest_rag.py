"""정책 공고를 Supabase(pgvector)에 임베딩하여 적재하는 향후 확장용 스크립트.

MVP에는 포함되지 않는 향후 개선 과제(RAG 고도화)를 위한 골격만 제공한다.
SUPABASE_URL / SUPABASE_SERVICE_KEY / UPSTAGE_API_KEY 가 모두 설정된 경우에만
실제 적재를 시도하고, 그렇지 않으면 무엇이 필요한지 안내만 출력한다.

실행: uv run python data/scripts/ingest_rag.py
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path

import httpx

DATA_DIR = Path(__file__).resolve().parent.parent
POLICIES_PATH = DATA_DIR / "mock_policies.json"

EMBEDDING_URL = "https://api.upstage.ai/v1/embeddings"
EMBEDDING_MODEL = "embedding-query"


def load_policies() -> list[dict]:
    return json.loads(POLICIES_PATH.read_text(encoding="utf-8"))


def build_chunk_text(policy: dict) -> str:
    return (
        f"{policy['title']} / {policy['agency']} / {policy['target_description']} / "
        f"{policy['support_content']}"
    )


def embed_text(text: str, api_key: str) -> list[float]:
    response = httpx.post(
        EMBEDDING_URL,
        headers={"Authorization": f"Bearer {api_key}"},
        json={"model": EMBEDDING_MODEL, "input": text},
        timeout=30,
    )
    response.raise_for_status()
    return response.json()["data"][0]["embedding"]


def upsert_to_supabase(
    supabase_url: str, service_key: str, policy: dict, chunk_text: str, embedding: list[float]
) -> None:
    headers = {
        "apikey": service_key,
        "Authorization": f"Bearer {service_key}",
        "Content-Type": "application/json",
        "Prefer": "resolution=merge-duplicates",
    }
    httpx.post(
        f"{supabase_url}/rest/v1/policies",
        headers=headers,
        json={**{k: v for k, v in policy.items()}},
        timeout=15,
    ).raise_for_status()
    httpx.post(
        f"{supabase_url}/rest/v1/policy_embeddings",
        headers=headers,
        json={"policy_id": policy["id"], "chunk_text": chunk_text, "embedding": embedding},
        timeout=15,
    ).raise_for_status()


def main() -> None:
    supabase_url = os.getenv("SUPABASE_URL")
    service_key = os.getenv("SUPABASE_SERVICE_KEY")
    upstage_key = os.getenv("UPSTAGE_API_KEY")

    missing = [
        name
        for name, value in (
            ("SUPABASE_URL", supabase_url),
            ("SUPABASE_SERVICE_KEY", service_key),
            ("UPSTAGE_API_KEY", upstage_key),
        )
        if not value
    ]
    if missing:
        print(
            "[ingest_rag] 다음 환경변수가 없어 임베딩 적재를 건너뜁니다: " + ", ".join(missing),
            file=sys.stderr,
        )
        print(
            "[ingest_rag] MVP는 키워드 기반 RAG-lite(app/repositories/rag.py)로 동작하며, "
            "이 스크립트는 pgvector 고도화를 위한 향후 확장 과제입니다."
        )
        return

    policies = load_policies()
    for policy in policies:
        chunk_text = build_chunk_text(policy)
        embedding = embed_text(chunk_text, upstage_key)
        upsert_to_supabase(supabase_url, service_key, policy, chunk_text, embedding)
        print(f"[ingest_rag] {policy['id']} 임베딩 적재 완료")


if __name__ == "__main__":
    main()
