# 🧭 정책나침반 (Policy Compass)

> 개발을 이어갈 때는 [개발 인수인계 문서](docs/DEVELOPMENT_HANDOFF.md)를 먼저 읽으세요. 현재 코드 구조, 로컬 변경, 검증 결과와 다음 작업 순서가 정리되어 있습니다.

사용자의 나이, 취업 상태, 졸업 여부, 거주지역, 관심 직무 등의 조건을 분석해
대학생, 졸업예정자, 사회초년생, 미취업 청년에게 맞는 취업 지원정책과
채용 정보를 추천하고 안내하는 AI 기반 Agent 챗봇입니다.

기존 청년 취업 지원 정보는 여러 사이트에 흩어져 있고, 신청 자격이 나이·소득·
지역·졸업 여부·취업 상태 등으로 복잡하게 구성되어 있어 본인에게 맞는 사업을
찾기 어렵습니다. 정책나침반은 사용자의 자연어 질문에서 조건을 추출하고,
부족한 정보는 되물어 보완한 뒤, 조건과 공고 데이터를 비교해 신청 가능성이
높은 취업 지원사업과 관련 채용 정보를 근거와 함께 추천합니다.

> ⚠️ 본 서비스는 **의사결정 보조 Agent**입니다. 최종 자격 판단이나 실제
> 신청은 대행하지 않으며, 항상 공식 공고문/담당 기관을 통해 재확인해야
> 합니다. 배포/연동 테스트 기준으로 데모용 대체 정책 데이터는 사용하지
> 않으며, 연결되지 않은 외부 데이터 소스는 빈 결과 또는 명시적인 안내
> fallback으로 처리합니다.

## 핵심 기능

1. **사용자 조건 분석 및 프로필 구성** — 나이, 취업 상태, 졸업 여부, 거주지역,
   관심 직무/산업, 희망 근무지역 등을 자연어에서 추출해 세션 단위로 누적 관리
2. **부족 조건 되묻기 (HITL)** — 추천에 꼭 필요한 조건(거주지역, 나이,
   취업 상태, 졸업 여부)이 부족하면 먼저 확인 질문을 함
3. **청년 취업정책 및 훈련과정 검색** — 온통청년 Open API와 고용24
   국민내일배움카드 훈련과정 API를 핵심 데이터 소스로 사용하고,
   고용24 채용정보 API는 개인키 조회 제한을 고려해 보조/확장 데이터로 유지
4. **자격 적합도 스코어링** — 지역/연령/취업상태/졸업여부/관심분야/신청기간을
   규칙 기반으로 비교해 점수·추천 이유·확인 필요 조건을 계산
5. **근거 기반 추천 응답 + 가드레일** — 사업명, 추천 이유, 지원 대상,
   신청 기간, 신청 방법, 확인 필요 조건, 원문 링크를 포함해 답변하며,
   "반드시 가능합니다" 같은 확정적 표현은 자동으로 완화됨
6. **새로고침 대화 복원** — 브라우저에는 최근 채팅 20개·채팅별 메시지
   50개를 제한적으로 저장하고, 같은 UUID를 백엔드 세션 키로 유지해
   새로고침 뒤에도 화면 기록과 멀티턴 문맥을 이어감

### MVP 우선순위 (2026-07-10 확정)

| 순위 | 시나리오 | 상태 |
| --- | --- | --- |
| 1 | 대학생/졸업예정자/사회초년생 대상 취업 지원정책 추천 | 핵심 MVP |
| 2 | 고용24 국민내일배움카드 기반 직무 훈련과정 추천 | 핵심 MVP |
| 3 | 고용24 채용정보 기반 공고 탐색 | 권한 허용 범위 내 보조 |
| 4 | 기업마당 기반 창업/사업자 지원사업 추천 | 보조 범위 |

MVP는 취업 준비 청년을 최우선 대상으로 한다. 창업/소상공인 추천은 기존
기업마당 API를 유지하되 발표와 개발의 중심 시나리오에서는 제외한다.

### 외부 데이터 소스

