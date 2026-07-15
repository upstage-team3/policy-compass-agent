# 정책나침반 개발 현황

최종 갱신: 2026-07-15

새 개발 세션은 먼저 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 읽는다.
Claude·Codex 교차 검증과 현재 잔여 이슈는 [INTEGRATED_ARCHITECTURE_ISSUES.md](INTEGRATED_ARCHITECTURE_ISSUES.md)를 기준으로 한다.

## 현재 요약

정책나침반은 FastAPI와 LangGraph를 사용하는 청년정책·훈련·채용 보조정보 Agent다. 2026-07-15 구조 개편으로 기업마당·Policy REST/RAG-lite·가중 스코어링을 제거하고, 그래프를 8개 의미 노드로 통합했다. 세 소스의 조회 결과는 `SearchOutcome`으로 정규화하며 결정론적 무점수 게이트 뒤에서 Upstage Solar가 조건 질문·일반 대화·검색 결과 설명·후속 질문·상태 안내를 생성한다. 창업·사업자 지원은 외부 Tool이나 사이트 안내 없이 일반 `out_of_scope`로 처리한다.

## 진행 상태

| 영역 | 상태 | 현재 기준 |
| --- | --- | --- |
| Docker | 완료 | Multi-stage 이미지와 Compose 구성 완료 |
| CI/CD | 구조 보강 완료 | 성공한 CI의 exact SHA를 checkout/tag/release metadata에 사용하고 GHCR digest로 배포; 현재 변경분 실제 배포 회귀 필요 |
| Google Cloud | 완료 | GCE 자동 배포 기반 보유; `/api/ready` 기반 새 배포 회귀 필요 |
| React UI | 3차 완료 | 추천 카드·피드백, 새로고침 복원, UUIDv4 유지, 프런트 회귀와 production build 통과 |
| MVP UI 문구 | 완료 | 온통청년 5개 분야·고용24 훈련/채용만 안내하고 창업·소상공인 표현 제거 |
| LLM Router | 구조 개편 완료 | 일반 입력까지 LLM이 의미 분류하고 `prepare_request` 안에서 계약·semantic guard·pending·필수 슬롯을 검증 |
| Conversation | LLM-first 개편 완료 | 인사·감사·취업 고민·일반 설명·범위 밖 응답을 최근 문맥 기반 Solar 응답으로 작성하고 동일 검증 경로 적용 |
| 프로필 추출 | 구조 보강 완료 | Pydantic allowlist와 필드별 `SET/CLEAR/UNCHANGED`로 검증된 값만 반영 |
| Tool 선택 | 4차 완료 | 주제가 아니라 정책·실제 과정·공채속보·채용행사라는 정보 객체로 Tool 하나를 고르고 보완 소스는 CTA만 제공 |
| 조건 확인 | LLM-first 개편 완료 | `NEW/RESUME/REFINE/REPLACE/FOLLOW_UP/CANCEL`, `required_slots`, 지역 `any`를 구분 |
| 검색 계약 | 완료 | `SearchOutcome(success/no_match/unavailable/partial)`과 guide 후보 제거 |
| 후보 검증 | 3상태 완료 | 명시적 불일치·마감은 제외하고 연령·지역·경력 근거 부족은 `unverified` 참고 카드로 보존 |
| 응답 생성 | 카드/말풍선 분리 완료 | Solar는 카드 수·소스·범위만 받아 짧은 안내를 만들고, 상세 정보는 카드에만 표시; 검증 실패 시 결정론적 카드 요약 fallback |
| 회복 경로 | 완료 | retry·rewrite가 공유하는 조회 총 2회, query rewrite 1회, 답변 revision+재검증 1회 상한 |
| 대화 메모리 | 인프로세스 기준 완료 | 최근 8개 이력·장기 프로필·pending·allowlist 후보 snapshot·결과 0건도 남기는 `last_search_plan`과 최대 2,048세션 local LRU mirror |
| 세션·트래픽 방어 | 인프로세스 기준 완료 | UUIDv4, 세션 lock, graph 60초·LLM 8초·source 10초·HTTP 9초 bounded 예산, 세션 20회/분·IP 120회/분 제한 |
| 온통청년 | live 검증 완료 | 전국 지역 코드·오표기·만료 필터 + 요청 헤더 안정화·5xx 재시도·장애 구분 |
| 고용24 훈련 | live 검증 완료 | 실데이터 3건과 상세 URL 확인 |
| 고용24 채용 | live 검증 완료 | 활성 채용행사·공채속보 2종 확인; 무필터 공채기업정보 제외 |
| 창업지원 | MVP 범위 밖 | 기업마당 API와 전용 redirect를 제거하고 Tool 미호출 `out_of_scope`로 통합 |
| SSE | 3차 완료 | `astream` 노드 상태를 React에 즉시 전송하고, 검증·finalize 후에만 최종 답변 전송 |
| Langfuse | 연결 완료 | LangGraph callback, 세션·태그·메타데이터, 종료 시 flush 적용 |
| 운영 health | 완료 | `/api/live`와 설정 기반 `/api/ready` 분리, release SHA와 비밀값 없는 의존성 상태 제공 |
| 테스트 | 로컬 기준 통과 | 전체 Python suite·프런트 회귀·production build 통과; Docker `/api/ready` smoke 통과 이력 |

