# 다음 작업 체크리스트

## GitHub 업데이트 전

- [x] 팀원 폴더 구조 기반으로 현재 프로젝트 통합
- [x] 8000 포트 단일 서버 기준으로 실행 방식 정리
- [x] 배포/연동 테스트 기준으로 데모용 정책 JSON 제거
- [x] 기업마당 API 실패/키 없음 시 대체 데이터 대신 빈 결과 반환
- [x] `/health`, `/api/v1/chat/sync` 기존 호환 라우트 유지
- [x] `uv lock`, `uv sync` 갱신
- [x] `uv run python -m pytest` 통과
- [x] README 1차 갱신
- [x] 개발/협업 문서 갱신
- [x] `.env`가 GitHub에 올라가지 않는지 확인
- [x] `_merge_backup_before_team_structure` 백업 폴더를 GitHub에서 제외할지 결정
- [x] `policy_compass.egg-info`, `.pytest_cache`, `.streamlit` 등 생성물 제외 확인
- [ ] `git status` 기준으로 커밋할 파일 범위 확인

## 바로 해야 할 일

1. 고용24 채용행사/공채속보/공채기업정보 세부 endpoint를 확인하고, 개인키로 가능한 항목부터 추가한다.
2. 온통청년 청년정책 API 키가 발급되면 `YouthCenterRepository`의 실제 호출 결과를 검증한다.
3. Missing Slot Node의 질문 문구를 청년지원사업/훈련과정/채용 보조 정보별로 더 자연스럽게 다듬는다.
4. 새 Tool 결과가 SSE 스트리밍 UI에서 자연스럽게 표시되는지 수동 QA한다.
5. Docker Compose 실행 확인 후 GitHub에 push한다.
6. GitHub Actions CI/CD 워크플로우의 `uv sync` 옵션, AI 리뷰 스크립트 경로, CD healthcheck 경로를 실제 프로젝트 구조에 맞춘다.

## 개발 우선순위

1. 청년지원사업 및 취업 관련 청년 정보 챗봇 흐름 안정화
2. 고용24 국민내일배움카드 훈련과정 API 연동 및 필드 매핑
3. 일반 설명 질문과 검색/추천 질문 라우팅 품질 개선
4. 고용24 채용행사/공채속보/공채기업정보 API 연동 및 채용정보목록/상세 제한 fallback 설계
5. 온통청년 API 키 미설정 상태와 향후 정책 필드 매핑 준비
6. LLM 응답 가드레일 강화
7. 기업마당 API를 창업/사업자 보조 데이터 소스로 정리
8. SSE 스트리밍 UI 개선
9. Docker/GCP 배포 정리
10. 발표자료 보강은 오늘 핵심 개발 범위에서 제외

## 테스트 질문

```text
국비지원 훈련을 받으면 뭐가 좋아?
```

```text
서울에서 데이터 분석 쪽으로 취업 준비 중이야. 국비지원 훈련과정 찾아줘.
```

```text
서울 사는 만 28세 미취업자인데 구직지원금 받을 수 있어?
```

```text
대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?
```

```text
서울에서 데이터 분석 신입으로 취업하고 싶은데 지금 지원할 만한 채용공고 있어?
```

```text
졸업예정자인데 인턴이나 일경험 지원사업도 같이 찾아줘.
```

```text
취업 준비 중인데 받을 수 있는 지원금 있어?
```

마지막 질문은 지역 등 조건이 부족하므로 바로 추천하지 않고 추가 질문이 나와야 한다.

## 완료 기준

- [x] 추천 응답에 정책명, 추천 이유, 확인 필요 조건, 신청 방법, 원문 링크가 나온다.
- [x] 조건이 부족하면 바로 정책을 나열하지 않고 추가 질문을 한다.
- [x] 기업마당 API가 실패해도 대체 데이터로 보완하지 않고 빈 결과로 처리한다.
- [x] 답변에서 최종 자격 판정을 하지 않는다.
- [x] 테스트 37개가 통과한다.
- [x] 온통청년 API 키 신청이 완료된다.
- [x] 고용24 국민내일배움카드 훈련과정 API 키 신청이 완료된다.
- [x] 고용24 채용정보 API 키 신청이 완료된다.
- [x] 고용24 채용정보 API의 개인키 권한 범위를 확인했다. 채용행사/공채속보/공채기업정보는 가능하고, 채용정보목록/상세는 불가하다.
- [x] 3개 API의 Tool Schema 설계가 코드에 반영된다.
- [x] 취업 MVP 데모 질문 중 고용24 훈련과정 상세 URL 제공과 일반 설명 질문 라우팅이 동작한다.
- [x] LLM 사용 시에도 출처 없는 정책 정보가 생성되지 않도록 프롬프트와 템플릿 응답을 보강했다.
- [ ] Docker Compose가 8000 포트에서 정상 실행된다. 현재는 Docker Desktop 데몬 미실행으로 빌드 검증 이월.
- [x] `.env`가 GitHub에 올라가지 않는다.