| 우선순위 | 데이터 소스 | 용도 | 연동 상태 |
| --- | --- | --- | --- |
| 1 | 온통청년 Open API | 청년 취업정책 조회 | `apiKeyNm` JSON API live 검증 완료 |
| 2 | 고용24 국민내일배움카드 훈련과정 API | 직무별 교육/훈련과정 조회 | live 검증 완료 |
| 3 | 고용24 채용정보 API | 채용행사, 공채속보, 공채기업정보 조회 | 허용 3종 live 검증 완료 |
| 4 | 기업마당 지원사업정보 API | 창업/사업자/중소기업 지원사업 조회 | live 검증 완료 |

## 아키텍처

```
사용자 → [FastAPI] → [LangGraph Agent]
                        Router LLM
                        └─ RoutingDecision(action, response_mode, request_kind, search_query)
                          ├─ RESPOND → Conversation Node
                          └─ SEARCH
                               → Profile Extractor Node
                               → Missing Slot Node
                                    ├─ 부족 → 되묻기
                                    └─ 충분 → request_kind별 Tool 하나
                                              → Eligibility Scorer Node
                                              → Grounded Response Composer
                        → Guardrail Node → 최종 응답
```

- **LLM**: Upstage Solar API가 행동, 응답 모드, Tool 종류, 검색어를 구조화해 결정합니다.
  출력은 Pydantic `RoutingDecision`으로 검증하며, 정상 LLM 판단을 키워드가
  덮어쓰지 않습니다. 키 누락·호출 실패·계약 오류 때만 규칙 fallback을 사용합니다.
- **데이터**: 온통청년, 고용24 훈련·채용, 기업마당 중 LLM이 선택한 Tool
  하나만 호출합니다. 연결 실패를 데모 데이터로 숨기지 않고 빈 결과 또는
  명시적인 안내로 처리합니다.
  고용24 채용은 개인회원에 허용된 채용행사·공채속보·공채기업정보만
  호출하고, 채용정보목록·상세는 호출하지 않습니다.
- **Conversation 경로**: 일반 고민·인사와 검색이 필요 없는 제도 설명은 하나의
  Conversation Node가 처리합니다. 특정 정책의 현재 조건 설명처럼 공식 데이터가
  필요한 질문은 `SEARCH/explain`으로 Tool을 거쳐 grounded 응답을 만듭니다.
- **세션**: Supabase에 최근 8개 메시지, 사용자 프로필, 조건 확인 중인 원래
  검색 계획을 저장합니다. 프로세스 재시작이나 재배포 뒤에도 문맥을 복원하며,
  주민등록번호·카드번호 형태는 저장 전에 마스킹합니다. `MemorySaver`는 실행 중
  그래프 상태를 보조합니다. React 화면은 동일한 UUID를 유지하면서 로컬 저장소에
  표시용 채팅 기록을 보관하며, 민감정보를 마스킹하고 개별·전체 삭제를 지원합니다.

## 폴더 구조

```
app/
├── api/routes/        # health, chat(SSE), policies REST 엔드포인트
├── core/               # 설정, 프롬프트, LLM 클라이언트
├── graph/              # LangGraph 조립, 구조화 계약, fallback, 응답 컴포저
├── repositories/       # 정책 데이터 접근(policy.py) 및 RAG-lite 검색(rag.py)
├── tools/              # Pydantic Tool 입력 스키마 + Tool executor
├── schemas/            # API 요청/응답 Pydantic 모델
├── static/             # 최소 채팅 UI (정적 HTML/JS)
└── main.py             # FastAPI 앱 엔트리포인트
data/
├── chat_memory_schema.sql # 대화 메모리 전용 Supabase 스키마
├── supabase_schema.sql # Supabase+pgvector RAG 확장 포함 전체 스키마
└── scripts/            # 기업마당 데이터 적재 / RAG 임베딩 적재 스크립트
tests/                  # pytest 기반 유닛/API 테스트
frontend/               # React UI, 로컬 채팅 복원과 프런트엔드 회귀 테스트
docs/DEVELOPMENT_HANDOFF.md # 다음 개발 세션의 현재 기준 문서
```

## 실행 방법

### 1. 의존성 설치

```bash
uv sync
cp .env.example .env
```

실제 LLM을 쓰려면 `UPSTAGE_API_KEY` 를 채워주세요. 배포/연동 테스트에서는
데모용 대체 정책 데이터 fallback을 사용하지 않으므로, 외부 API 키가 없거나 권한이
제한된 데이터 소스는 빈 결과 또는 안내 fallback으로 드러납니다.

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