## Agent 아키텍처

```text
prepare_request
├─ RESPOND / missing slots → direct_response → verify_answer
│                                             ├─ 검증 실패 → direct_response (validation_fatal)
│                                             └─ 통과 → finalize → END
└─ SEARCH → retrieve → assess_evidence
                ├─ retryable UNAVAILABLE, 총 2회 이내 → retrieve
                ├─ 보정 가능한 NO_MATCH, 1회 이내 → rewrite_query → retrieve
                ├─ 근거 없음 → direct_response → verify_answer
                └─ 근거 있음 → build_answer → verify_answer
                                           ├─ 수정 가능, 1회 이내 → build_answer
                                           ├─ 실패 → direct_response → verify_answer
                                           └─ 통과 → finalize → END
```

등록 노드는 `prepare_request`, `direct_response`, `retrieve`, `assess_evidence`,
`rewrite_query`, `build_answer`, `verify_answer`, `finalize`의 8개다. 그래프는
checkpointer 없이 컴파일되며 턴 상태는 매 요청 초기화한다.
`SupabaseChatMemoryRepository`가 장기 프로필·최근 8개 이력·pending·allowlist된
`last_presented_candidates`·`last_search_plan`의 단일 세션 경계다. Supabase 미설정 또는 실패 시에도
최대 2,048세션의 bounded local LRU mirror를 사용하고, 같은 프로세스·세션의
load→graph→save는 `SessionLockPool`이 직렬화한다.

## 핵심 기술 결정

- 일반 입력도 LLM Router가 판단한다. 키워드 규칙은 LLM 장애 fallback과 명백한
  검색/인사/범위 위반을 막는 좁은 semantic guard로만 사용한다.
- 라우팅 계약 검증은 별도 no-op 노드가 아니라 `prepare_request` 내부에서 수행하고 계약 위반 상태에만 fallback을 적용한다.
- 키워드와 정규식은 `app/graph/fallbacks.py`에만 둔다.
- LLM JSON은 `app/graph/contracts.py`의 Pydantic 모델로 검증한다.
- 세션 프로필은 `ProfileState` allowlist로 검증하고, 유효한 명시 값은 `SET`,
  명시적 삭제는 `CLEAR`, 빈 값·잘못된 값·미언급은 `UNCHANGED`로 적용한다.
- Tool 검색어는 Router의 `search_query`를 우선 사용한다.
- 온통청년·고용24 훈련·채용 Tool을 동시에 무차별 호출하지 않는다. 정책·제도와 실제 과정·공고를
  정보 객체로 구분하고, 다른 소스는 사용자가 선택할 수 있는 CTA로만 안내한다.
- 창업지원 요청은 `RESPOND/out_of_scope/general`로 분류한다. LLM Router·대화 생성은 사용하지만 외부 Tool과 창업 사이트 링크는 사용하지 않는다.
- 매 요청의 API 경계와 Router 진입에서 검색 결과·초안·검증 결과를 초기화해 이전 턴 증거가 새 답변을 오염시키지 않게 한다.
- pending은 `required_slots`가 현재 발화로 채워질 때만 `RESUME`하고, 무관 발화는 `KEEP`, 명시적 취소는 `CANCEL`, 새 검색은 `REPLACE`한다.
- 최초 검색 말풍선은 후보 제목·기관·금액·날짜·자격·신청 방법·URL을 반복하지 않고
  카드 수와 확인 안내만 1~2문장으로 제공한다. 상세 정보는 추천 카드가 단일 표시 책임을 가진다.
