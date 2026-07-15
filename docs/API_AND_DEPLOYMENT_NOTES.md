# API 및 배포 메모

최종 갱신: 2026-07-15

## 실행 기준

현재 프로젝트는 FastAPI 단일 서버 구조다.

```bash
uv sync
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

로컬 확인:

```text
http://localhost:8000/
http://localhost:8000/docs
http://localhost:8000/health
http://localhost:8000/api/live
http://localhost:8000/api/ready
```

## 주요 API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/` | 정적 채팅 데모 UI |
| GET | `/health` | 기존 호환 헬스체크 |
| GET | `/api/health` | 기존 API 클라이언트 호환 헬스체크 |
| GET | `/api/live` | 외부 의존성과 무관한 프로세스 liveness |
| GET | `/api/ready` | release SHA와 핵심 의존성 구성 readiness |
| POST | `/api/chat` | 동기 채팅 API |
| POST | `/api/chat/stream` | SSE 스트리밍 채팅 API |
| POST | `/api/chat/feedback` | 추천 카드 묶음의 up/down 피드백 저장 및 Langfuse score 연결 |

역사 기록: `/api/v1/chat*`, `/api/policies`, `/api/policies/{policy_id}`,
`/api/policies/search`는 기업마당·RAG-lite 파이프라인과 함께 2026-07-15 제거되어
현재 앱에 등록되지 않는다.

