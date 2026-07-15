# 🧭 정책나침반 (Policy Compass)

> 개발을 이어갈 때는 [문서 안내](docs/README.md)와
> [개발 인수인계 문서](docs/DEVELOPMENT_HANDOFF.md)를 먼저 읽으세요.

사용자의 만 나이, 취업 상태, 거주지역, 관심 분야·희망 직무 등의 조건을
분석해 청년에게 온통청년 청년정책과 고용24 훈련·채용 보조정보를 안내하는
AI 기반 Agent 챗봇입니다.

청년정책과 국비 훈련·채용 정보는 여러 서비스에 흩어져 있고, 신청 자격이 나이·
지역·취업 상태 등으로 복잡하게 구성되어 있어 본인에게 맞는 정보를
찾기 어렵습니다. 정책나침반은 사용자의 자연어 질문에서 조건을 추출하고,
부족한 정보는 되물어 보완한 뒤 공식 API에서 확인한 후보만 근거와 함께
정리합니다. 확인할 수 없는 자격은 신청 가능으로 추정하지 않습니다.

> ⚠️ 본 서비스는 **의사결정 보조 Agent**입니다. 최종 자격 판단이나 실제
> 신청은 대행하지 않으며, 항상 공식 공고문/담당 기관을 통해 재확인해야
> 합니다. 배포/연동 테스트 기준으로 데모용 대체 정책 데이터는 사용하지
> 않으며, 연결되지 않은 외부 데이터 소스는 `unavailable` 상태로 드러내
> 정상 무결과와 구분합니다.

## 핵심 기능

1. **사용자 조건 분석 및 프로필 구성** — Pydantic allowlist로 나이·취업 상태·
   거주지역 등을 검증하고 명시적 `SET/CLEAR/UNCHANGED` 의미로 세션 프로필 관리
2. **부족 조건 되묻기 (HITL)** — 추천에 꼭 필요한 조건이 부족하면 먼저
   확인하고, 후속 발화를 `KEEP/RESUME/CANCEL/REPLACE`로 구분해 미완료 작업을 관리
3. **청년정책 및 훈련·채용 보조정보 검색** — 온통청년 Open API와 고용24
   국민내일배움카드 훈련과정 API를 핵심 데이터 소스로 사용하고,
   고용24 채용정보 API는 개인키 조회 제한을 고려해 보조/확장 데이터로 유지
4. **결정론적 후보 방어** — 가중 점수 없이 세 소스 모두에 시·도/시·군·구·
   연령·관련성·허용 유형 게이트를 적용하고 합성 안내 레코드는 카드에서 제외
5. **근거 기반 추천 응답 + 재검증** — 사업명, 추천 이유, 지원 대상,
   신청 기간, 신청 방법, 확인 필요 조건, 원문 링크를 포함해 답변하며,
   "반드시 가능합니다" 같은 확정적 표현은 자동으로 완화됨
6. **명시적 세션 메모리** — 서버는 프로필·최근 8개 이력·pending·allowlist된
   직전 후보만 저장하고, 브라우저는 최근 채팅 20개·채팅별 메시지 50개를 보관

### MVP 우선순위 (2026-07-10 확정)

| 순위 | 시나리오 | 상태 |
| --- | --- | --- |
| 1 | 대학생/졸업예정자/사회초년생 대상 취업 지원정책 추천 | 핵심 MVP |
| 2 | 고용24 국민내일배움카드 기반 직무 훈련과정 추천 | 핵심 MVP |
| 3 | 고용24 채용정보 기반 공고 탐색 | 권한 허용 범위 내 보조 |
| 4 | 창업지원 질문 | MVP 범위 밖: LLM 범위 안내, Tool·외부 링크 미사용 |

MVP는 취업 준비 청년을 최우선 대상으로 한다. 기업마당 검색·추천 파이프라인은
2026-07-15 제거했으며 창업·사업자 지원 질문은 외부 Tool과 사이트 링크 없이
LLM 기반 `out_of_scope`로 처리한다.

### 외부 데이터 소스

