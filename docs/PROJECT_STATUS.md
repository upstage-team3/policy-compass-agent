# 정책나침반 개발 현황

작성일: 2026-07-10

## 한 줄 요약

정책나침반은 사용자의 자연어 질문에서 나이, 지역, 졸업 여부, 취업 상태, 관심 직무 등을 추출하고, 청년지원사업과 취업 관련 청년 정보를 안내하는 AI Agent 서비스다. 현재 연결 가능한 핵심 실데이터는 고용24 국민내일배움카드 훈련과정 API이며, 고용24 채용정보 API는 개인키로 채용행사, 공채속보, 공채기업정보만 사용할 수 있어 보조/확장 데이터로 둔다. 온통청년 API는 키 발급 전까지 빈 결과로 처리해 연결 상태를 명확히 드러낸다.

현재 코드는 팀원이 공유한 `policy-compass-agent` 구조를 기반으로 통합했다. FastAPI 단일 서버가 API와 정적 채팅 UI를 함께 제공하며, LangGraph 기반 Agent 흐름, 세션 기반 프로필 누적, 정책 목록/검색 API, SSE 스트리밍, 고용24 훈련과정 실연동, 기업마당 API 직접 정규화 로직을 포함한다. 2026-07-10 기준 MVP 범위는 취업 대상 청년으로 좁히고, 데모용 대체 정책 데이터 fallback은 배포/연동 테스트 기준에서 제거했다.

## 전체 진행률

현재 체감 진행률: 약 55%

| 영역 | 상태 | 진행 내용 |
| --- | --- | --- |
| 기획 | 완료 | 청년지원사업 및 취업 관련 청년 정보 챗봇으로 MVP 범위 재확정 |
| 코드 구조 통합 | 완료 | 팀원 GitHub 구조를 기반으로 `api/routes`, `graph`, `repositories`, `schemas`, `static` 구조 적용 |
| Agent 그래프 | 1차 완료 | Router -> Profile Extractor -> Missing Slot -> Search -> Score -> Response -> Guardrail 흐름 구성 |
| 사용자 조건 추출 | 1차 완료 | LLM 사용 가능, 미설정/실패 시 규칙 기반 fallback |
| 부족 조건 질문 | 1차 완료 | 지역, 취업/창업 상태 등 핵심 조건 부족 시 먼저 되묻기 |
| 정책 데이터 | 1차 완료 | 데모용 대체 정책 파일 제거. 실제 API 미연결/실패 시 빈 결과 또는 안내 fallback으로 처리 |
| 온통청년 API 연동 | 준비 완료 | 현재 키 미설정. 키가 없으면 내부 대체 데이터로 보완하지 않고 빈 결과 반환 |
| 고용24 훈련과정 API 연동 | 1차 완료 | `TrainingCourseSearchInput`/normalizer/Tool 추가. 핵심 직무 키워드 추출, 상세 과정 URL 제공, 결과 없음/실패 시 탐색 가이드 fallback |
| 고용24 채용정보 API 연동 | 1차 완료 | 개인회원 권한 제한 감지 및 채용 탐색 가이드 fallback 추가 |
| 기업마당 API 연동 | 1차 완료 | `BIZINFO_API_KEY` 기반 호출 및 응답 정규화. 취업 MVP에서는 보조 데이터로 유지 |
| 추천 점수화 | 1차 완료 | 지역, 연령, 취업상태, 창업 여부, 신청기간 기준 점수화 |
| LLM 응답 | 1차 완료 | Upstage Solar 연동 구조 있음. 후보 데이터 밖 사실 생성 금지, 일반 설명 질문 LLM 응답, 공식 링크 가드레일 보강 |
| 가드레일 | 1차 완료 | 확정적 표현 완화, 최종 자격 확인 안내, 신청 전 확인 필요 조건 안내 추가 |
| UI | 1차 완료 | FastAPI 정적 HTML 채팅 UI를 `/`에서 제공. SSE 진행 상태와 오류 메시지 표시 |
| API | 1차 완료 | `/api/chat`, `/api/chat/stream`, `/api/policies`, `/api/health` 제공. 기존 `/health`, `/api/v1/chat/sync` 호환 유지 |
| 테스트 | 완료 | `37 passed`, 경고 2건은 외부 라이브러리 deprecation warning |
| Docker/GCP 배포 | 진행 중 | Dockerfile/Compose는 8000 포트 기준. Compose 설정은 유효하나 Docker Desktop 데몬 미실행으로 빌드 검증은 이월 |
| 발표/README | 진행 중 | README는 통합 구조 기준으로 갱신, 발표자료는 미작성 |

