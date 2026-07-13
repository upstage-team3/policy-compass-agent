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
-- pgvector의 vector HNSW 인덱스는 최대 2,000차원만 지원한다.
-- Solar 4,096차원 임베딩은 우선 exact scan으로 유지하고, 실제 RAG 도입 시
-- 차원 축소 또는 별도 검색 전략을 확정한 뒤 ANN 인덱스를 추가한다.

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

-- 구조화된 멀티턴 상태. 전체 대화는 chat_logs에, 현재 검색 계획과 프로필만 여기에 보관한다.
create table if not exists chat_sessions (
    session_id text primary key,
    profile jsonb not null default '{}'::jsonb,
    pending_request jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists chat_sessions_updated_at_idx on chat_sessions (updated_at desc);

-- 대화 내용은 백엔드의 service role 키로만 접근한다.
alter table chat_logs enable row level security;
alter table chat_sessions enable row level security;