| 우선순위 | 데이터 소스 | 용도 | 연동 상태 |
| --- | --- | --- | --- |
| 1 | 온통청년 Open API | 일자리·주거·교육·직업·훈련·금융·복지·문화·참여·기반 청년정책 | `apiKeyNm` JSON API live 검증 완료 |
| 2 | 고용24 국민내일배움카드 훈련과정 API | 직무별 교육/훈련과정 조회 | live 검증 완료 |
| 3 | 고용24 채용정보 API | 채용행사·공채속보 조회 | 활성 2종 live 검증 완료 |

기업마당과 K-Startup은 현재 Agent의 데이터 소스나 안내 대상으로 사용하지 않는다.

React UI의 첫 안내는 온통청년 공식 5개 분야(일자리, 주거,
교육·직업·훈련, 금융·복지·문화, 참여·기반)와 고용24 훈련·채용정보만
노출한다. 입력창은 `청년 정책 및 훈련에 대해 질문해 주세요...`를 사용해
범용 정부 지원사업 검색기로 오해하지 않게 한다.

## 아키텍처

```text
사용자 → FastAPI(턴 상태 초기화) → 8-node LangGraph
  prepare_request(라우팅·프로필·pending·필수 슬롯)
    ├─ RESPOND/정보 부족 → direct_response → verify_answer
    └─ SEARCH → retrieve(활성 Tool 하나 → SearchOutcome)
                 → assess_evidence(세 소스 공통 무점수 게이트)
                    ├─ 일시 장애 → retrieve 재시도(추가 1회)
                    ├─ 보정 가능한 무결과 → rewrite_query(최대 1회) → retrieve
                    ├─ 근거 없음 → direct_response → verify_answer
                    └─ 근거 있음 → build_answer → verify_answer
                                                ├─ 수정 가능 → build_answer(최대 1회)
                                                ├─ 치명적 실패 → direct_response → verify_answer
                                                └─ 통과 → finalize
  verify_answer 통과 → finalize → END
```

- **LLM**: Upstage Solar API가 행동, 응답 모드, Tool 종류, 검색어를 구조화해 결정합니다.
  출력은 Pydantic `RoutingDecision`으로 검증하며, 정상 LLM 판단을 키워드가
  덮어쓰지 않습니다. 키 누락·호출 실패·계약 오류 때만 규칙 fallback을 사용합니다.
- **데이터**: 온통청년, 고용24 훈련·채용 중 LLM이 선택한 Tool 하나만
  호출합니다. 결과는 `SearchOutcome(success/no_match/unavailable/partial)`으로
  정규화해 정상 무결과와 장애를 구분하고, guide 안내 레코드를 후보로 취급하지
  않습니다. `partial`이면 확인된 후보만 제공하면서 일부 하위 조회가 완료되지
  않았다는 경고를 답변에 명시합니다.
  고용24 채용은 지역·직무 조건을 적용할 수 있는 채용행사·공채속보만 호출하고,
  무필터 공채기업정보와 채용정보목록·상세는 활성 검색에서 제외합니다.
- **직접 응답 경로**: 일반 고민·인사, 범위 밖, 조건 확인, 소스 상태 안내,
  검색 실패는 `direct_response`로 수렴합니다. 검색이 필요 없는 정책 용어 설명은
  이 경로에서 처리하고, 현행 조건처럼 공식 데이터가 필요한 설명은
  `SEARCH/explain`으로 승격합니다. 고정 응답도 `verify_answer`를 통과해야 합니다.
- **세션**: `SupabaseChatMemoryRepository`가 검증된 프로필, 최근 8개 메시지,
  pending, allowlist된 `last_presented_candidates`의 단일 경계입니다. Supabase가
  없거나 장애여도 최대 2,048세션의 bounded local LRU mirror로 같은 프로세스의
  멀티턴을 유지합니다. 동일 세션은 `SessionLockPool`이 load→graph→save를
  직렬화합니다. 그래프는 전역 `MemorySaver` 없이 턴 상태를 요청마다 새로 만듭니다.
  React 화면은 동일한 UUIDv4를 유지하면서 로컬 저장소에
  표시용 채팅 기록을 보관하며, 민감정보를 마스킹하고 개별·전체 삭제를 지원합니다.
