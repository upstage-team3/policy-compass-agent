# 개발 로드맵

> 이 문서는 중장기 설계와 과거 계획을 보존한다. 현재 구현 상태와 바로 이어서 할 작업은 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)와 [NEXT_ACTIONS.md](NEXT_ACTIONS.md)를 우선한다.

현재 스냅샷(2026-07-13): Day4 구현과 최신 main CI/CD·GCE 자동 배포까지 완료했다. Day5 사전 안정화에서 유형별 SSE, React 새로고침 대화 복원, 로컬 기록 삭제를 보강했다. 남은 핵심은 외부 URL 수동 회귀, 훈련·채용·창업 Agent 전체 경로 QA, 발표 시나리오 확정이다.

## 목표

2026-07-16 최종 발표까지 정책나침반을 취업 대상 청년을 위한 배포 가능한 AI Agent 데모로 완성한다.

핵심 목표는 기능을 많이 늘리는 것이 아니라, 다음 흐름을 안정적으로 시연하는 것이다.

```text
사용자 조건 분석 -> 부족 조건 확인 -> 지원사업 검색 -> 신청 가능성 점수화 -> 근거 기반 추천 답변 -> 공식 공고 확인 안내
```

2026-07-10 기준 MVP 핵심 대상은 대학생, 졸업예정자, 사회초년생, 미취업 청년이다.
온통청년 Open API와 고용24 국민내일배움카드 훈련과정 API를 중심으로 개발하고, 고용24 채용정보 API는 개인키로 허용되는 채용행사/공채속보/공채기업정보만 보조 기능으로 둔다. 채용정보목록/상세는 개인키로 사용할 수 없으므로 탐색 가이드로 폴백한다. 이미 확보한 기업마당 API는 창업/사업자 질문의 보조 데이터로 유지한다.

## 현재 기준 아키텍처

```text
FastAPI 단일 서버 (:8000)
├─ 정적 채팅 UI (/)
├─ API 문서 (/docs)
├─ Chat API (/api/chat, /api/chat/stream)
├─ Policy API (/api/policies)
└─ LangGraph Agent
   ├─ Router
   ├─ Profile Extractor
   ├─ Missing Slot
   ├─ Policy Search
   ├─ Eligibility Scorer
   ├─ Response
   └─ Guardrail
```

## Day2: 2026-07-09

목표: 실연동 중심 Agent MVP 구현 및 팀원 구조 통합

완료한 작업:

- 스타터 코드를 정책 추천 도메인으로 전환
- 팀원이 공유한 `policy-compass-agent` 구조 검토 및 통합
- FastAPI 단일 서버 구조로 8000 포트 통일
- LangGraph Agent 기본 흐름 구현
- 사용자 조건 추출 Node 구현
- 부족 조건 질문 흐름 구현
- 고용24 훈련과정 실데이터 연동
- 추천 점수화 로직 구현
- 상담형 응답 생성 구현
- 기업마당 API 인증키 기반 호출 구조 추가
- API 실패 시 빈 결과 또는 명시적 안내 fallback 구현
- 정적 채팅 UI 제공
- 정책 목록/상세/검색 API 추가
- SSE 스트리밍 API 추가
- 테스트 23개 통과
- README 및 개발 문서 1차 갱신

완료 기준:

- `http://localhost:8000/` UI 접속 가능
- `http://localhost:8000/health` 응답 확인
- 미취업 청년 시나리오 정상 응답
- 조건 부족 시 추가 질문
- `uv run python -m pytest` 통과

## Day3: 2026-07-10

목표: 취업 MVP 범위 확정, 외부 API 신청, LLM 응답 품질과 가드레일 고도화

작업:

- Upstage Solar 응답 프롬프트에 정책 추천 가이드라인 강화
- LLM이 후보 데이터 밖의 정책명, 금액, 날짜, 링크를 생성하지 않도록 제한
- Response Node 출력 형식 고정
- Guardrail Node에 금지 표현과 출처 없는 단정 표현 검출 보강
- LLM ON/OFF 상태별 데모 결과 비교
- 온통청년 Open API 신청 및 문서 기준 필드 매핑 설계
- 고용24 국민내일배움카드 훈련과정 API 응답 구조 분석 및 훈련과정 스키마 설계
- 고용24 채용정보 API 개인키 권한 범위 확인 및 채용정보목록/상세 fallback 설계
- 기업마당 API는 창업/사업자 보조 데이터로 역할 재정의
- SSE 이벤트 문구와 UI 표시 개선

완료 기준:

