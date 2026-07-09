# 다음 작업 체크리스트

## GitHub 업데이트 전

- [x] 팀원 폴더 구조 기반으로 현재 프로젝트 통합
- [x] 8000 포트 단일 서버 기준으로 실행 방식 정리
- [x] `data/mock_policies.json`을 현재 스키마에 맞게 작성
- [x] 기업마당 API fallback 구조 유지
- [x] `/health`, `/api/v1/chat/sync` 기존 호환 라우트 유지
- [x] `uv lock`, `uv sync` 갱신
- [x] `uv run python -m pytest` 통과
- [x] README 1차 갱신
- [x] 개발/협업 문서 갱신
- [ ] `.env`가 GitHub에 올라가지 않는지 확인
- [ ] `_merge_backup_before_team_structure` 백업 폴더를 GitHub에서 제외할지 결정
- [ ] `policy_compass.egg-info`, `.pytest_cache`, `.streamlit` 등 생성물 제외 확인
- [ ] `git status` 기준으로 커밋할 파일 범위 확인

## 바로 해야 할 일

1. LLM 응답 가이드라인을 `app/core/prompts.py`에 더 엄격하게 반영
2. Upstage 키가 있는 상태에서 데모 질문별 답변을 확인
3. LLM이 후보 데이터 밖의 날짜, 금액, 자격 조건, 링크를 만들지 않는지 확인
4. 기업마당 API 실제 응답 샘플을 확인하고 필드 매핑 보강
5. Docker Compose 실행 확인
6. GitHub에 push
7. 배포 VM에 코드 반영

## 개발 우선순위

1. LLM 응답 가드레일 강화
2. 미취업 청년 시나리오 안정화
3. 예비창업자 시나리오 안정화
4. 소상공인 시나리오 안정화
5. 기업마당 API 실제 응답 매핑 보강
6. SSE 스트리밍 UI 개선
7. Docker/GCP 배포 정리
8. 발표자료 보강

## 테스트 질문

```text
서울 사는 만 28세 미취업자인데 구직지원금 받을 수 있어?
```

```text
대학 졸업한지 6개월 됐고 서울에서 취업 준비 중인데 받을 수 있는 지원금 있어?
```

```text
아직 사업자는 없고 서울에서 AI 서비스 창업 준비 중이야. 창업지원사업 있어?
```

```text
경기에서 2년째 음식점 운영 중인데 소상공인 지원사업 찾아줘.
```

```text
취업 준비 중인데 받을 수 있는 지원금 있어?
```

마지막 질문은 지역 등 조건이 부족하므로 바로 추천하지 않고 추가 질문이 나와야 한다.

## 완료 기준

- [x] 추천 응답에 정책명, 추천 이유, 확인 필요 조건, 신청 방법, 원문 링크가 나온다.
- [x] 조건이 부족하면 바로 정책을 나열하지 않고 추가 질문을 한다.
- [x] 기업마당 API가 실패해도 Mock 데이터로 답변이 나온다.
- [x] 답변에서 최종 자격 판정을 하지 않는다.
- [x] 테스트 23개가 통과한다.
- [ ] LLM 사용 시에도 출처 없는 정책 정보가 생성되지 않는다.
- [ ] Docker Compose가 8000 포트에서 정상 실행된다.
- [ ] `.env`가 GitHub에 올라가지 않는다.

## DB 기반 고도화 작업 체크리스트

### 1. DB 및 스키마

- [ ] PostgreSQL 또는 Supabase 중 실제 적용 대상을 결정한다.
- [ ] `policies` 테이블을 현재 `PolicyItem` 스키마 기준으로 정리한다.
- [ ] `policy_sources` 테이블에 기업마당 API 원본 응답과 출처 URL을 저장한다.
- [ ] `chat_sessions`, `chat_messages` 테이블로 대화 이력을 저장할 수 있게 한다.
- [ ] 추후 RAG 확장을 위해 `policy_documents`, `policy_chunks`, `policy_embeddings` 설계를 문서화한다.
- [ ] `data/supabase_schema.sql`을 실제 MVP 스키마 기준으로 갱신한다.

### 2. 데이터 수집 및 Seed

- [ ] `data/mock_bizinfo_api_response.json`을 추가해 실제 기업마당 API 응답 형태의 mock을 만든다.
- [ ] API 응답과 mock API 응답이 같은 normalizer를 거치도록 정리한다.
- [ ] `data/scripts/seed_policies.py`를 추가해 mock 정책 데이터를 DB에 적재한다.
- [ ] 기업마당 API 호출 결과를 DB에 upsert하는 `PolicyIngestionService`를 추가한다.
- [ ] API 호출 실패 시 기존 mock fallback이 아니라, 마지막으로 저장된 DB 데이터를 우선 사용하도록 전환한다.

### 3. 계층 분리

- [ ] `app/services/policy_ingestion.py`를 추가한다.
- [ ] `app/services/policy_search.py`를 추가한다.
- [ ] `app/repositories/policy.py`에서 외부 API 호출 책임을 분리한다.
- [ ] `app/repositories/policy_db.py` 또는 기존 repository를 DB 조회/저장 전용으로 정리한다.
- [ ] FastAPI route는 Service 호출만 담당하도록 단순화한다.
- [ ] Tool은 Agent가 필요한 입력/출력 계약만 유지하도록 정리한다.

### 4. Tool Schema 및 Missing Slot

- [ ] `PolicySearchInput`에 `business_stage`, `preferred_support_type`, `income_level` 등 추천 품질을 높이는 선택 필드를 검토한다.
- [ ] 최소 추천 조건을 `region`, `age`, `employment_status`, `is_entrepreneur` 기준으로 정리한다.
- [ ] 창업/소상공인 정책에서는 `has_registered_business` 또는 `business_stage`가 부족할 때 추가 질문을 하도록 보강한다.
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
- [ ] Controller / Service / Repository / Tool 계층 구조를 다이어그램으로 정리한다.
- [ ] Tool Schema와 누락 조건 되묻기 전략을 설명한다.
- [ ] MVP 범위와 Out of Scope를 명확히 분리한다.
