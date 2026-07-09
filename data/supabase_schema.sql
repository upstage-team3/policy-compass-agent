-- 정책나침반 향후 확장용 Supabase 스키마
-- MVP는 data/mock_policies.json + 기업마당 API 조합으로 동작하며,
-- 아래 스키마는 pgvector 기반 RAG 및 정책 데이터 영속화를 위한 확장 설계다.

create extension if not exists vector;
create extension if not exists pgcrypto;

-- 정규화된 정책 공고 데이터
create table if not exists policies (
    id text primary key,
    title text not null,
    agency text not null,
    category text not null,
    target_description text not null,
    region text[] not null default array['전국'],
    min_age integer,
    max_age integer,
    target_employment_status text[] not null default array[]::text[],
    target_entrepreneur boolean,
    requires_business_registration boolean,
    apply_start date,
    apply_end date,
    apply_method text not null,
    support_content text not null,
    source_url text not null,
    raw_payload jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

-- 정책 본문/첨부문서 청크에 대한 임베딩 (pgvector)
-- Upstage Embedding 기준 차원(4096)을 기본값으로 두되, 실제 사용 모델에 맞게 조정한다.
create table if not exists policy_embeddings (
    id uuid primary key default gen_random_uuid(),
    policy_id text not null references policies (id) on delete cascade,
    chunk_text text not null,
    embedding vector(4096),
    created_at timestamptz not null default now()
);

create index if not exists policy_embeddings_policy_id_idx on policy_embeddings (policy_id);
create index if not exists policy_embeddings_embedding_idx
    on policy_embeddings using hnsw (embedding vector_cosine_ops);

-- 세션 기반 대화 로그 (민감 개인정보 미저장, 데모 환경에서는 최소 로그만 유지)
create table if not exists chat_logs (
    id bigint generated always as identity primary key,
    session_id text not null,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    intent text,
    created_at timestamptz not null default now()
);

create index if not exists chat_logs_session_id_idx on chat_logs (session_id);