## 채팅 요청 예시

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"550e8400-e29b-41d4-a716-446655440000\",\"message\":\"서울 사는 만 28세 미취업자인데 구직지원금 받을 수 있어?\"}"
```

`session_id`는 같은 대화 안에서 프로필과 미완료 검색 요청을 누적하는 데 사용한다.
API는 임의 문자열이나 다른 UUID 버전을 받지 않고 UUIDv4만 허용한다. 클라이언트는
새 대화마다 UUIDv4를 생성하고 같은 대화에서 유지해야 한다. UUIDv4 검증은 형식
방어일 뿐 사용자 소유권 증명이 아니므로 multi-worker owner binding은 남은 과제다.

## Supabase 대화 메모리

`data/chat_memory_schema.sql`을 Supabase SQL Editor에서 실행한다. 다음 데이터만
현재 문맥으로 다시 불러온다.

- 최근 사용자/Assistant 메시지 8개
- 지역, 나이, 정책 분야, 필요한 경우의 취업 상태 등 구조화 프로필
- 조건 확인 중인 원래 요청, Tool 종류, 검색어(`pending_request`)
- 검증을 통과해 직전에 제시한 allowlist 후보 최대 3건

`SupabaseChatMemoryRepository`가 위 상태의 단일 load/save 경계다. 메시지는 최대
4,000자까지 저장하고 주민번호·카드번호 형태는 마스킹한다. Supabase 조회 2건과
저장 2건은 각각 병렬 처리하며 요청 timeout은 3초다. Supabase가 설정되지 않았거나
조회·저장에 실패하면 최대 2,048세션의 bounded local LRU mirror가 같은 프로세스의
멀티턴 상태를 유지한다. 이 mirror는 프로세스 재시작이나 멀티워커 간 내구성을
보장하지 않는다.

그래프는 전역 `MemorySaver` 없이 컴파일되고 검색 결과·초안·검증 결과는 요청마다
초기화한다. `SessionLockPool`은 같은 프로세스·세션의 load→graph→save 전체를
직렬화한다. 그래프 실행은 60초 deadline이고, 개별 LLM은 8초, 소스는
10초, Repository HTTP는 9초로 제한한다. 인프로세스 sliding-window limiter는
세션당 분당 20회와 IP당 분당 120회로 제한하며 초과 시 429와 `Retry-After`를
반환한다. 멀티워커 owner binding, DB optimistic version, 서버 삭제 API·TTL과
분산 rate limit은 아직 구현되지 않았다.

`chat_logs`, `chat_sessions`는 RLS가 켜져 있고 클라이언트 정책은 만들지 않는다.
따라서 `SUPABASE_KEY`에는 publishable/anon 키가 아니라 백엔드 전용
secret/service_role 키를 설정해야 한다. 키 이름은 통일성을 위해
`SUPABASE_KEY`를 사용하지만 권한은 반드시 서버용이어야 한다.

## MVP 외부 API 우선순위

2026-07-10 revised 기준 MVP 핵심 대상은 대학생, 졸업예정자, 사회초년생, 미취업 청년이다.
서비스 핵심은 청년지원사업 및 취업 관련 청년 정보 챗봇이며, 현재 연결 가능한 API를 기준으로 다음 순서로 연동한다.

| 우선순위 | API | 역할 | 상태 |
| --- | --- | --- | --- |
| 1 | 온통청년 Open API | 일자리·주거·교육·복지·문화·참여 청년정책 조회 | `apiKeyNm` JSON API live 성공 |
| 2 | 고용24 국민내일배움카드 훈련과정 API | 취업 준비에 필요한 교육/훈련과정 조회 | live 성공 |
| 3 | 고용24 채용정보 API | 채용행사·공채속보 보조정보 | 활성 2종 live 성공 |

활성 검색 소스는 위 3개다. Solar, 온통청년, 고용24 훈련과 채용행사·공채속보는
실제 호출 성공 이력이 있다. 어떤 API도 연결 실패를 내부 대체 데이터로 숨기지 않는다.
고용24 개인 신청 키에는 공채기업정보 권한도 있지만 사용자 직무·지역을 적용할 수
없으므로 현재 Agent 검색에서는 호출하지 않는다.
채용정보목록과 채용정보상세 API는 개인회원 키로 사용할 수 없으므로,
직접 공고 조회가 필요할 때는 채용 탐색 가이드로 폴백한다.
창업지원 질문은 데이터 API를 호출하지 않고 LLM `out_of_scope`에서 현재 MVP 범위를
안내한다. 기업마당과 K-Startup 링크는 반환하지 않는다.
Tool 입력/출력 스키마와 사용자에게 먼저 물어볼 조건은 `docs/API_TOOL_SCHEMA_DESIGN.md`를 기준으로 구현한다.

현재 구현 상태:

- `YouthPolicySearchInput`, `TrainingCourseSearchInput`, `RecruitmentInfoSearchInput` 스키마 추가
- 고용24 훈련과정 XML normalizer와 상태형 장애 안내 추가
- 고용24 채용행사·공채속보 응답 normalizer와 실제 호출 추가
- 권한이 없는 채용정보목록·상세 endpoint는 설정과 코드 호출 대상에서 제외
- 외부 API 예외 로그에서 URL·query string·인증키 제외
- LLM 기반 `action`, `response_mode`, `request_kind`, `search_query` 계획과 Tool 단일 선택 추가
- API·Router 이중 fresh-turn reset과 pending `KEEP/RESUME/CANCEL/REPLACE` 추가
- 기업마당·Policy REST/RAG-lite·가중 스코어링 제거, 창업지원은 LLM `out_of_scope`로 통합
- 세 활성 Tool 결과를 `SearchOutcome(success/no_match/unavailable/partial)`으로 정규화하고 guide 레코드를 후보에서 제거
- 온통청년·훈련·채용 공통 결정론적 무점수 evidence gate 추가
- 8개 의미 노드와 source retry/query rewrite/answer revision의 bounded edge 추가
- 키워드 규칙을 `app/graph/fallbacks.py`로 격리
- 온통청년 `getPlcy` JSON 응답과 `YouthPolicyItem` normalizer 추가
- 포괄 청년정책 요청의 공식 5개 분야 확인과 분야별 필수 조건 분기 추가
- 온통청년 사업기간 정규화, 종료 정책 제외, 구체 검색어 보존 추가
- 일반 텍스트 응답 정리와 실제 null 신청 정보 `data_notice` 추가
- Pydantic profile allowlist와 필드별 `SET/CLEAR/UNCHANGED` 추가
- Supabase 최근 8개 대화·프로필·미완료 요청·allowlist 후보 snapshot의 단일 저장 경계 추가
- Supabase 미설정·장애용 bounded local LRU mirror와 동일 세션 lock 추가
- UUIDv4 검증, 그래프 60초·LLM 8초·소스 10초·Repository HTTP 9초 예산,
  세션·IP 인프로세스 rate limit 추가
- `direct_response` 공통 검증, PARTIAL 공개 경고, 시·군·구 gate와 검증 실패 카드·snapshot 차단 추가
- 검증 기준: 전체 로컬 Ruff·포맷·Python/프런트 회귀와 production build 통과

## 온통청년 Open API

문서:

```text
https://www.youthcenter.go.kr/cmnFooter/openapiIntro/oaiDoc
https://www.youthcenter.go.kr/cmnFooter/openapiIntro/oaiGuide
```

신청 방식:

- 온통청년 회원가입
- 로그인 후 마이페이지에서 Open API 인증키 신청
- 담당자 승인 후 인증키 발급

주요 특징:

- HTTPS 기반 API
- 응답 형식은 JSON
- 청년정책, 청년공간, 청년콘텐츠 정보를 제공
- 청년정책 목록 URL: `https://www.youthcenter.go.kr/go/ythip/getPlcy`
- 인증키는 `apiKeyNm`, 페이징은 `pageNum`/`pageSize`, 정책명 검색은 `plcyNm`을 사용