- Solar의 카드 요약 입력에는 후보 원문 대신 카드 수·소스·`partial`/`nearby`/`unknown` 범위와
  이번 조회에 실제 적용된 공개 필터만 전달한다.
- 후보 데이터에 없는 정책, 과정, 기업, 금액, 날짜, 링크를 생성하지 않는다.
- 신청 정보 누락은 실제 API null 필드만 `data_notice`로 전달하고 내부 필드명을 노출하지 않는다.
- 구체 검색어 결과가 없으면 무관한 넓은 분야 결과로 대체하지 않는다.
- 월세·전세·금융처럼 하위 유형이 명시된 검색은 상위 분야나 인접 지역 결과로 완화하지 않는다.
- 지역 정정 표현은 전환 표현 뒤의 새 지역을 우선하며, `지역 상관없이`는 저장된 거주지를
  지우지 않고 현재 훈련·채용 검색의 지역 제한만 해제한다. 시·도뿐 아니라 확인 가능한
  시·군·구까지 일치해야 한다. 구조화 지역이 없거나 검증할 수 없는 후보는 제외하지 않고
  `unverified` 참고 카드로 표시한다.
- 정확 지역과 전국 후보가 있으면 다른 지역 결과를 섞지 않는다.
- 정확 지역과 전국 후보가 모두 없을 때만 가까운 시·도 결과 최대 3건을 `nearby_reference`로 제공한다.
- 인접 거리는 도로 거리가 아닌 사용자 지역과 시·도 대표 좌표 간 직선거리임을 명시한다.
- 온통청년의 종료된 신청기간과 명시적인 지역 불일치는 결정론적으로 제외한다.
- 가중 점수와 `evidence_coverage`는 추천 판단에 사용하지 않는다. UI 호환 응답에 남은 숫자 필드는 전송용 자리표시자다.
- `SearchOutcome`은 정상 무결과와 외부 장애를 구분하며 guide/오류 안내 레코드를 후보로 전달하지 않는다.
- `PARTIAL` 후보로 답변할 때는 일부 하위 조회가 완료되지 않았다는 공개 경고를
  답변 앞에 붙이고 내부 오류 문구는 노출하지 않는다.
- `assess_evidence`는 세 소스 공통 무점수 게이트다. 온통청년은 연령·지역·구체 질의 관련성·명시적 마감, 훈련은 공식 Work24 지역 코드와 후처리 지역, 채용은 허용 유형·지역·마감을 결정론적으로 확인한다.
- source 재시도는 총 2회, 결정적 query rewrite와 답변 revision은 각각 최대 1회이며 hard condition을 완화하지 않는다.
- Router JSON 계약 뒤에는 고신뢰 semantic guard가 계약 오류·명시적 소스 모순·인사·범위 밖
  오판만 deterministic plan으로 복구하며, 휴리스틱 `GENERAL`이 정상 LLM `SEARCH`를 강등하지 않는다.
- 채용행사·공채속보는 병렬 호출해 한 endpoint의 지연이나 장애가 다른 endpoint의
  확인 결과까지 없애지 않으며, 일부 성공은 `partial`로 공개한다.
- 현재 발화에 없는 시·도를 LLM이 상식으로 보완하지 못하게 공식 지역 표현으로 다시 검증한다.
- `성남 거주`처럼 행정 접미사를 생략한 시·군·구 별칭도 거주·나이 답변 문맥에서
  표준 지역으로 변환한다. 임의 부분문자열과 동명이인 별칭은 특정 시·도로 추정하지 않는다.
- 동명이인 시·군·구는 시·도를 확인할 때까지 검색하지 않는다.
- 일반 채팅 UI에는 Markdown 기호와 형식적 답변 머리말을 남기지 않는다.
- 인사·감사·`뭐해?` 같은 짧은 사회적 발화와 취업 고민·일반 조언은 Solar가 최근 대화에
  맞춰 답한다. 키 미설정·호출 실패 때만 짧은 고정 템플릿을 사용한다.
- 첫 인사에서 실제 이력 없이 `다시`, `오랜만`, `지난번`을 만들거나 정책 범위·다음 질문
  안내를 누락하면 1회 재작성 후 고정 인사로 수렴한다.
