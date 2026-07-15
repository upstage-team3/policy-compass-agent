# 개발 로드맵

최종 갱신: 2026-07-15

> 이 문서는 중장기 방향을 정리한다. 당장 이어서 할 일은
> [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)와
> [NEXT_ACTIONS.md](NEXT_ACTIONS.md)를 우선한다.

## 제품 목표

정책나침반은 취업 준비 청년에게 온통청년 정책과 고용24 훈련·채용 보조정보를
공식 근거와 함께 안내하는 Agent다. 기능 수보다 다음 불변식을 우선한다.

- 정상 경로는 짧다.
- 실패 상태는 정상 무결과와 구분한다.
- 명시적 자격 불일치는 생성 전에 제외한다.
- 모든 retry/rewrite/revision은 상한이 있다.
- 근거를 검증하지 못하면 정직하게 중단한다.

```text
요청 계획
→ 부족 조건 확인 또는 Tool 하나 선택
→ SearchOutcome
→ 결정론적 무점수 evidence gate
→ 근거 기반 답변
→ 답변 재검증
→ 비변형 finalize
```

## 현재 범위

| 우선순위 | 소스/기능 | 상태 |
| --- | --- | --- |
| 1 | 온통청년 청년정책 | 활성 |
| 2 | 고용24 국민내일배움카드 훈련과정 | 활성 |
| 3 | 고용24 채용행사·공채속보 보조정보 | 활성, 직접 채용공고 전체가 아님 |
| 4 | 창업지원 | MVP 범위 밖: LLM 범위 안내, Tool·외부 링크 미사용 |

기업마당 API 검색, Policy REST/RAG-lite, `PolicyItem`, 가중 적합도 점수는 제품
범위에서 제거됐다. 다시 도입하려면 별도 제품 결정과 데이터 적합성 검증이 필요하다.

## 현재 8-node 아키텍처

```text
prepare_request
├─ direct_response → verify_answer
│                    ├─ validation_fatal → direct_response → verify_answer
│                    └─ finalize → END
└─ retrieve → assess_evidence
       ├─ retryable failure → retrieve (총 2회)
       ├─ rewriteable no-match → rewrite_query → retrieve (1회)
       ├─ no evidence → direct_response → verify_answer
       └─ build_answer → verify_answer
                           ├─ revision → build_answer (1회)
                           ├─ fatal → direct_response → verify_answer
                           └─ finalize → END
```

그래프는 전역 `MemorySaver`를 사용하지 않는다. TurnState는 요청마다 새로 만들고,
`SupabaseChatMemoryRepository`가 프로필·최근 8개 이력·pending·allowlist된 직전
후보의 단일 세션 경계다. Supabase 미설정·실패 시에는 최대 2,048세션 local LRU
mirror를 사용하고 같은 프로세스·세션의 load→graph→save는 lock으로 직렬화한다.

## 완료 이력

### 기반 MVP

- FastAPI, React UI, Docker Compose
- Upstage Solar Router/Profile/응답 경로와 규칙 fallback 격리
- 온통청년, Work24 훈련, Work24 허용 채용 보조 endpoint 연동
- SSE `status/token/done/error`, 추천 카드와 feedback/Langfuse score 계약
- 브라우저 대화 복원·UUID 세션·PII 마스킹
- Supabase 대화/프로필/pending 저장 기반

### 2026-07-15 구조 안정화

- 기업마당 검색과 가중 점수 파이프라인 제거
- 창업·사업자 지원을 Tool 미호출 LLM `out_of_scope`로 통합
- fresh-turn reset과 pending `KEEP/RESUME/CANCEL/REPLACE`
- `SearchOutcome(success/no_match/unavailable/partial)` 도입
- guide 후보 제거와 장애/무결과 분리
- 온통청년 연령·지역·관련성 gate
- Work24 훈련 공식 지역 코드와 후처리 지역 gate
- Work24 채용 무필터 company 기본 제외와 허용 유형 gate
- 11개 bookkeeping 중심 노드를 8개 의미 노드로 통합
- source retry/query rewrite/answer revision의 bounded feedback edge
- 검증 후 내용을 바꾸지 않는 `finalize`
- `/api/live`, 설정 기반 `/api/ready`
- CI exact `workflow_run.head_sha`, GHCR immutable digest 배포 계약
- Pydantic profile allowlist와 필드별 `SET/CLEAR/UNCHANGED`
- 시·군·구 검증 및 구조화 지역 검증 불가 후보 차단
- `direct_response` 공통 검증과 PARTIAL 공개 경고
- 검증 실패 추천 카드·allowlist 후보 snapshot 차단
- 명시적 Supabase 세션 경계와 bounded local LRU mirror
- UUIDv4 전용 세션 ID, 같은 프로세스 세션 lock,
  60초 그래프·8초 LLM·10초 소스·9초 Repository HTTP 예산
- 세션 20회/분·IP 120회/분 인프로세스 rate limit
- React UI를 온통청년 5개 분야와 고용24 훈련·채용 MVP 문구로 정렬

## Phase A — 회귀 기준선 고정 (로컬 완료)

목표: 구조 변경이 실제 사용자 계약을 깨지 않았음을 같은 working tree에서 확인한다.

