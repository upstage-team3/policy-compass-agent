# 정책나침반 개발 인수인계

최종 갱신: 2026-07-15
기준: 8-node bounded graph, LLM-first language path, `SearchOutcome`, 세 소스 무점수 gate

## 새 개발 세션의 읽기 순서

1. 이 문서에서 현재 구조와 남은 위험을 확인한다.
2. [PROJECT_STATUS.md](PROJECT_STATUS.md)에서 구현 상태를 확인한다.
3. [NEXT_ACTIONS.md](NEXT_ACTIONS.md)에서 우선순위와 완료 조건을 확인한다.
4. Tool 계약은 [API_TOOL_SCHEMA_DESIGN.md](API_TOOL_SCHEMA_DESIGN.md)를 읽는다.
5. 배포는 [day4/DEPLOYMENT_RUNBOOK.md](day4/DEPLOYMENT_RUNBOOK.md)를 따른다.
6. 전체 문서의 현재/역사 구분은 [README.md](README.md)에서 확인한다.

일일회고와 2026-07-14 감사 문서는 의사결정 근거다. 현재 동작은 코드와 테스트를
최종 기준으로 삼는다.

## 현재 제품 범위

활성 검색 소스는 정확히 세 개다.

| request kind | 소스 | 제공 범위 |
| --- | --- | --- |
| `youth_policy` | 온통청년 | 청년정책 |
| `training` | 고용24 | 국민내일배움카드 훈련과정 |
| `recruitment` | 고용24 | 채용행사·공채속보 보조정보 |

- 한 요청에서는 선택된 Tool 하나만 호출한다.
- 기업마당 API 검색, `/api/policies*`, RAG-lite, `PolicyItem`, 가중 점수 계산은
  2026-07-15 제거됐다.
- 창업·사업자 지원은 현재 MVP 범위 밖이다. 창업 질문은 LLM Router와 대화 생성기를
  사용하는 일반 `out_of_scope` 응답으로 처리하되 외부 검색 Tool을 호출하거나 기업마당·
  K-Startup을 제품 연동처럼 안내하지 않는다.
- 레거시 UI DTO의 `match_score`, `evidence_coverage` 숫자 필드는 전송 호환용이며
  추천 판단에 사용하지 않는다.

## 현재 LangGraph

등록 노드는 8개다.

```text
prepare_request
├─ RESPOND / missing slots → direct_response → verify_answer
└─ SEARCH → retrieve → assess_evidence
                ├─ retryable UNAVAILABLE → retrieve (총 2회 이내)
                ├─ 보정 가능한 NO_MATCH → rewrite_query → retrieve (1회)
                ├─ 근거 없음 → direct_response → verify_answer
                └─ 근거 있음 → build_answer → verify_answer
                                           ├─ 수정 가능 → build_answer (1회)
                                           ├─ 검증 실패 → direct_response → verify_answer
                                           └─ 통과 → finalize → END
direct_response 검증 실패 → direct_response(validation_fatal) → verify_answer → finalize
```

### 노드 책임

| 노드 | 책임 |
| --- | --- |
| `prepare_request` | Router, typed route validation, profile extraction, pending 전이, missing slot 계산 |
| `direct_response` | 일반/범위 밖/조건 질문/no-match/장애를 LLM 우선으로 작성하고 검증 실패 시 결정론적 fallback으로 수렴 |
| `retrieve` | 선택된 세 소스 중 하나를 호출하고 `SearchOutcome` 생성 |
| `assess_evidence` | source별 결정론적 무점수 gate와 제외 사유 기록 |
| `rewrite_query` | hard condition을 유지하는 허용된 검색 표현만 최대 1회 보정 |
| `build_answer` | 카드 수·소스·지역 범위만 LLM에 전달해 짧은 카드 안내를 작성하고 결정론적 확인 문구 적용 |
| `verify_answer` | 최초 검색 말풍선의 카드 상세 중복, direct/status 환각, 민감정보 요구를 검증하고 revision budget 결정 |
| `finalize` | 검증된 응답을 더 바꾸지 않고 최근 이력 갱신 |