MVP 활용:

- 일자리·주거·교육·직업·훈련·금융·복지·문화·참여·기반 청년정책 검색
- 지역, 만 나이, 정책 분야, 필요한 경우의 취업 상태, 구체 키워드 기반 gate
- 추천 답변의 정책명, 지원 대상, 신청 기간, 신청 방법, 원문 링크 근거 제공

예상 환경변수:

```env
YOUTHCENTER_POLICY_API_KEY=
YOUTHCENTER_POLICY_API_URL=https://www.youthcenter.go.kr/go/ythip/getPlcy
```

## 고용24/HRD-Net 국민내일배움카드 훈련과정 API

MVP 활용:

- 국민내일배움카드로 수강 가능한 훈련과정 조회
- 취업 준비 청년에게 직무별 교육/훈련과정 추천
- 채용공고와 연결해 "필요 역량 -> 추천 훈련과정 -> 지원 가능한 공고" 흐름 구성

예상 환경변수:

```env
EMPLOYMENT24_TRAINING_API_KEY=
EMPLOYMENT24_TRAINING_API_URL=https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
```

연동 시 확인할 것:

- 응답 형식(JSON/XML), 필수 파라미터, 호출 제한 확인
- 과정명, 훈련기관, 지역, 훈련기간, 자비부담액, 상세 URL 필드 매핑

## 고용24 채용정보 API

개인회원 키 권한과 현재 Agent 사용 범위:

| API 항목 | 개인회원 키 사용 | 현재 Agent 검색 |
| --- | --- | --- |
| 채용행사 API | 가능 | 사용 |
| 공채속보 API | 가능 | 사용 |
| 공채기업정보 API | 가능 | 미사용: 직무·지역 필터 불가 |
| 채용정보목록 API | 불가 | 미사용 |
| 채용정보상세 API | 불가 | 미사용 |

MVP 활용:

- 채용행사·공채속보 조회
- 신입/공채 중심 채용 소식 보조
- 채용행사·공채속보 하위 조회 일부만 실패하면 `partial`, 전체 조회를
  확인할 수 없으면 `unavailable`로 구분하고 채용공고를 임의 생성하지 않음

예상 환경변수:

```env
EMPLOYMENT24_JOB_API_KEY=
EMPLOYMENT24_JOB_EVENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L11.do
EMPLOYMENT24_OPEN_RECRUITMENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do
```

연동 시 확인할 것:

- 채용행사·공채속보 API의 요청 URL과 파라미터 확인
- 기업회원/기관회원 키가 필요한 API인지 확인
- 응답 형식(JSON/XML), 필수 파라미터, 호출 제한 확인
- 채용공고 원문 URL, 회사명, 직무명, 지역, 마감일 필드 매핑

## 창업지원 범위

기업마당 API 연동, `PolicyItem`, 가중 스코어링, `/api/policies*`는 제거됐고
환경변수나 배포 Secret도 사용하지 않는다. 창업지원 질문은 검색 Tool 없이
`RESPOND/out_of_scope/general`로 처리하며 청년정책·구직·취업·직업훈련·채용정보라는
현재 MVP 범위를 안내한다.

## 환경변수

`.env.example`에는 키 이름만 둔다. 실제 `.env`는 로컬/VM에만 둔다.