- 전체 Ruff/pytest/frontend/build 실행
- 검색 후 일반 대화 state leak 0건
- pending 네 상태 전이 정확도
- SearchOutcome 네 상태와 guide 후보 0건
- source retry 총 2회, rewrite/revision 각 1회 상한
- gate 통과 후보만 API 카드에 포함
- startup/business 질문의 검색 Tool·외부 링크 0회, LLM `out_of_scope` 응답

현재 전체 로컬 Ruff·Python/프런트 회귀와 production build가 통과한다. 활성 외부
API와 실제 배포본 smoke는 Phase D/F의 별도 release 기준으로 계속 확인한다.

## Phase B — 명시적 저장소 세션 메모리 (인프로세스 기준 완료)

목표: 그래프 checkpoint에 기대지 않고 세션 상태의 소유권과 수명을 명확히 한다.

- [x] profile, recent 8-message history, pending을 load/save하는 단일 저장소 계약
- [x] 검증을 통과한 직전 제시 후보 최대 3건을 allowlist snapshot으로 저장
- [x] TurnState에는 검색 결과·검증·retry counter만 두고 요청 뒤 폐기
- [x] 같은 프로세스·session 동시 요청을 load→graph→save 범위에서 직렬화
- [x] Supabase 미설정·장애 시 bounded local LRU mirror contract test
- [ ] multi-worker owner binding과 routing
- [ ] DB optimistic version을 통한 교차 프로세스 충돌 방지
- [ ] 서버 세션·로그 삭제 API와 TTL·보존 정책

local LRU mirror는 프로세스 재시작·멀티워커 내구성을 보장하지 않으며 Supabase의
대체 영구 저장소가 아니다.

## Phase C — claim grounding

목표: 제목·URL 집합 검사를 넘어 사실과 출처를 후보 단위로 연결한다.

- AnswerPlan 또는 동등한 구조화 claim 계약
- candidate ID·source field·claim·citation binding
- 후보에 없는 금액·기간·신청방법 차단
- 후보 A 사실과 후보 B URL 교차 결합 차단
- 검증 실패 시 1회 revision 후 재검증, 두 번째 실패는 abstention
- `finalize` 전후 factual content 동일성 테스트

## Phase D — semantic evaluation

목표: 초록 trace가 실행 완료가 아니라 사용자 관점의 정확성을 뜻하게 한다.

- 세 source별 정상 검색·hard mismatch·장애·멀티턴·grounding 데이터셋
- requested/applied filter 일치율
- source별 Precision@3
- hard mismatch 노출 0건
- supported claim/citation precision
- `NO_MATCH`/`UNAVAILABLE` 구분 정확도
- 이전 턴 누출과 retry 상한 release blocker
- release SHA, source status, retry/rewrite/revision, gate 전후 수를 Langfuse에 기록

과거 93.3% 평가는 구 그래프의 역사적 smoke baseline이며 현재 release 품질
근거로 사용하지 않는다.

## Phase E — 보안·개인정보

- [x] UUIDv4 전용 세션 ID 검증
- [x] 세션·IP 기준 인프로세스 rate limit과 `Retry-After`
- 로그인 또는 서버 서명 익명 세션 owner binding
- 다른 owner session 접근 차단
- 멀티워커 공유 IP·owner·session rate limit과 전역 동시 실행 상한
- 서버 로그 보존 기간과 삭제/내보내기 API
- trace allowlist redaction과 PII scan

완료 전에는 공개 실서비스 준비가 끝났다고 판단하지 않는다.

## Phase F — 운영 안정화

- [x] 그래프 턴 전체 60초 deadline과 worst-case 설정 검증
- [x] LLM 8초·source 10초·Repository HTTP 9초 timeout 세분화
- 공유 HTTP client/pooling
- source별 circuit breaker와 짧은 cache
- 실제 upstream/circuit를 반영하는 readiness 확장 검토
- 실제 LLM token streaming과 요청 취소
- Docker smoke, dependency/secret/container scan

현재 `/api/ready`는 구성 여부만 확인한다. 로컬/CI 키 누락은 `200 degraded`,
production 필수 구성 누락은 `503 not_ready`다.

## 배포 revision 규칙

- CI가 성공한 `workflow_run.head_sha`를 exact checkout한다.
- 같은 전체 SHA를 image tag와 `APP_RELEASE_SHA`에 사용한다.
- GCE에는 tag가 아니라 `image@sha256:...` digest를 배포한다.
- `.current_image`와 `.previous_image`도 digest를 기록한다.
- 컨테이너와 배포 후 healthcheck는 `/api/ready`를 사용한다.

## DB/문서 고도화 후보

실시간 API의 재현성과 장애 내성을 더 높여야 할 때 다음을 검토한다.

```text
온통청년 / Work24 / 공식 문서
→ ingestion
→ 정규화·검증
→ source별 DB/cache
→ SearchOutcome adapter
→ LangGraph
```

- 외부 API 원본과 정규화 후보의 provenance 보존
- 정책 공고 PDF/HTML의 Document Parse/Information Extract
- 구조화한 지원 대상·제외 조건·제출 서류를 claim 근거로 사용

이 확장은 현재 세 source 계약을 대체하지 않고 adapter 뒤에 추가한다. 제거된
기업마당·RAG-lite 설계를 기본안으로 되돌리지 않는다.

## Out of Scope

- 최종 자격 판정 또는 합격 가능성 보장
- 실제 신청 대행
- 민감 개인정보 원문 저장
- 청년정책 외 분야 상담
- 모든 정부지원사업 실시간 동기화
- 모든 첨부 문서 자동 파싱
