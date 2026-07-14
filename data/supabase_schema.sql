-- 정책나침반 Supabase 스키마
-- 현재 앱은 기업마당/온통청년/고용24 API를 매 요청마다 라이브로 호출하며
-- 로컬 캐시가 없다. 아래 테이블은 API 장애·키 미설정 시 fallback으로 쓸
-- 캐시 데이터(주기적 배치 인제스트로 채워짐)와, 향후 pgvector 기반 RAG
-- 확장을 위한 스키마다.

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

-- 고용24 국민내일배움카드 훈련과정 캐시 (app/repositories/work24_training.py fallback용)
-- start_date/end_date/cost/capacity는 원본 API가 항상 정형 포맷을 보장하지
-- 않아 text로 저장한다 (date/numeric으로 변환 시 파싱 실패 위험).
-- course_id="work24-training-guide" 같은 안내용 합성 레코드(fallback_reason 있는 것)는
-- 실제 훈련과정이 아니므로 인제스트 시 제외한다.
create table if not exists training_courses (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'work24_training',
    course_id text not null,
    course_round text,
    title text not null,
    institution text,
    region text,
    address text,
    start_date text,
    end_date text,
    cost text,
    actual_cost text,
    ncs_code text,
    target text,
    capacity text,
    contact text,
    detail_url text,
    institution_url text,
    raw_payload jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, course_id, course_round)
);

create index if not exists training_courses_region_idx on training_courses (region);
create index if not exists training_courses_start_date_idx on training_courses (start_date);
create index if not exists training_courses_fetched_at_idx on training_courses (fetched_at);

-- 온통청년(youthcenter) 청년정책 캐시 (app/repositories/youthcenter.py fallback용)
-- application_period은 원본 API가 자유 형식 문자열로 내려줘 text로 저장한다.
-- policy_id="youthcenter-guide" 같은 안내용 합성 레코드(fallback_reason 있는 것)는
-- 실제 정책이 아니므로 인제스트 시 제외한다.
create table if not exists youth_policies (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'youthcenter',
    policy_id text not null,
    title text not null,
    organization text,
    region text,
    target_summary text,
    support_summary text,
    business_period text,
    business_end_date text,
    application_period text,
    application_method text,
    detail_url text,
    raw_payload jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, policy_id)
);

create index if not exists youth_policies_region_idx on youth_policies (region);
create index if not exists youth_policies_fetched_at_idx on youth_policies (fetched_at);

-- 고용24/워크넷 채용정보 캐시 (app/repositories/work24_recruitment.py fallback용)
-- item_type: event(채용행사) | open_recruitment(공채속보) | company(공채기업정보) | guide(안내용)
-- item_id="work24-recruitment-guide" 같은 안내용 합성 레코드(fallback_reason 있는 것)는
-- 실제 채용정보가 아니므로 인제스트 시 제외한다.
create table if not exists recruitment_infos (
    id uuid primary key default gen_random_uuid(),
    source text not null default 'work24_recruitment',
    item_id text not null,
    item_type text not null,
    title text not null,
    company text,
    region text,
    start_date text,
    end_date text,
    summary text,
    detail_url text,
    raw_payload jsonb,
    fetched_at timestamptz not null default now(),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    unique (source, item_id)
);

create index if not exists recruitment_infos_region_idx on recruitment_infos (region);
create index if not exists recruitment_infos_item_type_idx on recruitment_infos (item_type);
create index if not exists recruitment_infos_fetched_at_idx on recruitment_infos (fetched_at);

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

-- 추천 결과(말풍선 1개 = 카드 여러 개)에 대한 사용자 피드백(엄지 업/다운).
-- 같은 메시지에 다시 누르면 rating만 덮어쓴다 (session_id, message_id 유니크).
-- trace_id는 Langfuse 트레이스와 연결해 점수(score)로도 남기기 위한 참조값이다.
create table if not exists recommendation_feedback (
    session_id text not null,
    message_id text not null,
    trace_id text,
    rating text not null check (rating in ('up', 'down')),
    created_at timestamptz not null default now(),
    updated_at timestamptz not null default now(),
    primary key (session_id, message_id)
);

create index if not exists recommendation_feedback_session_id_idx on recommendation_feedback (session_id);

-- 대화 내용은 백엔드의 service role 키로만 접근한다.
alter table chat_logs enable row level security;
alter table chat_sessions enable row level security;
alter table recommendation_feedback enable row level security;