노드 수를 줄인 목적은 관측성을 포기하는 것이 아니라 bookkeeping 노드를 합치고
실패 회복 edge를 명시하는 것이다. 내부 route/profile/slot 작업은 필요하면 child
span으로 관측한다.

## 검색 결과 계약

`app/graph/search_contracts.py`의 `SearchOutcome`이 Repository/Tool과 그래프 사이의
공통 경계다.

```text
status: success | no_match | unavailable | partial
source: youth_policy | training | recruitment
items
requested_filters
applied_filters
warnings
retryable
```

- 키 미설정, 호출 실패, 파싱 실패 같은 guide 레코드는 후보가 아니라
  `status/warnings/retryable`로 바뀐다.
- `no_match`는 정상 조회 0건이고 `unavailable`은 정책 유무를 확인하지 못한
  상태다. 사용자 문구와 retry edge가 다르다.
- `partial`은 일부 하위 조회가 실패한 상태다. 확인된 후보가 있으면 범위
  한정 경고를 붙여 제시하고, 확인된 후보까지 gate에서 탈락하면 전체
  무결과로 단정하지 않는 고정 재시도 안내로 끝낸다.
- HTTP 200이더라도 XML `<error>`·실패 `resultCode`는 빈 결과가 아니라
  `unavailable`로 올린다.

## 검색 결과 표시 계약

- 최초 검색 성공 응답은 `reply` 말풍선과 최대 3개의 `recommendations` 카드로 분리한다.
- 말풍선은 LLM이 카드 수·데이터 소스·`partial`/`nearby` 범위만 받아 1~2문장으로
  작성한다. 후보 원문 전체는 이 LLM 호출에 전달하지 않는다.
- 정책명·과정명·기업/기관명·지원 내용·금액·날짜·자격·신청 방법·공식 URL은 카드에만
  표시한다. 말풍선에서 후보 제목이나 URL을 반복하면 검증 실패다.
- 말풍선 끝에는 `최종 신청 가능 여부는 공식 공고나 담당 기관에서 한 번 더 확인해 주세요.`를
  코드가 정확히 한 번 붙인다. LLM은 이 문구를 만들지 않는다.
- LLM 생성이나 1회 수정이 검증에 실패해도 검증된 카드를 버리지 않고 같은 메타데이터의
  결정론적 카드 요약으로 대체한다.
- 사용자가 이후 `1번 자세히`, `신청 방법은?`처럼 직전 카드를 명시적으로 물을 때만
  allowlist snapshot을 근거로 상세 말풍선과 공식 URL을 제공한다.
- 후보 후속 LLM이 금액·날짜·URL을 바꾸어 두 번 검증에 실패하면 같은 snapshot의
  공식 값을 결정론적으로 조립한다. snapshot이 없으면 번호를 추측하지 않고 재검색을 요청한다.

## 결정론적 무점수 gate

`app/graph/evidence.py`가 세 소스를 공통 경계에서 평가한다. 가중 합산이나 적합도
점수는 없다.

- 온통청년: 구조화 min/max 연령, 요청 지역, 구체 질의 관련성, 명시적 마감
- 고용24 훈련: 공식 `srchTraArea1` 지역 코드 적용과 결과 시·도/시·군·구 후처리
- 고용24 채용: `event`, `open_recruitment`만 허용하고 무필터 company 호출 계약은 완전 제거,
  구조화 시·도/시·군·구와 요청한 신입·인턴 근거를 확인
- gate 제외 사유와 전후 후보 수는 `evidence_assessment`에 남긴다.
- 요청 지역이 있는데 후보 지역을 확인할 수 없거나 같은 시·도 안의 다른
  시·군·구이면 카드·답변 후보에서 제외한다.
- 확인할 수 없는 조건을 자동 적합으로 점수화하지 않는다.

## 프로필 계약

`app/graph/profile_contracts.py`의 `ProfileState`가 세션 프로필의 Pydantic
allowlist다. 나이 범위, enum, 문자열 길이와 관심 분야 수를 필드별로 검증한다.
upstream 필터나 evidence gate에 쓰이지 않는 졸업상태는 새로 추출·저장하지 않으며,
API 응답의 기존 nullable 필드만 프런트 호환을 위해 유지한다.