## Day3 검증 메모

- `/api/chat/stream`은 `status`, `token`, `done`, `error` SSE 이벤트 흐름을 제공한다.
- 정적 UI는 빈 말풍선 대신 진행 상태와 오류 안내를 표시한다.
- 기업마당 정규화는 nested 응답과 빈 필드를 기본 안내 문구로 처리한다.
- 로컬 서버 기준 `/health`, `/`, `/docs`, `/api/chat/stream` 응답을 확인했다.
- 고용24 훈련과정 normalizer, 채용정보 권한 제한 fallback, 온통청년 키 미설정 fallback을 추가했다.
- 테스트 기준은 `uv run python -m pytest` 37개 통과다.
- 배포/연동 테스트 기준으로 데모용 대체 정책 파일 fallback을 제거했다.
- “국비지원 훈련을 받으면 뭐가 좋아?” 같은 설명형 질문은 훈련과정 검색이 아니라 LLM 설명 응답으로 처리한다.
- 고용24 훈련과정 검색은 사용자 문장에서 `데이터 분석` 같은 핵심 직무 키워드를 우선 추출하고, 결과에 상세 과정 URL을 포함한다.

## DB 기반 고도화 작업 체크리스트

### 1. DB 및 스키마

- [ ] PostgreSQL 또는 Supabase 중 실제 적용 대상을 결정한다.
- [ ] `policies` 테이블을 현재 `PolicyItem` 스키마 기준으로 정리한다.
- [ ] `policy_sources` 테이블에 온통청년, 고용24 훈련과정, 고용24 채용정보, 기업마당 API 원본 응답과 출처 URL을 저장한다.
- [ ] `recruitment_infos` 테이블 또는 스키마는 고용24 개인키로 허용되는 채용행사/공채속보/공채기업정보를 저장하도록 설계한다.
- [ ] `chat_sessions`, `chat_messages` 테이블로 대화 이력을 저장할 수 있게 한다.
- [ ] 추후 RAG 확장을 위해 `policy_documents`, `policy_chunks`, `policy_embeddings` 설계를 문서화한다.
- [ ] `data/supabase_schema.sql`을 실제 MVP 스키마 기준으로 갱신한다.

### 2. 데이터 수집 및 Seed

- [ ] `data/sample_youthcenter_api_response.xml`을 추가해 온통청년 API 응답 형태의 샘플 fixture를 만든다.
- [ ] `data/sample_recruitment_infos.json`을 추가해 채용행사/공채속보/공채기업정보 응답과 채용정보목록/상세 제한 응답 샘플을 함께 만든다.
- [ ] `data/sample_bizinfo_api_response.json`을 추가해 실제 기업마당 API 응답 형태의 샘플 fixture를 만든다.
- [ ] 실제 API 응답과 샘플 API 응답이 같은 normalizer를 거치도록 정리한다.
- [ ] `data/scripts/seed_policies.py`를 추가해 정규화된 샘플 정책 데이터를 DB에 적재한다.
- [ ] 온통청년 API 호출 결과를 DB에 upsert하는 `PolicyIngestionService`를 추가한다.
- [ ] 고용24 채용행사/공채속보/공채기업정보 호출 결과를 DB에 upsert하고 권한 제한 응답은 fallback reason으로 기록하는 `RecruitmentInfoIngestionService`를 추가한다.
- [ ] 기업마당 API 호출 결과는 창업/사업자 보조 데이터로 DB에 upsert한다.
- [ ] API 호출 실패 시 데모용 대체 데이터가 아니라, 마지막으로 저장된 DB 데이터를 우선 사용하도록 전환한다.

### 3. 계층 분리

- [ ] `app/services/policy_ingestion.py`를 추가한다.
- [ ] `app/services/policy_search.py`를 추가한다.
- [ ] `app/repositories/policy.py`에서 외부 API 호출 책임을 분리한다.
- [ ] `app/repositories/policy_db.py` 또는 기존 repository를 DB 조회/저장 전용으로 정리한다.
- [ ] FastAPI route는 Service 호출만 담당하도록 단순화한다.
- [ ] Tool은 Agent가 필요한 입력/출력 계약만 유지하도록 정리한다.