- LLM 사용 시에도 정책 후보 데이터 밖의 사실을 만들지 않음
- 답변에 추천 이유, 확인 필요 조건, 신청 방법, 원문 링크 포함
- 최종 자격 판정처럼 들리는 표현 없음
- 핵심 시나리오 2개 이상 반복 성공
- 온통청년/고용24 API 신청 상태가 문서에 반영됨

## Day4: 2026-07-13

목표: 배포 가능한 수준으로 운영화

작업:

- Docker Compose 실행 검증
- GCP VM 환경 세팅
- 8000 포트 방화벽 허용
- 필요 시 Nginx 80 -> 8000 프록시 구성
- GitHub Actions CI 확인
- `.env`와 GitHub Secret 분리
- `/health`, `/api/health`, `/api/chat` 외부 접속 확인

완료 기준:

- 외부 URL 접속 가능
- Docker 빌드 성공
- CI 통과
- `.env` 미업로드 확인

## Day5: 2026-07-14

목표: 취업 MVP 기능 보강 및 안정화

작업:

- 대학생, 졸업예정자, 사회초년생, 미취업 청년 시나리오 안정화
- 취업 지원정책과 훈련과정을 중심으로 보여주고, 채용정보는 가능할 때만 보조로 붙이는 답변 형식 정리
- 마감 공고 처리 개선
- 지역 미입력 시 되묻기 개선
- 온통청년/고용24 응답 필드가 비어 있을 때 예외 처리
- 기업마당 응답은 창업/사업자 질문에서만 보조적으로 사용
- 가드레일 테스트 추가
- 정책 검색 결과가 없을 때 대체 질문 제안
- React 새로고침 뒤 채팅 목록·메시지·정책 카드와 같은 UUID 세션 복원
- 브라우저 표시 기록의 민감정보 마스킹·보존 한도·개별/전체 삭제

완료 기준:

- 취업 MVP 핵심 시나리오 3개 반복 재현
- 치명적 오류 0건
- 추천 결과에 출처 링크 포함
- LLM 환각성 응답 발견 시 프롬프트/가드레일로 수정

## Day6: 2026-07-15

목표: 통합, 문서화, 발표 준비

작업:

- README 최종 보강
- 설치/실행/환경변수/문제 해결 문서화
- 데모 시나리오 2개 확정
- 발표자료 초안 작성
- 백업 데모 영상 녹화
- GitHub Repository 정리

완료 기준:

- README만 보고 실행 가능
- 데모 2회 반복 성공
- 발표자료 초안 완성
- 백업 영상 준비

## Day7: 2026-07-16

목표: 최종 발표 및 산출물 제출

작업:

- 발표자료 최종 정리
- 라이브 데모 점검
- GitHub Repository 최종 정리
- 데모 영상 제출
- 최종 회고 작성

완료 기준:

- 발표자료 제출
- 데모 영상 제출
- GitHub 프로젝트 제출
- 발표 및 Q&A 완료

## DB 기반 고도화 계획

현재 프로젝트는 기업마당 Open API와 고용24 훈련과정 API를 통해 데이터를 가져오고, LangGraph Agent가 조건 추출 -> 누락 조건 확인 -> 정책/훈련 검색 -> 자격 점수화 -> 답변 생성을 수행하는 MVP 구조다. 배포/연동 테스트 기준으로 데모용 대체 정책 데이터 fallback은 제거했으며, 다음 구현 단계에서는 온통청년 API와 고용24 훈련과정 API를 핵심 데이터 소스로 강화하고 고용24 채용정보 API는 보조/fallback 대상으로 둔다.

평가 기준과 서비스 완성도를 고려하면 다음 단계에서는 외부 API를 실시간으로 직접 조회하는 방식보다, 외부 정책 데이터를 내부 표준 스키마로 정규화해 DB에 저장하고 Agent가 DB를 조회하는 구조가 더 적합하다.

권장 목표 구조:

```text
온통청년 API / 고용24 훈련과정 API / 고용24 채용행사·공채속보·공채기업정보 API(보조) / 기업마당 API / 샘플 API 응답 fixture / 정책 문서
-> Ingestion Service
-> 정규화 및 검증
-> DB 저장
-> PolicyRepository
-> PolicySearchTool
-> LangGraph Agent
-> 사용자 답변
```

### DB 도입 범위

MVP 고도화 단계에서는 PostgreSQL 또는 Supabase를 기준으로 다음 데이터를 저장한다.