## 현재 동작 흐름

1. 사용자가 `http://localhost:8000/`의 채팅 UI 또는 API로 질문을 입력한다.
2. Router Node가 추천, 설명, 자격 확인, 일반 대화, 범위 밖 요청을 분류한다.
3. Profile Extractor Node가 사용자 조건을 추출한다.
4. Missing Slot Node가 추천에 필요한 조건이 부족한지 확인한다.
5. 조건이 부족하면 Clarification Node가 추가 질문을 반환한다.
6. 조건이 충분하면 청년지원사업, 고용24 훈련과정, 채용 보조 정보 중 의도에 맞는 Tool을 선택한다. 고용24 훈련과정은 실제 API 결과를 사용하며, 온통청년/기업마당은 대체 데이터로 보완하지 않는다.
7. Eligibility Scorer Node가 정책 후보를 점수화한다.
8. Response Node가 정책 후보, 추천 이유, 확인 필요 조건, 신청 방법, 원문 링크를 포함한 답변을 만든다.
9. Guardrail Node가 확정적 표현을 완화하고 공식 공고 확인 안내를 덧붙인다.

## 구현된 주요 파일

| 파일 | 역할 |
| --- | --- |
| `app/main.py` | FastAPI 앱 생성, 라우터 등록, 정적 UI 제공, 기존 API 호환 라우트 |
| `app/api/routes/chat.py` | `/api/chat`, `/api/chat/stream` 채팅 API |
| `app/api/routes/health.py` | `/api/health` 헬스체크 |
| `app/api/routes/policies.py` | 정책 목록, 상세, 키워드 검색 API |
| `app/graph/graph.py` | LangGraph 노드 연결 및 MemorySaver 세션 관리 |
| `app/graph/nodes.py` | Router, Profile, Missing Slot, Search, Response, Guardrail 노드 |
| `app/graph/scoring.py` | 정책 적합도 점수화 |
| `app/repositories/policy.py` | 기업마당 API 호출, 응답 정규화, 실패/키 없음 시 빈 결과 |
| `app/repositories/youthcenter.py` | 온통청년 XML normalizer, 키 미설정 시 빈 결과 |
| `app/repositories/work24_training.py` | 고용24 훈련과정 API 호출, XML normalizer, 핵심 직무 키워드 검색, 상세 URL 제공, 훈련과정 탐색 fallback |
| `app/repositories/work24_recruitment.py` | 고용24 채용정보 권한 제한 감지, 채용 탐색 가이드 fallback |
| `app/repositories/rag.py` | MVP용 키워드 기반 RAG-lite 검색 |
| `app/core/llm.py` | Upstage Solar API 클라이언트 및 JSON 추출 |
| `app/core/prompts.py` | Router/Profile/Response용 프롬프트 |
| `app/schemas/` | 채팅/정책 Pydantic 스키마 |
| `app/static/index.html` | FastAPI에서 제공하는 정적 채팅 데모 UI |
| `tests/` | Agent/API 테스트 |

## 확인된 기술 결정

- 서버/UI: FastAPI 단일 서버, 정적 HTML UI
- Agent 흐름: LangGraph + MemorySaver
- LLM: Upstage Solar API, 실패 시 규칙 기반 fallback
- 정책 데이터: 고용24 국민내일배움카드 훈련과정 API를 현재 연결 가능한 핵심 실데이터로 우선 구현, 온통청년 Open API는 키 발급 전까지 빈 결과로 처리, 고용24 채용정보 API는 개인키 권한 허용 범위에서만 보조 사용, 기업마당 지원사업정보 API는 창업/사업자 보조 데이터로 유지하되 데모용 대체 데이터 fallback은 사용하지 않음
- 검색: MVP는 키워드 기반 RAG-lite, 향후 Supabase pgvector 확장 가능
- 실행 포트: 로컬/배포 기본 `8000`
- 패키지 관리: `uv`
- 배포 예정: Docker Compose + GCP Compute Engine

