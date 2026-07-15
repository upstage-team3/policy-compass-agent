# 다음 개발 작업

최종 갱신: 2026-07-15

세부 배경은 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 먼저 읽는다.
코드와 테스트가 이 문서보다 우선한다.
교차 검증과 단계별 완료 기준은 [INTEGRATED_ARCHITECTURE_ISSUES.md](INTEGRATED_ARCHITECTURE_ISSUES.md)를 따른다.

## 완료된 구조 기준선

- [x] 기업마당 검색, Policy REST/RAG-lite, `PolicyItem`, 가중 점수 파이프라인 제거
- [x] 창업지원 질문을 LLM `out_of_scope`로 통합하고 외부 Tool·기업마당·K-Startup 링크 제거
- [x] 턴 검색·초안·검증 상태 초기화와 pending `KEEP/RESUME/CANCEL/REPLACE`
- [x] 세 활성 소스 결과를 `SearchOutcome(success/no_match/unavailable/partial)`으로 정규화
- [x] guide/장애 안내 레코드를 후보 배열에서 제거하고 warnings/status로 이동
- [x] 명시적 불일치·마감은 제외하고 근거 부족은 `unverified` 참고 카드로 보존하는 3상태 gate
- [x] Work24 훈련 지역명→공식 `srchTraArea1` 코드 적용
- [x] 무필터 공채기업정보를 기본 채용 결과에서 제외
- [x] LangGraph를 8개 의미 노드로 통합
- [x] retryable source 조회 추가 1회, deterministic query rewrite 1회, 답변 revision+재검증 1회 상한
- [x] `direct_response`까지 포함한 공통 `verify_answer` 경로와 검증 실패 안전 수렴
- [x] PARTIAL 공개 경고, 시·군·구 gate, 검증 실패 추천 카드·후보 snapshot 차단
- [x] Pydantic profile allowlist와 필드별 `SET/CLEAR/UNCHANGED`
- [x] `SupabaseChatMemoryRepository` 단일 경계, recent 8/history·pending·allowlist 후보 snapshot·`last_search_plan`
- [x] Supabase 미설정·장애 시 최대 2,048세션 bounded local LRU mirror
- [x] 같은 프로세스·세션 load→graph→save 직렬화, UUIDv4 검증, graph 60초 bounded deadline
- [x] 인프로세스 세션 20회/분·IP 120회/분 sliding-window rate limit
- [x] `/api/live`와 설정 기반 `/api/ready` 분리
- [x] CD checkout/tag/release metadata를 CI exact SHA로 고정하고 GHCR digest로 배포
- [x] 조건 질문·일반 대화·검색 답변·상태 안내·후속 질문을 Solar 우선 경로로 전환하고 결정론적 fallback 유지
- [x] `astream` 기반 LangGraph 노드 진행 상태 SSE와 검증 전 초안 비노출
- [x] React 첫 안내·사이드바·입력창을 온통청년 5개 분야와 고용24 훈련·채용 MVP 범위로 축소

현재 그래프:

```text
prepare_request
├─ RESPOND / missing slots → direct_response → verify_answer
│                                             ├─ 실패 → direct_response (validation_fatal)
│                                             └─ 통과 → finalize → END
└─ SEARCH → retrieve → assess_evidence
                ├─ retryable UNAVAILABLE → retrieve (총 2회 이내)
                ├─ rewrite 가능한 NO_MATCH → rewrite_query → retrieve (1회)
                ├─ 근거 없음 → direct_response → verify_answer
                └─ 근거 있음 → build_answer → verify_answer
                                           ├─ 수정 가능 → build_answer (1회)
                                           ├─ 실패 → direct_response → verify_answer
                                           └─ 통과 → finalize → END
```

## P0. 구조 개편 회귀 고정

- [x] 전체 Python 테스트, Ruff, 프런트 테스트와 production build를 같은 working tree에서 실행해 로컬 기준선 기록
- [x] 검색 후 인사/설명, pending KEEP/RESUME/CANCEL/REPLACE, turn retry counter 초기화 회귀 확인
- [x] 명시적 검색 요청의 valid-but-wrong LLM 결정과 pending slot 답변 오판을 semantic guard로 복구
- [x] `SearchOutcome`의 네 상태와 guide 제거를 세 source fixture로 고정
- [x] retryable 장애가 총 2회에서 멈추고, rewrite/revision이 각각 1회를 넘지 않는지 확인
- [x] query rewrite가 지역·나이·상태·구체 주제 같은 hard condition을 완화하지 않는지 확인
- [x] API 추천 카드와 세션 후보 snapshot이 gate·답변 검증을 통과한 `success`/`partial` 후보만 포함하는지 확인

## P1. 세션 메모리와 동시성 경계

그래프는 전역 `MemorySaver`를 사용하지 않는다. 현재 인프로세스 기준선은
`SupabaseChatMemoryRepository`가 프로필·최근 8개 이력·pending·allowlist된
`last_presented_candidates`를 단일 계약으로 load/save하고, Supabase 미설정이나
실패 시 최대 2,048세션 local LRU mirror를 사용하는 것이다.