- `policies`: 정규화된 정책 공고 데이터
- `policy_sources`: 온통청년, 고용24 훈련과정, 고용24 채용정보, 기업마당 API 원본 응답 및 출처 정보
- `recruitment_infos`: 고용24 개인키로 허용되는 채용행사/공채속보/공채기업정보 정규화 데이터
- `chat_sessions`: 사용자 대화 세션
- `chat_messages`: 세션별 대화 이력
- `policy_documents`: 추후 정책 공고 PDF/첨부 문서 저장 및 파싱 결과 연결
- `policy_chunks` / `policy_embeddings`: 추후 pgvector 기반 RAG 확장용

초기 구현에서는 `policies`, `policy_sources`, `chat_sessions`, `chat_messages`를 우선 적용하고, 문서 파싱과 임베딩 검색은 확장 가능하도록 인터페이스와 스키마만 설계한다.

### 계층 분리 방향

현재 구조는 FastAPI 라우트, LangGraph 노드, Tool, Repository가 분리되어 있지만, `PolicyRepository`가 외부 API 호출, 정규화, 데이터 조회 역할을 함께 가지고 있다.

다음 단계에서는 역할을 더 명확히 나눈다.

- Controller: `app/api/routes`, HTTP 요청/응답만 담당
- Service: `app/services`, 정책 수집/검색/추천 흐름 조율
- Repository: `app/repositories`, DB 읽기/쓰기만 담당
- Tool: `app/tools`, Agent가 호출하는 기능 인터페이스
- Schema: `app/schemas`, API 및 내부 데이터 계약 정의

예상 추가 모듈:

- `app/services/policy_ingestion.py`
- `app/services/policy_search.py`
- `app/repositories/policy_db.py`
- `app/repositories/chat_session.py`
- `data/sample_bizinfo_api_response.json`
- `data/scripts/seed_policies.py`

### Tool Schema 및 누락 조건 질문

Tool Schema는 Agent가 도구를 호출할 때 사용하는 입력 계약이다. 챗봇은 사용자 입력에서 조건을 추출한 뒤, Tool Schema 기준으로 필수 조건이 부족한지 판단하고, 부족하면 바로 검색하지 않고 되묻는다.

정책 추천 Tool의 주요 입력 필드:

- `region`
- `age`
- `employment_status`
- `is_entrepreneur`
- `has_registered_business`
- `business_stage`
- `interest_categories`
- `preferred_support_type`
- `income_level`
- `limit`

최소 추천 조건은 `region`, `age`, `employment_status`, `is_entrepreneur`로 두고, 사업자 등록 여부나 관심 분야는 추천 품질을 높이는 선택 조건으로 처리한다. 단, 창업/소상공인 정책을 추천할 때는 `has_registered_business` 또는 `business_stage`가 부족하면 추가 질문을 우선한다.

### 실제 API와 저장 데이터 호환성

실연동 전환 시 깨지지 않도록 실제 API 응답과 내부 표준 데이터를 분리한다.

- `sample_bizinfo_api_response.json`: 기업마당 API 응답 형태를 보존한 샘플 fixture
- 저장 데이터: 내부 표준 정책/훈련 스키마에 맞춘 정규화 결과

실제 API 응답과 샘플 API 응답은 같은 normalizer를 거쳐 DB에 저장되도록 한다.

### Upstage Document Parse / Information Extract 확장

정책 공고는 API 필드만으로는 지원 대상, 제외 조건, 제출 서류, 신청 절차가 부족할 수 있다. 추후 Upstage Document Parse와 Information Extract를 활용해 공고 PDF/HTML/첨부 문서에서 구조화 정보를 추출하는 흐름을 추가한다.

예상 흐름:

```text
정책 공고 문서 수집
-> Upstage Document Parse
-> Information Extract
-> 신청 대상 / 지원 내용 / 신청 기간 / 제외 조건 / 제출 서류 추출
-> DB 저장
-> Agent 답변 근거로 활용
```

MVP에서는 전체 문서 자동 파싱을 Out of Scope로 두되, 아키텍처와 테이블 설계에는 반영한다.

### Out of Scope

- 모든 정부지원사업 실시간 동기화
- 모든 첨부 문서 자동 파싱
- 최종 자격 판정
- 민감 개인정보 저장
- 신청 대행
- 법률/세무/노무 판단

### 기획 설명 문장

외부 정책 API와 공고 문서를 내부 표준 정책 스키마로 정규화해 DB에 저장하고, Agent는 저장된 정책 카탈로그와 근거 데이터를 기반으로 추천하므로 외부 API 장애에 강하고 추천 결과를 재현할 수 있다.
