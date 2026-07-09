# 🧭 정책나침반 (Policy Compass)

사용자의 나이, 취업 상태, 졸업 여부, 거주지역, 창업 여부 등의 조건을 분석해
청년/구직자/예비창업자/소상공인에게 맞는 정부 지원사업을 추천하고 안내하는
AI 기반 Agent 챗봇입니다.

기존 정부 지원사업 정보는 여러 사이트에 흩어져 있고, 신청 자격이 나이·소득·
지역·취업 상태·창업 여부 등으로 복잡하게 구성되어 있어 본인에게 맞는 사업을
찾기 어렵습니다. 정책나침반은 사용자의 자연어 질문에서 조건을 추출하고,
부족한 정보는 되물어 보완한 뒤, 조건과 공고 데이터를 비교해 신청 가능성이
높은 지원사업을 근거와 함께 추천합니다.

> ⚠️ 본 서비스는 **의사결정 보조 Agent**입니다. 최종 자격 판단이나 실제
> 신청은 대행하지 않으며, 항상 공식 공고문/담당 기관을 통해 재확인해야
> 합니다. 데모용 정책 데이터(`data/mock_policies.json`)는 실제 공고를
> 단순화한 예시이며 실시간 정확성을 보장하지 않습니다.

## 핵심 기능

1. **사용자 조건 분석 및 프로필 구성** — 나이, 취업/창업 상태, 거주지역,
   졸업 여부, 관심 분야 등을 자연어에서 추출해 세션 단위로 누적 관리
2. **부족 조건 되묻기 (HITL)** — 추천에 꼭 필요한 조건(거주지역, 취업/창업
   상태)이 부족하면 먼저 확인 질문을 함
3. **정책 공고 검색** — 기업마당 Open API 연동(선택) 또는
   `data/mock_policies.json` 기반 검색, 실패 시 자동 폴백
4. **자격 적합도 스코어링** — 지역/연령/취업상태/창업여부/관심분야/신청기간을
   규칙 기반으로 비교해 점수·추천 이유·확인 필요 조건을 계산
5. **근거 기반 추천 응답 + 가드레일** — 사업명, 추천 이유, 지원 대상,
   신청 기간, 신청 방법, 확인 필요 조건, 원문 링크를 포함해 답변하며,
   "반드시 가능합니다" 같은 확정적 표현은 자동으로 완화됨

### MVP 우선순위 (기획서 기준)

| 순위 | 시나리오 | 상태 |
| --- | --- | --- |
| 1 | 미취업 청년 구직/취업 지원사업 추천 (핵심 시나리오) | ✅ 완성 구현 |
| 2 | 예비창업자 창업 지원사업 추천 | ✅ 동일 파이프라인으로 지원 |
| 3 | 자영업자/소상공인 경영 지원사업 추천 | ✅ 동일 파이프라인으로 지원 |

세 시나리오 모두 "조건 분석 → 부족 조건 확인 → 공고 검색 → 적합도 판단 →
근거 기반 답변"이라는 동일한 핵심 흐름을 공유합니다.

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
- **데이터**: 1차로 기업마당 Open API, 실패/미설정 시
  `data/mock_policies.json` 로 폴백합니다.
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
├── main.py             # FastAPI 앱 엔트리포인트
└── ui.py               # (선택) Gradio 데모 UI
data/
├── mock_policies.json  # 데모용 정책 공고 데이터
├── supabase_schema.sql # 향후 Supabase+pgvector RAG 확장용 스키마
└── scripts/            # 기업마당 데이터 적재 / RAG 임베딩 적재 스크립트
tests/                  # pytest 기반 유닛/API 테스트
```

## 실행 방법

### 1. 의존성 설치

```bash
uv sync --extra dev
cp .env.example .env
```

`.env` 는 비워둔 상태로도 전체 데모가 동작합니다 (LLM/외부 API 미설정 시
자동 폴백). 실제 LLM을 쓰려면 `UPSTAGE_API_KEY` 를 채워주세요.

### 2. 서버 실행

```bash
uv run uvicorn app.main:app --reload
```

- 채팅 데모 UI: http://localhost:8000/
- API 문서(Swagger): http://localhost:8000/docs

### 3. 테스트 & 린트

```bash
uv run pytest -q
uv run ruff check .
```

### 4. (선택) Gradio 데모

```bash
uv sync --extra ui
uv run python -m app.ui
```

### 5. Docker

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
사용자: 대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?
Agent: 조건을 바탕으로 확인해볼 만한 지원사업을 정리했어요.

1. 청년 구직활동지원금(예시) (고용노동부)
   - 지원 대상: 만 18~34세 미취업 청년 중 졸업(예정) 후 2년 이내이며 ...
   - 지원 내용: 월 최대 50만원, 최대 6개월간 구직활동 지원금 지급 ...
   - 신청 기간: 2026-01-01 ~ 2026-12-31 [모집중]
   - 신청 방법: 고용24(work24.go.kr) 온라인 신청
   - 추천 이유: 현재 상태(취업 준비/재직 등)와 지원 대상이 일치해요. ...
   - 원문 링크: https://www.work24.go.kr/
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
- **기업마당 연동**: API 응답 정규화 매핑은 `data/scripts/ingest_data.py`
  에 최소 필드 매핑만 구현되어 있으며, 실제 스펙에 맞춰 보강이 필요합니다.
- **세션 저장소**: 인메모리 `MemorySaver` 를 사용해 서버 재시작 시
  초기화됩니다. 다중 인스턴스 배포 시 Redis/DB 기반 checkpointer로 교체가
  필요합니다.