### 4. Tool Schema 및 Missing Slot

- [ ] `PolicySearchInput`에 `graduation_status`, `desired_job`, `preferred_region`, `preferred_support_type`, `income_level` 등 취업 추천 품질을 높이는 선택 필드를 검토한다.
- [ ] 최소 추천 조건을 `region`, `age`, `employment_status`, `graduation_status` 기준으로 정리한다.
- [ ] 채용공고 검색에서는 `desired_job` 또는 `preferred_region`이 부족할 때 추가 질문을 하도록 보강한다.
- [ ] 창업/소상공인 정책에서는 `has_registered_business` 또는 `business_stage`가 부족할 때 추가 질문을 하도록 보조 흐름으로 유지한다.
- [ ] 누락 조건 질문 문구를 사용자 친화적으로 정리한다.
- [ ] 조건이 부족한 상태에서는 정책 검색 Tool을 호출하지 않는 테스트를 추가한다.

### 5. 문서 파싱 확장 설계

- [ ] Upstage Document Parse를 정책 공고 PDF/HTML/첨부 문서 처리 후보로 문서화한다.
- [ ] Information Extract로 신청 대상, 지원 내용, 신청 기간, 제외 조건, 제출 서류를 추출하는 흐름을 설계한다.
- [ ] MVP에서는 전체 문서 자동 파싱을 Out of Scope로 명시한다.
- [ ] 추후 구현을 위해 `policy_documents`와 추출 필드 저장 구조를 남긴다.

### 6. README 및 발표 자료 반영

- [ ] DB를 쓰는 이유를 README에 추가한다.
- [ ] 외부 API를 직접 조회하지 않고 DB에 저장한 뒤 조회하는 이유를 설명한다.
- [ ] 취업 대상 청년을 MVP 핵심으로 잡은 이유를 발표자료에 반영한다.
- [ ] 온통청년 + 고용24 훈련과정 + 고용24 채용정보 보조 + 기업마당 보조 구조를 데이터 아키텍처로 설명한다.
- [ ] Controller / Service / Repository / Tool 계층 구조를 다이어그램으로 정리한다.
- [ ] Tool Schema와 누락 조건 되묻기 전략을 설명한다.
- [ ] MVP 범위와 Out of Scope를 명확히 분리한다.

## 개발 중 보완 이슈 - 2026-07-10

### 1. 일반 대화 생성 노드에 LLM 사용 적용

현재 일반 설명 질문 일부는 LLM 응답 경로를 사용하지만, 일반 대화 전용 생성 노드는 더 명확히 분리할 필요가 있다.

해야 할 일:

- 일반 대화/설명형 질문 전용 노드 추가 또는 기존 노드 정리
- 정책/훈련/채용 검색이 필요한 질문과 설명형 질문 분리
- 일반 질문은 LLM으로 자연스럽게 답하되, 정책명/금액/날짜/자격 조건을 새로 만들지 않도록 제한

### 2. SSE 상태 문구 개선

현재 SSE 진행 상태 문구가 모든 대화에서 거의 동일하게 전송된다. 사용자 질문 유형에 따라 다른 상태 메시지를 보내도록 개선한다.

예시:

- 훈련과정 검색: `고용24 훈련과정을 확인하고 있어요.`
- 정책 추천: `조건에 맞는 청년지원사업을 살펴보고 있어요.`
- 채용 정보: `채용 정보 제공 가능 범위를 확인하고 있어요.`
- 일반 설명: `질문에 맞는 설명을 정리하고 있어요.`

### 3. 라우팅 의도 분류 디테일 개선

현재 라우팅은 기본 동작은 가능하지만, 질문 의도 간 경계를 더 세밀하게 나눠야 한다.

개선 대상:

- 국비지원/내일배움카드 설명 질문 vs 실제 훈련과정 검색 질문
- 청년정책 추천 질문 vs 제도 설명 질문
- 채용공고 검색 질문 vs 취업 준비 일반 상담
- 지역/직무/기간 등 조건이 부족한 검색 질문
- 단순 잡담 또는 서비스 범위 밖 질문

목표:

- 불필요한 검색 API 호출 줄이기
- 일반 질문은 LLM 설명으로 답하기
- 실제 추천/검색 질문만 Tool 실행으로 연결하기