## API 요약

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/api/health` | 헬스체크 |
| POST | `/api/chat` | 동기 방식 채팅 (테스트/단순 클라이언트용) |
| POST | `/api/chat/stream` | SSE 스트리밍 채팅 |
| GET | `/api/policies` | 조건(지역/카테고리) 기반 정책 목록 조회 |
| GET | `/api/policies/{policy_id}` | 정책 상세 조회 |
| POST | `/api/policies/search` | RAG(경량 키워드 검색) 기반 정책 검색 |

## 예시 대화

```
사용자: 대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 취업 지원 있어?
Agent: 조건을 바탕으로 확인해볼 만한 지원사업을 정리했어요.

1. 서울 청년수당 (서울특별시)
   - 지원 대상: 서울 거주 미취업 청년 중 연령, 졸업 여부, 소득 기준 등 세부 요건을 충족하는 사람
   - 지원 내용: 활동지원금, 진로상담, 취업역량 프로그램
   - 신청 기간: 상시 또는 모집 공고별 확인 필요
   - 신청 방법: 청년몽땅정보통에서 모집기간 중 온라인 신청
   - 추천 이유: 현재 상태(취업 준비/재직 등)와 지원 대상이 일치해요. ...
   - 원문 링크: https://youth.seoul.go.kr/
...
※ 최종 자격 및 신청 가능 여부는 공식 공고문 또는 담당 기관을 통해 꼭 확인해주세요.
```

## 가드레일 및 제약사항 (Out of Scope)

- 최종 자격 판정, 실제 신청 대행, 세무/법률 상담은 지원하지 않습니다.
- 소득 기준, 고용보험 가입 여부, 병역 이력, 중복 수급 여부처럼 정밀한
  확인이 필요한 항목은 "추가 확인 필요"로 안내하며 단정하지 않습니다.
- 민감 개인정보(주민등록번호, 계좌번호 등)를 요청하지 않습니다.

## 알려진 MVP 단순화 지점 (향후 개선 과제)

- **스트리밍**: 현재 `/api/chat/stream` 은 그래프 실행이 끝난 최종 응답을
  일정 크기로 나눠 점진 전송합니다. LLM 토큰 단위 실시간 스트리밍(Response
  Node에서 `stream_complete` 직결)은 후속 과제입니다.
- **RAG**: `app/repositories/rag.py` 는 키워드 매칭 기반 경량 검색입니다.
  `data/supabase_schema.sql` + `data/scripts/ingest_rag.py` 골격을 이용해
  Supabase pgvector 임베딩 검색으로 교체할 수 있도록 설계했습니다.
- **온통청년/고용24 연동**: 내부 스키마와 normalizer는 구현되어 있지만,
  현재 키로 실제 응답 필드와 Agent 전체 경로를 다시 검증해야 합니다.
  채용정보 API는 개인키 제한이 확인되어 직접 공고용 `JobPostingItem` 대신
  채용행사/공채속보/공채기업정보용 `RecruitmentInfoItem`을 보조 스키마로 유지합니다.
- **기업마당 연동**: API 응답 정규화 매핑은 `data/scripts/ingest_data.py`
  와 `app/repositories/policy.py` 에 1차 구현되어 있으며, 취업 MVP에서는
  보조 데이터 소스로 유지합니다.
- **세션 보안**: 현재 `session_id`는 추측하기 어려운 UUID 사용을 전제로 하며
  사용자 로그인과 세션 소유권 검증은 아직 없습니다. 브라우저 표시 기록은
  사용자가 삭제할 수 있지만, 외부 공개 운영 전에는 인증과 Supabase 서버 로그의
  보존·삭제 정책이 추가로 필요합니다.
- **멀티턴 저장**: Supabase 장애 시에도 인프로세스 대화는 계속되지만 재시작 후
  복원은 보장되지 않습니다. 같은 세션의 동시 요청 충돌 제어는 후속 과제입니다.
- **SSE 상태**: `status`, `token`, `done`, `error` 이벤트와 청년정책·훈련·채용·
  창업·일반 응답별 상태 문구를 React UI에 연결했습니다. 실제 LLM token
  streaming은 후속 과제입니다.