- 그 밖의 `out_of_scope`는 청년 정책 외 다른 분야에 답변하기 어렵고 찾고 싶은
  청년 정책·지원 정보를 말해 달라고 안내한다.
- 범위 밖 분류는 LLM이 수행하지만 최종 응답은 고정 범위 안내이며, 사용자 주제나 특정
  전문 분야명을 반복 열거하거나 관련 없는 프로그램을 제안하지 않는다.
- 최초 검색 응답은 `카드` 안내를 포함하고 후보 제목·URL을 포함하지 않는지 검증한다.
  최대 한 번 LLM으로 다시 작성하며 두 번째 실패는 검증된 카드를 유지한 채 결정론적 요약으로 수렴한다.
- 직전 카드 후속 질문은 별도 allowlist snapshot 안의 후보 제목과 공식 URL을 근거로 검증한다.
- 직전 카드 LLM 설명이 두 번 실패하면 snapshot의 공식 값을 결정론적으로 조립하고,
  snapshot이 없는 번호 참조는 새 정책을 만들지 않고 재검색을 요청한다.
- 검색 없는 `direct_response`도 `verify_answer`를 우회하지 않는다. 검증 실패 응답은
  `validation_fatal` 안전 문구로 한 번 수렴한 뒤 다시 검증한다.
- 민감 식별정보는 브라우저 전송 전과 백엔드 그래프 실행 전 두 단계에서 차단하고, 차단 요청은 LLM·외부 API·Langfuse에 전달하지 않는다.
- Supabase 메시지·프로필·미완료 요청과 브라우저 표시 기록에는 민감정보 원문 대신 삭제 표식만 저장한다.
- 외부 API 장애는 `unavailable`, 정상 무결과는 `no_match`로 보존해 서로 다른 결정론적 안내로 처리한다.
- 부족한 조건을 물을 때 원래 요청과 검색어를 `pending_request`로 보존한다.
- 포괄 청년정책 문의는 공식 5개 분야를 묻고 일자리를 기본값으로 추정하지 않는다.
- 취업 상태는 일자리 정책에서만 필수로 묻고 다른 청년정책 분야에는 강제하지 않는다.
- Supabase에는 최근 8개 메시지, 구조화 프로필, 미완료 요청과 allowlist된 직전 후보
  최대 3건만 문맥으로 불러온다.
- 실제 DB에 `last_presented_candidates` 컬럼이 아직 없을 때는 기존 `pending_request`
  JSONB 예약 키에 동일 snapshot을 임시 저장해 컨테이너 재시작 후 후속 질문도 보존한다.
- 검증을 통과한 `success`/`partial` 검색 턴만 추천 카드와 직전 후보 snapshot을
  갱신한다. 실제 조회한 새 검색이 후보를 제시하지 못하면 오래된 번호 참조를 막기
  위해 snapshot을 비우며, 일반 응답과 조건 질문은 기존 snapshot을 보존한다.
- 브라우저 표시 기록은 `policy-compass.chat-state.v1`에 최근 채팅 20개·채팅별 메시지 50개까지만 저장하고 민감정보를 먼저 마스킹한다.
- React `Chat.id`는 UUID로 만들고 같은 값을 백엔드 `session_id`로 재사용해 새로고침 뒤 멀티턴 문맥을 잇는다.
- API는 UUIDv4 형식의 `session_id`만 허용한다. 그래프 실행은 60초 deadline,
  개별 LLM은 8초, 소스는 10초, Repository HTTP는 9초로 제한하고
  인프로세스 limiter는 세션당 분당 20회, IP당 분당 120회를 허용한다.
