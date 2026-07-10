# 🧭 정책나침반 (Policy Compass)

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
> 합니다. 배포/연동 테스트 기준으로 데모용 mock 정책 데이터는 사용하지
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
| 1 | 온통청년 Open API | 청년 취업정책, 청년공간, 청년콘텐츠 조회 | 신청 예정 |
| 2 | 고용24 국민내일배움카드 훈련과정 API | 직무별 교육/훈련과정 조회 | 정상 호출 확인 |
| 3 | 고용24 채용정보 API | 채용행사, 공채속보, 공채기업정보 조회 | 개인키 일부 허용 |
| 4 | 기업마당 지원사업정보 API | 창업/사업자/중소기업 지원사업 보조 조회 | 키 확보 |

## 아키텍처

```
사용자 → [FastAPI] → [LangGraph Agent]
                        Router Node
                          ├─ EXPLAIN / GENERAL / OUT_OF_SCOPE → 즉시 응답
                          └─ RECOMMEND / ELIGIBILITY_CHECK
                               → Profile Extractor Node
                               → Missing Slot Node
                                    ├─ 부족 → 되묻기
                                    └─ 충분 → Policy Search Tool
                                              → Eligibility Scorer Node
                                              → Response Node
                        → Guardrail Node → 최종 응답
```

- **LLM**: Upstage Solar API. `UPSTAGE_API_KEY` 가 없으면 각 노드는 규칙
  기반 휴리스틱(정규식/키워드 매칭)으로 자동 전환되어, 키 없이도 전체
  데모 흐름이 동작합니다.
- **데이터**: 취업 MVP 기준 현재 실데이터로 확인된 핵심 소스는 고용24
  국민내일배움카드 훈련과정 API입니다. 온통청년 API는 키 미설정 시 빈
  결과를 반환하고, 기업마당 API도 mock 데이터로 대체하지 않습니다.
  고용24 채용정보 API는 개인키 권한 제한을 감지하면 채용 탐색 가이드로
  안내합니다.
- **일반 설명 질문**: “국비지원 훈련을 받으면 뭐가 좋아?”처럼 특정 과정
  검색이 아니라 제도 설명을 묻는 질문은 과정 검색으로 보내지 않고 LLM
  기반 설명 응답으로 처리합니다.
- **세션**: LangGraph `MemorySaver` checkpointer가 `session_id` 를
  thread_id로 사용해 대화 내 프로필을 누적합니다(민감 개인정보 미저장,
  프로세스 재시작 시 초기화되는 인메모리 저장).

## 폴더 구조

```
app/
├── api/routes/        # health, chat(SSE), policies REST 엔드포인트
├── core/               # 설정, 프롬프트, LLM 클라이언트
├── graph/              # LangGraph state / nodes / edges / scoring / graph 조립
├── repositories/       # 정책 데이터 접근(policy.py) 및 RAG-lite 검색(rag.py)
├── tools/              # Pydantic Tool 입력 스키마 + Tool executor
├── schemas/            # API 요청/응답 Pydantic 모델
├── static/             # 최소 채팅 UI (정적 HTML/JS)
└── main.py             # FastAPI 앱 엔트리포인트
data/
├── supabase_schema.sql # 향후 Supabase+pgvector RAG 확장용 스키마
└── scripts/            # 기업마당 데이터 적재 / RAG 임베딩 적재 스크립트
tests/                  # pytest 기반 유닛/API 테스트
```

## 실행 방법

### 1. 의존성 설치

```bash
uv sync
cp .env.example .env
```

실제 LLM을 쓰려면 `UPSTAGE_API_KEY` 를 채워주세요. 배포/연동 테스트에서는
mock 정책 데이터 fallback을 사용하지 않으므로, 외부 API 키가 없거나 권한이
제한된 데이터 소스는 빈 결과 또는 안내 fallback으로 드러납니다.

### 2. 서버 실행

```bash
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

- 채팅 데모 UI: http://localhost:8000/
- API 문서(Swagger): http://localhost:8000/docs

### 3. 테스트 & 린트

```bash
uv run python -m pytest -q
uv run ruff check app/ tests/
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
- **온통청년/고용24 연동**: 실제 응답 샘플을 기준으로 내부
  `YouthPolicyItem`/`TrainingCourseItem` 스키마 매핑을 추가해야 합니다.
  채용정보 API는 개인키 제한이 확인되어 직접 공고용 `JobPostingItem` 대신
  채용행사/공채속보/공채기업정보용 `RecruitmentInfoItem`을 보조 스키마로 유지합니다.
- **기업마당 연동**: API 응답 정규화 매핑은 `data/scripts/ingest_data.py`
  와 `app/repositories/policy.py` 에 1차 구현되어 있으며, 취업 MVP에서는
  보조 데이터 소스로 유지합니다.
- **세션 저장소**: 인메모리 `MemorySaver` 를 사용해 서버 재시작 시
  초기화됩니다. 다중 인스턴스 배포 시 Redis/DB 기반 checkpointer로 교체가
  필요합니다.