- **운영 방어**: 세션 ID는 UUIDv4만 허용하고 그래프 턴은 60초로 제한합니다.
  개별 LLM 요청은 8초, 소스 조회 시도는 10초, Repository HTTP는 9초로 제한합니다.
  최대 LLM 4회·소스 2회와 8초 예비 시간을 포함한 최악 경로가 60초 안에
  들어오지 않으면 설정 로드 단계에서 거절합니다.
  인프로세스 sliding-window limiter는 세션당 분당 20회, IP당 분당 120회를
  초과하면 `429 Retry-After`를 반환합니다.

## 폴더 구조

```
app/
├── api/routes/        # health, chat(SSE), recommendation feedback 엔드포인트
├── core/               # 설정, 프롬프트, LLM 클라이언트
├── graph/              # LangGraph 조립, 구조화 계약, fallback, 응답 컴포저
├── repositories/       # 온통청년·고용24 API, Supabase 메모리·피드백
├── tools/              # Pydantic Tool 입력 스키마 + Tool executor
├── schemas/            # API 요청/응답 Pydantic 모델
├── static/             # 최소 채팅 UI (정적 HTML/JS)
└── main.py             # FastAPI 앱 엔트리포인트
data/
├── chat_memory_schema.sql # 대화 메모리 전용 Supabase 스키마
├── supabase_schema.sql # 현재/과거 데이터 테이블을 포함한 전체 스키마
└── scripts/            # 훈련과정 적재 보조 스크립트
tests/                  # pytest 기반 유닛/API 테스트
frontend/               # React UI, 로컬 채팅 복원과 프런트엔드 회귀 테스트
docs/README.md              # 현재 문서와 역사·감사 문서 안내
docs/DEVELOPMENT_HANDOFF.md # 다음 개발 세션의 현재 기준 문서
```

## 실행 방법

### 1. 의존성 설치

```bash
uv sync
cp .env.example .env
```

실제 LLM을 쓰려면 `UPSTAGE_API_KEY` 를 채워주세요. 배포/연동 테스트에서는
데모용 대체 정책 데이터를 사용하지 않으므로, 외부 API 키가 없거나 권한이 제한된
데이터 소스는 `SearchOutcome.unavailable`과 명시적인 장애 안내로 드러납니다.

대화 문맥을 재시작 뒤에도 유지하려면 `data/chat_memory_schema.sql`을 Supabase
SQL Editor에서 실행하고 `SUPABASE_URL`, `SUPABASE_KEY`를 설정합니다.
`SUPABASE_KEY`에는 publishable/anon 키가 아니라 서버 전용 secret/service_role
키만 사용해야 합니다.

### 2. 서버 실행

터미널 1에서 백엔드를 실행합니다.

```bash
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

터미널 2에서 최신 React UI를 실행합니다.

```bash
cd frontend
pnpm run dev
```

- 최신 React UI: http://localhost:5173/
- 최소 정적 데모 UI: http://localhost:8000/
- API 문서(Swagger): http://localhost:8000/docs

### 3. 테스트 & 린트

```bash
uv run python -m pytest -q
uv run ruff check app/ tests/
uv run ruff format app/ tests/ --check
cd frontend && pnpm test && pnpm run build
```

### 4. Docker

```bash
docker compose up --build
```

운영 CD는 성공한 CI의 `workflow_run.head_sha`를 checkout·이미지 태그·
`APP_RELEASE_SHA`에 동일하게 사용하고, GCE에는 태그가 아니라 빌드 결과의
불변 digest(`image@sha256:...`)를 배포합니다. 컨테이너와 배포 작업의 준비 상태는
`/api/ready`로 확인합니다.

## API 요약

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/api/health` | 기존 클라이언트 호환 헬스체크 |
| GET | `/api/live` | 외부 의존성과 무관한 프로세스 생존 확인 |
| GET | `/api/ready` | release SHA와 핵심 의존성 설정 상태 확인; production 미구성 시 503 |
| POST | `/api/chat` | 동기 방식 채팅 (테스트/단순 클라이언트용) |
| POST | `/api/chat/stream` | SSE 스트리밍 채팅 |
| POST | `/api/chat/feedback` | 추천 카드 묶음에 대한 사용자 피드백 저장 |