```env
UPSTAGE_API_KEY=
YOUTHCENTER_POLICY_API_KEY=
YOUTHCENTER_POLICY_API_URL=https://www.youthcenter.go.kr/go/ythip/getPlcy
EMPLOYMENT24_TRAINING_API_KEY=
EMPLOYMENT24_TRAINING_API_URL=https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
EMPLOYMENT24_JOB_API_KEY=
EMPLOYMENT24_JOB_EVENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L11.do
EMPLOYMENT24_OPEN_RECRUITMENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do
SUPABASE_URL=
SUPABASE_KEY=
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=https://jp.cloud.langfuse.com
LANGFUSE_TRACING_ENVIRONMENT=development
SERVICE_NAME=policy-compass
APP_ENV=local
APP_RELEASE_SHA=local
CORS_ORIGINS=["http://localhost:5173","http://127.0.0.1:5173"]
AGENT_TURN_TIMEOUT_SECONDS=60
LLM_REQUEST_TIMEOUT_SECONDS=8
SOURCE_SEARCH_TIMEOUT_SECONDS=10
SOURCE_HTTP_TIMEOUT_SECONDS=9
CHAT_SESSION_RATE_LIMIT_PER_MINUTE=20
CHAT_IP_RATE_LIMIT_PER_MINUTE=120
FEEDBACK_SESSION_RATE_LIMIT_PER_MINUTE=30
FEEDBACK_IP_RATE_LIMIT_PER_MINUTE=120
```

주의:

- 실제 API 키를 문서, README, GitHub에 올리지 않는다.
- `.env`를 새 파일로 덮어쓰지 않는다.
- 배포/연동 테스트 기준으로 데모용 대체 정책 데이터 fallback은 사용하지 않는다.
- 실제 온통청년/고용24 API를 확인하려면 VM/로컬 `.env`에
  해당 API 키를 넣는다.
- `SUPABASE_KEY`는 secret/service_role 키만 사용하고 브라우저 코드에 전달하지 않는다.
- 배포 환경에서는 Langfuse 키 2개와 리전 URL을 GitHub Actions Secrets로 주입하고
  `LANGFUSE_TRACING_ENVIRONMENT=production`으로 구분한다.
- `/api/health`의 `langfuse_tracing` 값으로 배포 컨테이너가 Langfuse 키를 읽었는지 확인한다.

## LLM 사용 메모

Upstage Solar API 키가 있으면 `prepare_request` 내부 Router가 `action`, `response_mode`, `request_kind`, `search_query`, `resume_pending`을 생성하고 `RoutingDecision`으로 검증한다. `RESPOND`와 조건 부족은 `direct_response`, `SEARCH`는 `retrieve → assess_evidence`로 이동한다. 조건 질문, 일반·범위 밖 대화, gate 통과 검색 답변, source 상태 안내와 직전 후보 후속 답변은 모두 Solar를 1차 생성 경로로 사용한다. 두 경로의 최종 문구는 `verify_answer`를 통과하고 오류가 있으면 같은 근거와 검증 오류로 한 번 다시 작성한다. 키 누락·호출 실패·재검증 실패 때만 결정론적 템플릿으로 수렴한다. 창업지원은 LLM `out_of_scope`로 분류하지만 Tool은 호출하지 않는다.

LLM은 다음 언어 이해·생성 역할을 담당한다.

- 사용자 조건 추출 보조
- 질문 의미 기반 의도·Tool·검색어 계획
- 부족 조건 확인 질문과 일반·범위 밖 대화
- 검증된 공식 후보의 목적별 설명과 비교
- no-match/unavailable/partial 상태 안내
- allowlist된 직전 후보의 후속 설명
- 후보 정책을 사용자 관점으로 설명
- 확인 필요 조건을 자연어로 정리

LLM이 하면 안 되는 것:

- 후보 데이터에 없는 정책명 생성
- 출처 없는 금액, 날짜, 자격 조건 생성
- 최종 자격 판정
- 민감 개인정보 요청

검색 결과 응답은 `app/graph/response_composer.py`가 담당한다. 후보 데이터가 있으면 grounded LLM 응답을 시도하고, 실패하면 같은 데이터를 사용하는 결정론적 템플릿으로 전환한다. `PARTIAL` 결과는 일부 하위 조회가 완료되지 않았다는 공개 경고를 답변 앞에 붙인다. 추천 카드와 `last_presented_candidates`는 gate와 답변 검증을 통과한 `success`/`partial` 검색 턴에서만 만든다.

## Docker

```bash
docker compose up --build
```