- 거주 지역과 만 나이만 브라우저 기본 프로필로 분리해 새 채팅에 전달하고, 채팅별 Supabase 프로필을 우선한다.
- 기본 프로필은 다른 기기와 공유하지 않으며 전체 로컬 기록 삭제 시 함께 삭제한다.
- 광범위한 현재 정책 목록을 묻는 `정책을 알려줘`는 추천 검색이고, 특정 정책명의 개념·자격 설명만 explain이다.
- 외부 API가 실패했을 때 빈 결과로 축약하지 않고 실제 무결과와 장애 안내를 구분한다.
- `SUPABASE_KEY`는 RLS를 우회하는 서버용 secret/service_role 키만 사용한다.
- 테스트는 외부 네트워크 없이 통과해야 한다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `app/graph/contracts.py` | Router의 구조화된 출력 계약 |
| `app/graph/profile_contracts.py` | 세션 프로필 allowlist와 `SET/CLEAR/UNCHANGED` 계약 |
| `app/graph/fallbacks.py` | 키워드·정규식 장애 fallback |
| `app/graph/nodes.py` | LangGraph 노드 orchestration |
| `app/graph/edges.py` | SearchOutcome·retry budget 기반 bounded edge 결정 |
| `app/graph/search_contracts.py` | 세 소스 공통 `SearchOutcome` 계약과 guide 제거 adapter |
| `app/graph/evidence.py` | 지역·연령·관련성·채용 유형 결정론적 무점수 게이트 |
| `app/graph/validators.py` | 응답 역할·검색 근거 검증 |
| `app/graph/response_composer.py` | LLM 응답과 결정론적 템플릿 |
| `app/graph/graph.py` | 8개 의미 노드와 bounded feedback edge 조립 |
| `app/graph/state.py` | 턴 상태·retry/rewrite/revision budget 계약 |
| `app/core/privacy.py` | 민감 식별정보 탐지·마스킹·입력 차단 응답 |
| `app/core/session_control.py` | 세션별 lock pool과 인프로세스 sliding-window rate limiter |
| `app/core/administrative_regions.py` | 2026-07-14 현존 시·군·구 300개와 공식 5자리 코드 |
| `app/core/regions.py` | 사용자 지역·법정코드 정규화와 근접 거리 |
| `app/core/relevance.py` | 관심 분야 유사어와 정책 관련성 판정 |
| `app/core/dates.py` | 공고 종료일 상태를 결정론적으로 정규화 |
| `app/repositories/chat_memory.py` | Supabase 세션 단일 경계와 bounded local LRU mirror |
| `app/repositories/youthcenter.py` | 온통청년 API |
| `app/repositories/work24_training.py` | 고용24 훈련 API |
| `app/repositories/work24_recruitment.py` | 고용24 채용 보조 API |
| `app/api/routes/chat.py` | 동기 채팅과 SSE API |
| `app/api/routes/health.py` | 호환 health, process live, 설정 기반 readiness |
| `frontend/src/lib/chatStorage.ts` | 버전이 있는 로컬 채팅 저장·복원, 보존 한도, 민감정보 마스킹 |
| `frontend/src/components/PolicyCard.tsx` | 정책 지역 범위·인접 참고 배지·거리 표시 |
| `data/chat_memory_schema.sql` | 대화 메모리 테이블과 RLS 스키마 |

## 남은 주요 위험

1. UUIDv4 검증은 소유권 경계가 아니다. multi-worker owner binding이 아직 없다.
2. 브라우저 표시 기록 삭제는 구현됐지만 Supabase 서버 로그의 보존 기간·사용자 삭제 API는 아직 없다.
3. 같은 프로세스의 동일 세션은 직렬화되지만 멀티워커 간 owner routing과 DB
   optimistic version이 없어 교차 프로세스 lost update 가능성이 남아 있다.
4. SSE 노드 상태는 실시간으로 표시하지만 실제 LLM token stream은 아니다.
5. 인프로세스 limiter는 멀티워커 전체 쿼터를 공유하지 않는다.
6. 배포 자동화는 성공했지만 외부 `/`, `/docs`와 대표 질문의 수동 회귀 결과는 아직 기록되지 않았다.
7. 전국 시·군·구 코드는 지원하지만 근접 거리는 일부 검증 좌표 외에는 시·도 대표 좌표를 사용하는 근사치다.
8. 행정구역 개편 시 `administrative_regions.py` 스냅샷을 행정표준코드 현존 목록과 다시 비교해야 한다.
9. 새 채팅 기본 프로필은 현재 브라우저에만 저장되므로 로그인 전에는 기기 간 동기화되지 않는다.
10. `/api/ready`는 현재 키/URL 구성 여부를 확인하며 실제 upstream 연결·circuit 상태까지 probe하지 않는다.
11. `SearchOutcome`·게이트의 실 API fixture와 의미 평가 범위가 아직 충분하지 않다.

## 제거된 범위와 역사 기록