- 유효하고 명시된 값은 `SET`
- 비어 있거나 잘못된 LLM 추출은 기존 값을 보존하는 `UNCHANGED`
- “나이는 저장하지 마”, “지역을 지워줘”, “프로필 모두 삭제” 같은 명시 요청은
  결정론적 `CLEAR`
- `CLEAR`는 같은 턴의 충돌하는 추출보다 우선하고 RESPOND 경로에서도 적용

## bounded recovery

모든 cycle은 턴 상태 카운터로 제한된다.

| 실패 | edge | 상한 | 소진 후 |
| --- | --- | ---: | --- |
| retryable source 장애 | `assess_evidence → retrieve` | 조회 총 2회 | source unavailable 안내 |
| 허용된 정상 무결과 | `assess_evidence → rewrite_query → retrieve` | rewrite 1회, 조회 총 2회 내 | no-match 안내 |
| 답변 검증 실패 | `verify_answer → build_answer/direct_response` | LLM revision 1회 | 결정론적 fallback 또는 안전 종료 |

query rewrite는 지역·나이·상태·마감·월세/전세 같은 구체 주제를 완화하지 않는다.
현재 구현은 제한된 deterministic rewrite만 허용한다.
전체 턴은 60초, 개별 LLM 요청은 8초, 소스 조회 시도는 10초,
Repository HTTP는 9초 상한이다. 최대 LLM 4회·소스 2회와 8초 예비 시간을
포함한 bounded worst case가 60초에 들어오지 않으면 설정 로드 단계에서 거절한다.
채용행사와 공채속보는 같은 소스
시도 안에서 병렬 조회하며 한 endpoint 실패 시 확인된 결과만 `partial`로 보존한다.

## 턴과 세션 상태

- `fresh_turn_fields()`는 검색 문맥, `SearchOutcome`, gate 결과, retry/rewrite/revision
  카운터, 결과 bucket, draft와 검증 상태를 매 요청 초기화한다.
- pending은 `required_slots`와 `KEEP/RESUME/CANCEL/REPLACE` 전이를 사용한다.
- `RESUME`은 현재 발화가 실제 required slot을 채웠을 때만 허용한다.
- 일반 입력도 LLM Router가 의미를 판단한다. 인사·감사·취업 고민·일반 설명·범위 밖
  요청까지 대화 생성 LLM이 최근 문맥과 검증된 프로필을 받아 작성한다. 카드 검색 요약,
  조건 질문, 직전 후보 후속 질문, no-match/unavailable/partial 안내도 각각 근거가 제한된
  LLM 프롬프트를 1차 경로로 사용하고, LLM 미설정·장애·재검증 실패 때만 고정 템플릿으로 수렴한다.
- 범위 밖 여부는 LLM Router가 판단하되 최종 문구는 고정된 정책나침반 범위 안내를 사용한다.
  첫 인사는 이전 대화가 없는데 `다시`, `오랜만`, `지난번` 같은 관계를 만들면 재검증한다.
- `성남 거주`, `성남거주`처럼 `시·군·구` 접미사를 생략한 공식 지역명도 거주·나이
  답변 문맥에서 인식한다. 임의 부분문자열은 지역으로 보지 않으며, 동명이인 별칭은
  특정 시·도로 추정하지 않고 `region_detail`을 묻는다.
- 검증 전의 tentative LLM route가 `REPLACE`를 제안해도 semantic guard가 일반
  응답으로 복구하면 기존 pending을 `KEEP`한다.
- 그래프는 전역 `MemorySaver` 없이 컴파일된다.
- `SupabaseChatMemoryRepository`가 profile, 최근 8개 history, pending,
  allowlist된 `last_presented_candidates`의 단일 세션 경계다.
- Supabase 미설정·조회/저장 장애에서도 최대 2,048세션의 bounded local LRU
  mirror가 같은 프로세스의 멀티턴 상태를 유지한다.