현재 Docker 기준 포트:

```text
host 8000 -> container 8000
```

## Health와 readiness

- `/api/live`는 프로세스가 HTTP 요청을 받을 수 있는지만 확인하고 항상 200을 반환한다.
- `/api/ready`는 `APP_RELEASE_SHA`, `APP_ENV`와 Upstage, 온통청년, Work24 훈련,
  Work24 채용, Supabase의 **구성 여부만** 비밀값 없이 반환한다.
- 로컬/CI에서 필수 구성이 빠지면 `200 degraded`, `APP_ENV=production`에서는
  `503 not_ready`다.
- 현재 readiness는 실제 upstream 연결이나 circuit 상태를 probe하지 않는다.

## CD revision 불변식

CD는 성공한 CI가 검증한 커밋과 실제 배포 이미지를 다음처럼 고정한다.

1. `RELEASE_SHA`는 `github.event.workflow_run.head_sha`를 사용한다. 수동 실행만
   `github.sha`를 사용한다.
2. checkout, SHA 이미지 태그, `APP_RELEASE_SHA`가 같은 전체 SHA를 사용한다.
3. GCE는 태그가 아닌 build output digest의
   `ghcr.io/.../policy-compass-agent@sha256:...`를 pull/run한다.
4. `.current_image`와 `.previous_image`에도 digest reference를 기록해 rollback한다.
5. Compose healthcheck와 배포 후 확인은 `/api/ready`를 사용한다.

## GCP VM 권장 설정

초기 추천:

```text
Machine type: e2-medium
OS: Ubuntu 22.04 LTS 또는 24.04 LTS
Disk: Balanced Persistent Disk 30GB
Region: asia-northeast3-a 또는 asia-northeast3-b
```

방화벽:

- 개발/실습 단계: 8000 허용
- URL 제출/정식 접근: 80 허용
- HTTPS 적용 시: 443 허용
- SSH: 22 허용

외부 확인:

```text
http://VM_EXTERNAL_IP:8000/
http://VM_EXTERNAL_IP:8000/health
http://VM_EXTERNAL_IP:8000/api/live
http://VM_EXTERNAL_IP:8000/api/ready
http://VM_EXTERNAL_IP:8000/docs
```

## URL 신청 시 주의

어떤 신청 폼은 `http://IP:8000`처럼 포트가 붙은 URL을 거부할 수 있다.

그 경우 다음 중 하나로 처리한다.

1. 신청란에는 `http://VM_EXTERNAL_IP`만 입력한다.
2. VM에서 Nginx를 설치해 80번 포트를 8000번으로 프록시한다.

Nginx 구성 방향:

```text
외부 http://VM_EXTERNAL_IP
-> VM 80번 포트
-> 내부 http://127.0.0.1:8000
```

## 배포 전 확인할 것

- [ ] `.env`에 필요한 키가 있는가?
- [ ] `.env`가 GitHub에 올라가지 않는가?
- [ ] `/api/live`가 200이고 `/api/ready`가 배포 환경에서 `ready`인가?
- [ ] `/api/ready.release_sha`가 CI의 exact head SHA와 같은가?
- [ ] 실행 중 이미지가 `.current_image`의 `@sha256:` digest와 같은가?
- [ ] `/` UI가 정상 표시되는가?
- [ ] `/api/chat`이 정상 응답하는가?
- [ ] UUIDv4가 아닌 `session_id`가 422로 거절되는가?
- [ ] 같은 세션 동시 요청이 한 프로세스에서 load→graph→save 순서로 직렬화되는가?
- [ ] 그래프 60초 deadline과 세션·IP 초과 요청이 각각 timeout/429 계약으로 끝나는가?
- [ ] 창업지원 질문이 Tool 없이 LLM `out_of_scope`로 응답하고 외부 링크를 반환하지 않는가?
- [ ] 온통청년 API 신청 상태와 키 발급 여부를 확인했는가?
- [ ] 고용24 채용정보 API 개인키 조회 제한을 `unavailable`/명시 안내로 처리하는가?
- [ ] 추천 응답에 원문 링크가 포함되는가?
- [ ] PARTIAL 응답에 공개 경고가 있고 검증 실패 응답에는 카드·후보 snapshot이 없는가?
- [ ] 신청 가능 여부를 확정적으로 말하지 않는가?