## LLM 사용 원칙

- LLM은 정책 데이터를 생성하지 않고, 주어진 후보 데이터와 사용자 프로필을 설명하는 역할로 제한한다.
- 정책명, 신청기간, 지원내용, 신청방법, 원문 링크는 API/RAG 결과에서만 가져온다.
- 후보 데이터에 없는 금액, 날짜, 자격 조건, 링크를 만들지 않는다.
- "신청 가능합니다" 같은 최종 판정 대신 "신청 가능성이 있습니다", "확인해볼 만합니다", "추가 확인이 필요합니다"를 사용한다.
- 소득, 재산, 고용보험, 거주기간, 중복 수혜 등 정밀 조건은 별도 확인 필요 항목으로 분리한다.
- 주민등록번호, 계좌번호, 정확한 주소, 전화번호 등 민감정보를 요청하지 않는다.
- 답변 마지막에는 공식 공고문 또는 담당 기관 확인 안내를 포함한다.

## 현재 주의사항

- `.env`에는 실제 API 키가 들어 있으므로 GitHub에 절대 올리지 않는다.
- `.env.example`에는 키 이름과 기본값만 둔다.
- 현재 실제 키가 있으면 LLM 응답이 활성화될 수 있으므로, 발표 전 프롬프트/가드레일 품질을 반드시 확인한다.
- 온통청년 API와 고용24 국민내일배움카드 API는 실제 응답 샘플을 기준으로 정규화 품질을 확인해야 한다.
- 고용24 채용정보 API는 개인키로 채용행사/공채속보/공채기업정보만 사용할 수 있으며, 채용정보목록/상세가 필요하면 채용 탐색 가이드로 폴백해야 한다.
- 기업마당 API 응답 필드는 실제 공고마다 비어 있을 수 있어 보조 데이터로 사용할 때도 정규화 품질 보강이 필요하다.
- 기존 작은 구조의 백업은 `_merge_backup_before_team_structure`에 남아 있으나 GitHub 업로드 전 포함 여부를 확인해야 한다.

## 다음 고도화 방향: DB 기반 Agent 서비스

현재 구현은 정책 추천 챗봇 MVP로서 FastAPI, LangGraph Agent, 정책 검색 Tool, 기업마당 API 연동 구조, RAG-lite 검색, 누락 조건 질문 흐름을 포함한다. 다음 구현에서는 이 구조를 유지하되 데이터 소스의 중심을 온통청년과 고용24 훈련과정 API로 옮긴다.

다음 단계의 핵심 목표는 현재의 API 직접 조회 구조를 DB 중심 구조로 전환해 추천 결과의 재현성, 장애 대응력, 평가 설득력을 높이는 것이다.

우선순위는 다음과 같다.

1. 온통청년 정책 데이터와 고용24 훈련과정 데이터를 PostgreSQL 또는 Supabase에 저장한다.
2. 온통청년, 고용24 훈련과정, 고용24 채용정보 보조 데이터, 기업마당 API 응답을 같은 normalizer로 정규화한 뒤 DB에 upsert한다.
3. `PolicyRepository`는 DB 접근만 담당하도록 줄이고, 외부 API 수집은 `PolicyIngestionService`와 `RecruitmentInfoIngestionService`로 분리한다.
4. `PolicySearchTool`과 채용공고 검색 Tool은 명확한 Pydantic Tool Schema를 기준으로 호출되도록 유지한다.
5. 누락 조건이 있을 때는 Tool을 바로 호출하지 않고 챗봇이 먼저 되묻도록 Missing Slot 흐름을 강화한다.
6. Upstage Document Parse / Information Extract는 정책 공고 문서 파싱 확장 설계로 반영하되, MVP에서는 전체 자동 파싱을 Out of Scope로 둔다.

설명 문장:

> 온통청년 정책 API, 고용24 훈련과정 API, 고용24 채용행사/공채속보/공채기업정보 보조 데이터, 기업마당 보조 데이터를 내부 표준 스키마로 정규화해 DB에 저장하고, Agent는 저장된 정책/훈련 카탈로그와 근거 데이터를 기반으로 추천하므로 외부 API 장애에 강하고 추천 결과를 재현할 수 있다.