- 원격 저장 실패 세션은 dirty로 표시해, 다음 load가 더 오래된 Supabase 행으로
  로컬 CLEAR·pending·snapshot을 되돌리지 않게 한다.
- `SessionLockPool`이 같은 프로세스·같은 세션의 load→graph→save를 직렬화한다.
- 직전 후보 스냅샷은 최대 3건, source별 allowlist 필드만 저장하며 검증을 통과한
  `success/partial` 검색 턴만 새 스냅샷을 만들 수 있다.
- `chat_sessions.last_presented_candidates` additive migration 전 환경에서는 기존
  `pending_request` JSONB의 예약 키에 같은 allowlist snapshot을 임시 보존한다. 읽을 때
  예약 키를 pending 상태에서 분리하므로 그래프 슬롯 전이에는 노출되지 않는다.
- 저장된 snapshot을 읽을 때도 source/type/scope/guide ID/URL을 다시 검증해
  레거시 guide·company 레코드가 후속 답변으로 노출되지 않게 한다.
- 세션 ID는 UUIDv4만 허용한다. 그래프 턴 deadline은 60초다.
- 인프로세스 limiter는 세션당 분당 20회, IP당 분당 120회이며 초과 시
  `429 Retry-After`를 반환한다.

## API·UI 호환 계약

React UI 변경과 충돌을 피하기 위해 다음 계약을 유지한다.

- `POST /api/chat/stream` 요청: `session_id`, `message`, 선택적 `profile_defaults`
- SSE event: `status`, `token`, `done`, `error`
- `status.stage`: `accepted`, 실제로 실행된 8개 LangGraph 노드, `timeout`,
  그래프를 실행하지 않는 보호 경로의 `complete`
- SSE 경로는 `astream(updates, values)`로 노드 완료 상태를 즉시 전송하되,
  내부 state·검증 전 초안은 전송하지 않는다. 최종 답변 `token`은
  `verify_answer` 통과와 `finalize` 완료 후에만 전송한다.
- `done`: `intent`, `missing_slots`, `recommendations`, `profile_defaults`, `trace_id`
- `profile_defaults.age/region`의 `null`은 명시적 CLEAR다. 브라우저가 기존 값을
  merge해 부활시키지 않도록 두 키를 항상 보낸다.
- React 첫 안내는 온통청년 5개 공식 분야(`일자리`, `주거`, `교육·직업·훈련`,
  `금융·복지·문화`, `참여·기반`)와 고용24 훈련·채용정보만 노출한다.
- React 입력창 placeholder는 `청년 정책 및 훈련에 대해 질문해 주세요...`로
  범용 정부 지원사업 검색 범위를 표방하지 않는다.
- 추천 카드 DTO: `policy`, `match_score`, `evidence_coverage`, `match_reasons`,
  `follow_up_checks`, `is_recommendable`, `recommendation_scope`, `deadline_status`
- feedback: `POST /api/chat/feedback`와 Langfuse `user-thumbs` 연결

추천 카드와 새 세션 스냅샷은 현재 턴의 gate와 `verify_answer`를 통과하고 상태가
`success/partial`인 후보만 사용한다. 실제 조회까지 수행한 더 최근 검색이
`no_match`·장애·검증 실패로 끝나면 과거 후보 번호가 “방금 결과”로 재사용되지 않도록
snapshot을 명시적으로 비운다. 조건 질문·일반 응답은 기존 snapshot을 보존한다.

## 운영 health와 배포 불변식

| endpoint | 의미 |
| --- | --- |
| `/api/health` | 기존 클라이언트 호환 상태와 Langfuse 설정 표시 |
| `/api/live` | 외부 의존성과 무관한 프로세스 생존, 200 |
| `/api/ready` | release SHA, app env, Upstage/온통청년/Work24 훈련·채용/Supabase 구성 상태 |

- 로컬/CI에서 필수 키가 없으면 `/api/ready`는 `200 degraded`다.
- `APP_ENV=production`에서 필수 구성이 빠지면 `503 not_ready`다.
- 응답에는 키·URL 값 자체를 내보내지 않는다.
- readiness는 현재 구성 여부 검사다. 실제 upstream 연결이나 circuit 상태까지
  확인하는 probe는 후속 범위다.