- 기업마당 Repository/Tool은 2026-07-14에 live 호출, 16/17개 지역 태그,
  지자체 소재지·이전 조건, 사업자등록 조건과 관심 분야 순위를 검증한 이력이 있다.
  이 파이프라인은 제품 범위 정렬을 위해 2026-07-15 현재 코드에서 제거됐다.
- `app/repositories/policy.py`, `app/repositories/rag.py`, `app/schemas/policy.py`,
  `app/graph/scoring.py`, `/api/policies*`는 과거 구현 이력이며 현재 활성 모듈/API가 아니다.
- 과거의 전체 기준 가중 점수·근거 확인률과 기업마당 인접 지역 계산은 더 이상
  Agent의 추천 판단에 사용하지 않는다.

## 현재 완료 조건

- [x] 8개 의미 노드와 `direct_response` 통합 경로
- [x] LLM 중심 의도·Tool·검색어 계획
- [x] fallback 규칙 모듈 격리
- [x] grounded 응답 컴포저 분리
- [x] Tool 단일 선택
- [x] 구조 개편 후 전체 로컬 Ruff·pytest·프런트 회귀와 production build 통과
- [x] Upstage, 온통청년, 고용24 훈련·활성 채용행사·공채속보 Repository live 검증 이력
- [ ] 활성 외부 API 3종 Agent 전체 경로 QA
- [x] 질문 유형별 SSE 상태 문구와 React UI 연결
- [x] LangGraph 노드 상태 실시간 SSE, 내부 state·검증 전 초안 비노출
- [x] 멀티턴 관심 분야 전환과 원래 검색 요청 재개
- [x] Supabase 대화·프로필·미완료 요청 저장/복원
- [x] `SupabaseChatMemoryRepository` 단일 경계와 recent 8/history·pending·allowlist 후보 snapshot
- [x] Supabase 미설정·장애 시 bounded local LRU mirror
- [x] 같은 프로세스·세션 load→graph→save 직렬화와 UUIDv4 검증
- [x] 그래프 60초·LLM 8초·소스 10초·Repository HTTP 9초 예산과 세션·IP 인프로세스 rate limit
- [x] 새로고침 뒤 채팅 목록·메시지·정책 카드·활성 채팅 복원
- [x] UUID 세션 유지, 전송 전·서버 입력 단계 민감정보 차단, 개별·전체 기록 삭제
- [x] 기존 main CI/CD와 GCE 내부 헬스체크 성공 이력; 현재 변경분 CI/CD는 재검증 필요
- [x] 성남시 지역 호출·정확/전국 우선·인접 지역 참고 결과 회귀 확인
- [x] 만료 신청기간과 지역 범위 회귀 확인
- [x] 전국 현존 시·군·구 300개 코드 복원
- [x] 기업마당·가중 스코어링 제거와 기존 기업마당 프로필/pending 정리
- [x] 검색→일반 대화에서 이전 결과가 답변·카드에 남지 않는 fresh-turn 회귀
- [x] pending `KEEP/RESUME/CANCEL/REPLACE` 회귀
- [x] 창업 질문의 LLM `out_of_scope`, 외부 Tool·기업마당·K-Startup 링크 미사용 회귀
- [x] 동명이인 지역 확인 질문과 멀티턴 검색 재개 확인
- [x] `성남 거주 만 24세` 일괄 보완과 `성남 거주` 후 나이만 재질문하는 회귀 확인
- [x] 인사 LLM 분류·친화 응답·pending 보존 semantic guard 회귀 확인
- [x] 기존 지역·나이를 새 채팅에서 재사용하고 광범위한 주거 정책 요청을 추천 검색으로 처리
- [x] 온통청년 5xx 재시도와 실제 무결과/호출 장애 안내 분리
- [x] `SearchOutcome` 4상태와 guide 후보 제거
- [x] 세 소스 공통 결정론적 무점수 evidence gate
- [x] 시·군·구 검증과 검증 불가능 지역 한정 후보 차단
- [x] 조회 retry·query rewrite·답변 revision/re-verification bounded edge
- [x] `direct_response` 재검증, PARTIAL 공개 경고, 검증 실패 카드·snapshot 차단
- [x] `/api/live`, `/api/ready`, exact CI SHA·digest 배포 계약
- [x] 일반 입력 LLM 분류, 인사 친화 응답, 범위 밖 고정 분야명 제거
- [ ] 배포본 외부 `/`, `/docs`와 API별 대표 질문 수동 QA