`/api/policies`, `/api/policies/{policy_id}`, `/api/policies/search`는 기업마당·RAG-lite
제거와 함께 2026-07-15 더 이상 등록하지 않는다.

## 예시 대화

```text
사용자: 서울에 사는 만 25세 미취업 청년인데 일자리 정책 찾아줘.
Agent: 온통청년에서 확인한 조건 부합 후보를 최대 3건의 카드로 제시합니다.
       각 카드에는 공식 정책명·기관·지원 내용·신청 기간·원문 URL과
       확인할 자격 조건을 보여줍니다.
사용자: 1번 신청 방법을 자세히 알려줘.
Agent: 직전 카드의 allowlist snapshot 안에서만 신청 방법과 공식 URL을 설명합니다.
```

실제 정책명·금액·날짜·URL은 실행 시점의 API 후보에서만 표시하며
문서 예시로 임의 정책 사실을 고정하지 않습니다.

## 가드레일 및 제약사항 (Out of Scope)

- 최종 자격 판정, 실제 신청 대행, 청년정책 외 분야 답변은 지원하지 않습니다.
- 소득 기준, 고용보험 가입 여부, 병역 이력, 중복 수급 여부처럼 정밀한
  확인이 필요한 항목은 "추가 확인 필요"로 안내하며 단정하지 않습니다.
- 민감 개인정보(주민등록번호, 계좌번호 등)를 요청하지 않습니다.

## 알려진 MVP 단순화 지점 (향후 개선 과제)

- **스트리밍**: `/api/chat/stream` 은 LangGraph `astream` 업데이트를 이용해
  실제로 실행된 노드의 진행 상태를 즉시 전송합니다. 내부 state와 검증 전
  초안은 노출하지 않고, `verify_answer` 검증과 `finalize` 완료 후에만
  최종 응답을 일정 크기로 나눠 전송합니다. LLM 토큰 단위 스트리밍은
  후속 과제입니다.
- **검색·회복 계약**: `SearchOutcome`과 결정론적 게이트, 동일 검색 재시도·검색어
  재작성·답변 재검증의 상한은 구현했습니다. 다음 단계는 실 API fixture와 의미
  평가 데이터셋을 늘려 source별 관련성·자격·citation 품질을 release gate로 만드는
  것입니다.
- **온통청년/고용24 연동**: 내부 스키마와 normalizer는 구현되어 있지만,
  Repository live 검증 이력과 별개로 각 release에서 Agent 전체 경로를 다시 검증해야 합니다.
  채용정보 API는 개인키 제한이 확인되어 직접 공고용 `JobPostingItem` 대신
  채용행사·공채속보용 `RecruitmentInfoItem`을 보조 스키마로 유지합니다.
- **기업마당·가중 스코어링 이력**: 기업마당 Repository/Tool, `PolicyItem`,
  RAG-lite `/api/policies` 경로와 가중 점수 계산은 과거 구현 이력이며 현재 코드에서
  제거했습니다. 창업지원 질문은 외부 검색·사이트 링크 없이 현재 MVP 범위를 안내합니다.
- **세션 보안**: UUIDv4 검증, 단일 프로세스 세션 lock과 rate limit은 구현됐지만,
  multi-worker owner binding·DB optimistic version은 아직 없습니다. 브라우저 표시
  기록은 삭제할 수 있으나 Supabase 서버 데이터의 TTL·삭제 API도 후속 과제입니다.
- **검증된 카드·스냅샷**: 검색 검증을 통과하고 상태가 `success/partial`인 후보만
  추천 카드와 allowlist 세션 스냅샷을 갱신합니다. 검증 실패 턴은 둘 다 차단합니다.
- **SSE 상태**: `status`, `token`, `done`, `error` 이벤트와 노드별 `stage`를
  React UI에 연결했습니다. 실제 LLM token streaming은 후속 과제입니다.