CD 불변식:

1. `RELEASE_SHA = workflow_run.head_sha`(수동 실행은 `github.sha`)
2. checkout, image tag, `APP_RELEASE_SHA`가 같은 exact SHA를 사용
3. 배포 대상은 mutable tag가 아니라 build output digest의
   `ghcr.io/.../policy-compass-agent@sha256:...`
4. `.current_image`와 `.previous_image`도 digest reference를 기록
5. 컨테이너와 배포 작업은 `/api/ready`를 사용

## 핵심 파일

| 파일 | 책임 |
| --- | --- |
| `app/graph/graph.py` | 8개 노드와 bounded edge 조립 |
| `app/graph/edges.py` | SearchOutcome와 budget 기반 분기 |
| `app/graph/state.py` | 턴 상태와 retry/rewrite/revision counter |
| `app/graph/search_contracts.py` | 검색 상태 공통 계약과 legacy guide adapter |
| `app/graph/evidence.py` | 세 소스 결정론적 gate |
| `app/graph/nodes.py` | 노드 orchestration |
| `app/graph/validators.py` | 응답 역할·grounding 검증 |
| `app/graph/response_composer.py` | source별 결정론적/grounded 응답 |
| `app/api/routes/chat.py` | 동기·SSE·피드백 API 경계 |
| `app/api/routes/health.py` | health/live/readiness |
| `app/repositories/youthcenter.py` | 온통청년 정규화·조회 |
| `app/repositories/work24_training.py` | Work24 훈련 지역 코드·조회 |
| `app/repositories/work24_recruitment.py` | Work24 허용 채용 보조정보 조회 |

## 알려진 남은 위험

1. UUIDv4는 소유권 경계가 아니다. multi-worker owner binding이 아직 없다.
2. `SessionLockPool`은 단일 프로세스만 보호한다. DB optimistic version은 남아 있다.
3. Supabase 세션/로그의 서버 삭제 API와 TTL이 없다.
4. answer validator는 후보명·URL과 후보에 없는 구조화 금액·날짜를 차단하지만 완전한 claim-field-citation 검증은 남아 있다.
5. SSE 노드 상태는 실시간으로 전송하지만, `token`은 검증이 끝난 완성
   답변을 나눠 보내는 방식이며 실제 LLM token stream이 아니다.
6. 인프로세스 rate limiter는 multi-worker 전체 쿼터를 공유하지 않는다.
7. `/api/ready`는 구성 상태만 확인하고 upstream 실제 연결·circuit 상태를 확인하지 않는다.
8. 새 8-node/SearchOutcome 변경분의 실제 GCE 배포와 live 대표 질의 회귀가 필요하다.
9. 과거 Langfuse 93.3%는 구 그래프의 기계적 smoke baseline이며 현재 품질 근거가 아니다.

## 다음 작업 순서

1. claim-candidate-field-citation 검증과 semantic Langfuse 평가를 보강한다.
2. multi-worker owner binding과 DB optimistic version을 추가한다.
3. 서버 세션/로그 TTL·삭제 API와 사용자 고지를 추가한다.
4. 분산 rate limit이 필요할 운영 규모와 저장소를 결정한다.
5. exact SHA/digest 배포본에서 `/api/live`, `/api/ready`, 세 Tool과 창업 out-of-scope를 회귀한다.

## 로컬 검증

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

로컬 전체 suite는 통과했다. 테스트는 외부 키와 네트워크 없이 결정적으로 통과해야
하며, 테스트 개수는 coverage 추가에 따라 변하므로 고정 숫자를 기준으로 사용하지 않는다.

## 비밀값 및 Git 주의사항

- `.env`는 커밋하지 않는다.
- API 키, 인증 URL query, authorization header를 로그·문서·캡처에 남기지 않는다.
- `SUPABASE_KEY`는 브라우저에 전달하지 않는다.
- 기존 사용자/팀원 변경을 되돌리지 않는다.
