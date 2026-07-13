-- 정책나침반 대화 메모리 전용 스키마
-- Supabase SQL Editor에서 이 파일만 실행해도 멀티턴 메모리를 사용할 수 있다.

create table if not exists chat_logs (
    id bigint generated always as identity primary key,
    session_id text not null,
    role text not null check (role in ('user', 'assistant')),
    content text not null,
    intent text,
    created_at timestamptz not null default now()
);

create index if not exists chat_logs_session_id_idx
    on chat_logs (session_id, created_at desc);

create table if not exists chat_sessions (
    session_id text primary key,
    profile jsonb not null default '{}'::jsonb,
    pending_request jsonb not null default '{}'::jsonb,
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now()
);

create index if not exists chat_sessions_updated_at_idx
    on chat_sessions (updated_at desc);

-- 대화 내용은 브라우저의 publishable/anon 키로 읽거나 쓸 수 없게 한다.
-- 백엔드의 SUPABASE_KEY에는 secret/service_role 키를 설정하며 service role은 RLS를 우회한다.
alter table chat_logs enable row level security;
alter table chat_sessions enable row level security;