- [x] 요청마다 새 TurnState를 만들고 세션 상태와 검색/검증 상태가 섞이지 않게 유지
- [x] profile/history/pending/allowlist 후보 snapshot을 단일 저장소 경계로 확정
- [x] 검증 성공 후보 최대 3건만 `last_presented_candidates`로 저장
- [x] 같은 프로세스·`session_id`의 load→graph→save를 `SessionLockPool`으로 직렬화
- [x] Supabase 미설정·장애 시 bounded local LRU mirror 동작을 contract test로 고정
- [ ] 멀티워커 owner binding과 sticky routing 또는 동등한 소유권 경계 도입
- [ ] DB optimistic version으로 교차 프로세스 lost update 차단
- [ ] 서버 세션·로그 삭제 API와 TTL·보존 정책 확정

## P2. Grounding과 의미 평가

현재 검증은 후보명·허용 URL 중심이므로 claim 단위 검증은 남은 핵심 과제다.

- [ ] 후보 ID·원본 필드·claim·citation을 연결하는 구조화 AnswerPlan 도입 검토
- [ ] 후보에 없는 금액·기간·신청방법과 후보 A 사실/후보 B URL 결합 차단
- [x] 연령·지역·경력처럼 구조화 근거가 부족한 요건은 `unknown/unverified` 참고 카드로 표시
- [ ] source별 관련성·자격·citation fixture와 hard mismatch release blocker 추가
- [ ] `NO_MATCH`와 `UNAVAILABLE` 사용자 안내 정확도 평가
- [ ] Langfuse metadata에 release SHA, source status, requested/applied filters, retry/rewrite/revision, gate 전후 건수 기록
- [ ] 과거 93.3% 평가는 역사적 smoke baseline으로만 취급하고 현재 코드 semantic experiment를 새로 생성

## P3. 보안·개인정보

- [x] API `session_id`를 UUIDv4로 제한
- [x] 인프로세스 세션 20회/분·IP 120회/분 제한과 `Retry-After`
- [ ] 로그인 또는 서버 서명 익명 세션으로 owner와 `session_id` 결합
- [ ] 다른 owner의 세션 접근을 403/404로 차단
- [ ] 멀티워커 공유 owner/IP/session rate limit과 전역 동시 실행 상한
- [ ] Supabase 서버 로그 보존 기간, 삭제 API, 사용자 고지 확정
- [ ] Langfuse 전송 전 allowlist redaction과 로그 PII scan

## P4. 운영·배포 회귀

- [x] graph 60초·LLM 8초·source 10초·repository HTTP 9초의 bounded worst-case 예산과 설정 검증
- [ ] 공통 turn deadline의 남은 예산을 각 노드에 전달하고 Router+Profile 통합 후 상한 재축소
- [x] 세션·IP 인프로세스 rate limit과 429 응답 회귀 고정
- [ ] 로컬/CI 키 누락에서 `/api/ready`가 `200 degraded`인지 확인
- [ ] production 필수 설정 누락에서 `/api/ready`가 `503 not_ready`인지 확인
- [ ] readiness 응답에 API 키·Supabase URL/키 값이 노출되지 않는지 확인
- [ ] 성공한 CI의 `workflow_run.head_sha`, checkout SHA, `APP_RELEASE_SHA`가 같은지 확인
- [ ] GCE의 `.current_image`가 mutable tag가 아닌 `image@sha256:...`인지 확인
- [ ] 배포본 `/`, `/docs`, `/api/live`, `/api/ready`와 세 활성 Tool 대표 질문 확인
- [ ] rollback도 `.previous_image`의 digest를 사용하는지 확인
- [ ] readiness는 현재 구성 여부 검사임을 유지하고, 실제 upstream/circuit probe는 별도 후속 설계

## P5. 제품 QA

- [ ] 훈련 질문이 `training`과 적절한 `search_query`를 만들고 지역 code/gate를 적용하는지 live 확인
- [ ] 채용 질문이 `recruitment`만 호출하며 무필터 company 결과를 섞지 않는지 확인
- [ ] 온통청년 대표 5개 분야에서 연령·지역·관련성 gate를 확인
- [ ] 창업 질문이 LLM `out_of_scope`를 사용하되 Tool과 외부 창업 사이트 링크를 반환하지 않는지 확인
- [ ] 일반 대화가 고민과 문맥에 맞는 실용적 Solar 응답을 반환하는지 의미 평가
- [ ] 실제 LLM token streaming과 요청 취소는 후속 기능으로 유지

## 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

## 대표 회귀 질문

| 질문 | 기대 action | 기대 mode | 기대 request_kind |
| --- | --- | --- | --- |
| 요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어 | `RESPOND` | `general` | `general` |
| 국비지원 훈련을 받으면 뭐가 좋아? | `RESPOND` | `explain` | `general` |
| 청년도약계좌의 현재 조건을 설명해줘 | `SEARCH` | `explain` | `youth_policy` |
| 서울에서 클라우드 엔지니어 국비과정 찾아줘 | `SEARCH` | `recommend` | `training` |
| 서울 사는 만 28세 미취업자인데 청년정책 찾아줘 | `SEARCH` | `recommend` | `youth_policy` |
| 서울 데이터 분석 신입 채용정보 찾아줘 | `SEARCH` | `recommend` | `recruitment` |
| 카페 창업 지원사업 추천해줘 | `RESPOND` | `out_of_scope` | `general` |

멀티턴 회귀:

```text
사용자: 거주지원을 받고 싶은데 관련 정책 있어?
Agent: 거주 지역, 만 나이 확인
사용자: 안녕하세요
Agent: 일반 범위 안내, pending은 KEEP
사용자: 서울에 사는 만 25세야
Agent: required slot 충족으로 원래 주거 검색 RESUME
```
