# 정책나침반 통합 구조 이슈·개선 기준

- 작성일: 2026-07-15
- 비교 기준: `docs/CLAUDE_ARCHITECTURE_PEER_REVIEW.md`, 최신 working tree, 실사용 채팅 재현 사례, Codex 코드·테스트 교차 검증
- 문서 목적: Claude 피어 리뷰와 Codex 검증 결과를 하나의 수정 기준으로 합치고, 단편적인 문구 수정이 아닌 시스템 단위의 완료 조건을 정의한다.
- 보존 원칙: 원본 Claude 문서는 수정하지 않는다. 이 문서는 원본을 대체하는 것이 아니라, 현재 코드와 새로 발견된 사용자 문제를 반영한 통합 판단표다.

> 주의: 작성 시점에 구현이 병행 진행 중이다. 아래의 `미해결`, `부분 해결`, `현재 불일치` 표시는 병합 완료 후 전체 테스트와 최신 Langfuse 실험으로 다시 판정해야 한다.

---

## 0. 2026-07-15 적용 결과

이 절은 아래 분석표보다 최신 상태이며, 이번 구조 수정 뒤의 코드·테스트 판정을 기록한다.

### 적용 완료

| 항목 | 현재 구현 | 검증 |
| --- | --- | --- |
| 정상 LLM `SEARCH` 강등 제거 | 휴리스틱 `GENERAL`이 의미상 유효한 LLM 검색을 다시 `RESPOND`로 바꾸지 않는다. 인사와 명시적 범위 밖 요청만 고신뢰 불변식으로 교정한다. | source routing 회귀 테스트 |
| 정보 객체 기준 소스 선택 | 취업·교육이라는 주제가 아니라 정책·제도, 실제 훈련과정, 공채속보·채용행사 중 무엇을 원하는지로 온통청년/고용24를 선택한다. | `test_source_selection.py`, phase-1 routing 회귀 테스트 |
| 교차 소스 1단계 | 한 턴에는 주 소스 하나만 호출하고, 보완 소스는 검색했다고 표현하지 않는 CTA 한 문장으로만 제안한다. | 카드·상태 CTA 회귀 테스트 |
| pending 취소 오판 | `서울이면 됐어`는 지역 슬롯 응답으로 재개하고, 단독 취소 또는 명시적 취소만 `CANCEL`로 처리한다. | source/multiturn 회귀 테스트 |
| 검색 태스크 전환 | `NEW/RESUME/REFINE/REPLACE/FOLLOW_UP/CANCEL` 관계를 상태에 기록한다. 명시적 고용24 전환은 이전 정책 pending을 `REPLACE`한다. | `test_multiturn_search_contracts.py` |
| 소스별 실효 필터 | 온통청년의 거주지역, 훈련지역, 희망 근무지역을 이번 턴의 `effective_filters`로 분리한다. 정책의 지역·분야가 새 Work24 검색에 자동 적용되지 않는다. | 멀티턴 payload 캡처 테스트 |
| 지역 제한 해제 | `지역 상관없이`는 저장된 거주지를 삭제하지 않고 현재 훈련/채용 검색의 지역 모드만 `any`로 바꾼다. | 멀티턴 payload 캡처 테스트 |
| 직전 완료 검색 보존 | 결과가 0건이거나 소스가 unavailable이어도 `last_search_plan`을 별도 JSONB에 저장해 후속 `REFINE`이 검색어와 소스를 유지한다. | local memory·no-match plan 회귀 테스트 |
| 프로필 오염 축소 | 완료된 턴 뒤에는 나이·거주지역·취업상태만 장기 프로필로 저장하고, 정책 분야·희망 직무·request kind는 pending 동안만 유지한다. | API profile persistence 테스트 |
| 근거 3상태 | 명시적 불일치·마감은 제외하고, 연령·지역·경력 근거 부족은 `unverified` 참고 카드로 보존한다. 참고 카드는 추천 가능으로 표시하지 않고 공식 원문 확인을 요구한다. | evidence/API/response 안전성 테스트 |
| 검색 상태 프롬프트 격리 | LLM에는 전체 프로필·대화·원시 warning 대신 실제 적용된 공개 필터와 상태만 전달한다. 내부 제외 건수와 API 키 명칭도 validator가 차단한다. | response safety 회귀 테스트 |
| 카드 단일 표시 책임 | 말풍선은 카드의 제목·URL·세부 내용을 반복하지 않고 검색 의미·카드 수·참고 여부·최종 확인 안내만 제공한다. | grounded response 회귀 테스트 |
| 채용 소스 범위 정직성 | UI와 답변을 `고용24 공채속보·채용행사`로 제한하고 일반 채용공고 전체나 회사명 검색을 지원한다고 말하지 않는다. | prompt/API 회귀 테스트 |
| 설명 실패 복구 | 자유 작문이 수치·URL 검증에 두 번 실패해도 범용 중단문구 대신 비정량 결정론 설명으로 복구한다. | answer verification 회귀 테스트 |
| timeout 정합성 | 기본 예산을 graph turn 60초, LLM 8초, source boundary 10초, repository HTTP 9초로 정렬하고 `4×LLM + 2×source + 8초`보다 작은 설정은 시작 시 거부한다. | `test_timeout_budget.py` |

현재 검증 결과는 다음과 같다.

- 백엔드 전체 자동 테스트: **336 passed**
- Python 정적 검사·포맷 검사·`git diff --check`: 통과
- 프런트 저장소/민감정보 회귀 테스트: **8 passed**
- 프런트 프로덕션 빌드: 통과
- 통합 API Docker 이미지 `policy-compass-agent:latest`: 빌드 통과, 임시 컨테이너 `/api/ready` 응답 `ready` 확인 후 종료

남은 경고 2건은 Starlette와 LangChain의 상위 라이브러리 deprecation 경고다. Docker 빌드 통과는 패키징 검증이며, 실제 외부 API·LLM·Langfuse를 사용하는 브라우저 시나리오와 최신 semantic experiment를 대신하지 않는다.

### 부분 적용 또는 다음 단계

| 항목 | 남은 이유와 다음 작업 |
| --- | --- |
| Supabase fallback 운영 데이터 | 코드에는 온통청년·고용24 훈련·채용 fallback과 3개 ingest 스크립트가 연결됐다. 그러나 현재 연결된 Supabase에는 `youth_policies`, `recruitment_infos`, `recommendation_feedback`, `last_search_plan` 컬럼이 아직 반영되지 않았고 캐시 데이터도 0건이다. `data/supabase_schema.sql` 적용 후 ingest를 실행해야 실제 장애 fallback이 동작한다. |
| 영구 상태 계약의 물리적 분리 | 실행 시에는 `effective_filters`와 `last_search_plan`으로 분리했지만 외부 API 호환을 위해 장기 프로필 필드명은 아직 `region`이다. 다음 스키마 버전에서 `residence_region`으로 명시적으로 이관한다. |
| 전역 deadline의 남은 예산 계산 | 고정 timeout의 상하 관계와 bounded worst case는 맞췄지만 각 노드가 공통 deadline의 잔여 시간을 받는 구조는 아니다. Router+Profile 통합 또는 deadline context 도입 뒤 기본 60초 상한을 다시 낮춘다. |
| 일반 설명 후 지시어 | `나도 받을 수 있어?`를 안정적으로 잇는 `active_subject` 계약은 아직 없다. 특정 카드 snapshot 후속은 지원하지만 일반 설명 주제의 FOLLOW_UP은 별도 상태가 필요하다. |
| 교차 소스 2단계 | 단일 `SearchOutcome`, 단일 카드 그룹, 단일 snapshot 계약을 복수형으로 바꾸기 전에는 자동 두 번째 Tool 호출을 하지 않는다. 사용자 수락 또는 명시적 “둘 다” 요청에서만 최대 2소스를 호출하는 구조가 다음 단계다. |
| 공개 배포 보안 | session owner binding, TTL, 삭제 API, 다중 worker optimistic locking은 미구현이며 완전 공개 배포 blocker로 유지한다. |
| 최신 의미 평가 | 새 회귀 테스트는 통과했지만 최신 working tree로 Langfuse semantic experiment를 다시 실행해야 한다. 이전 93.3% 수치는 현재 구조의 release gate로 사용하지 않는다. |

---

## 1. 통합 결론

현재 8개 노드 LangGraph를 더 크게 만드는 것이 핵심은 아니다. 현재 구조에는 이미 다음 회복 경로가 존재한다.

- 외부 소스 장애의 bounded retry
- 검색어 rewrite 1회
- 답변 검증 실패 후 재생성 1회
- `NO_MATCH`, `UNAVAILABLE`, `PARTIAL` 분리
- 직전 후보 allowlist snapshot
- 세션 lock, rate limit, turn deadline, PII 사전 차단

실사용 문제의 핵심은 노드 개수가 아니라 다음 네 가지 계약의 충돌이다.

1. **LLM 라우팅과 휴리스틱 2차 검증의 충돌**
   - 올바른 LLM `SEARCH` 판단이 키워드 휴리스틱에 의해 `RESPOND/general`로 강등될 수 있다.
2. **영구 프로필과 현재 검색 계획의 혼합**
   - `region` 하나가 거주지, 훈련 지역, 근무 지역을 모두 대표하고, 직전 청년정책 필터가 채용 검색 설명에 재사용된다.
3. **검색 근거의 `일치 / 미확인 / 불일치` 구분 부재**
   - 명시적 불일치와 데이터 부족을 모두 제외로 처리해 실제 후보가 있어도 `NO_MATCH`가 될 수 있다.
4. **한 턴의 전체 시간 예산과 개별 timeout·retry 정책의 모순**
   - 외부 소스 4초, LLM 5초, 전체 20초라는 현재 설정은 여러 번의 순차 LLM 호출과 소스 retry를 동시에 수용하지 못한다.

따라서 우선순위는 **라우팅 신뢰 복구 → 현재 검색 상태 분리 → 근거 3상태화 → 시간 예산 재설계 → 답변 회복 품질 → 교차 소스 확장** 순서가 되어야 한다.

---

## 2. Claude ↔ Codex 교차 검증 판단표

### 2.1 판단 범례

| 판단 | 의미 |
| --- | --- |
| 동의 | 문제 진단과 핵심 수정 방향이 현재 코드에서도 유효함 |
| 부분 동의 | 문제 진단은 맞지만 제안을 그대로 적용하면 새로운 오류나 계약 충돌이 생김 |
| 현재와 불일치 | Claude 스냅샷 이후 구조가 바뀌었거나 이미 대체된 문제 |
| Codex 추가 | Claude 문서에 직접 없지만 실사용 채팅과 현재 상태 계약에서 추가로 확인된 문제 |

### 2.2 이슈별 대조

| 항목 | 통합 판단 | 현재 근거 | 통합 수정 원칙 |
| --- | --- | --- | --- |
| 8노드 bounded-loop 구조 | 동의, 유지 | 검색·rewrite·답변 재생성의 상한이 이미 그래프에 표현됨 | no-op 노드를 늘리지 말고 상태·조건부 edge·노드 내부 span을 보강 |
| #1 semantic guard의 정상 `SEARCH` 강등 | 동의, 미해결 | `non_search_request_misclassified`가 휴리스틱 `GENERAL`을 LLM `SEARCH`보다 우선할 수 있음 | 구조 계약 오류, 명시적 소스, 명시적 범위 밖만 강제. 애매한 의미 판단은 LLM을 유지 |
| #2 `unknown=제외` 게이트 | 부분 동의 | `age_unverified`, `region_unverified`, `career_unverified`가 hard 제외로 사용됨 | unknown을 정상 추천으로 올리지 말고 `verified / unverified reference / mismatch` 3상태로 분리 |
| #3 timeout 모순 | 진단 동의, 수치 처방 불일치 | 실행값 turn 20s, LLM 5s, source 4s. 소스 내부는 10/15/20s | 개별 timeout만 늘리지 말고 global deadline에서 남은 예산을 계산. Router+Profile 통합 또는 전체 turn 상향 중 하나를 먼저 결정 |
| #4 모든 후보 제목·URL 인용 강제 | 현재와 불일치, 검색 답변은 구조 변경됨 | 현재 검색 말풍선은 카드 건수·확인 안내만 제공하고 제목·URL 반복을 오히려 차단함 | 현재 카드 단일 표시 책임을 유지. 검증 실패 최종 fallback은 결정론 카드 요약으로 복구 |
| #5 explain/general 수치 검열 | 부분 동의, 미해결 | 최신 검색 없이 금액·날짜·자격·URL을 차단하는 것은 맞지만 정상 설명도 범용 중단문구로 끝날 수 있음 | 현행·정량 질문은 `SEARCH`; 비정량 개념은 `RESPOND`. 검증 실패는 의도별 복구로 분기 |
| #6 pending 중 `서울이면 됐어` 취소 오판 | 동의, 미해결 | `됐어`가 슬롯 충족 검사보다 먼저 취소로 판정될 수 있음 | 슬롯 데이터가 함께 있으면 `RESUME` 우선. 취소는 짧은 단독 발화로 제한 |
| #7 session owner binding | 동의, 공개 배포 blocker | 임의 UUIDv4 세션을 특정 사용자와 연결하는 서명된 owner 계약이 없음 | 서명 세션 토큰 또는 인증 owner 조건을 load/save/delete에 일관 적용 |
| #8 TTL·세션 삭제 | 동의, 공개 배포 blocker | 보존 만료와 세션 삭제 API가 없음 | TTL, 삭제 API, 피드백 보존 정책, 감사 로그 범위를 함께 정의 |
| #9 새 구조 Langfuse 평가 | 동의, 미해결 | 93.3%는 이전 구조의 smoke baseline으로 현재 품질 근거가 아님 | working tree/commit SHA와 dataset version을 저장하고 semantic 실험을 새로 실행 |
| 4.4 교차 소스 비가시성 | 진단 동의, 자동 대체 검색은 부분 동의 | `SearchOutcome.source`는 하나고 `retrieve`도 한 소스만 호출함 | 1단계는 분류·CTA만. 2단계 자동 handoff는 넓고 애매한 요청 또는 사용자 명시 동의에서만 1회 |
| 일반 대화 LLM 생성 유지 여부 | 현재 제품 결정으로 해소 | 사용자는 인사·감사에 직접 답하고 정책나침반의 도움 범위를 안내하도록 요청함 | LLM-first 대화를 유지하되 인사·범위 위반·LLM 장애는 결정론 fallback |
| 프로필과 현재 검색 필터 혼합 | Codex 추가, P0 | `profile.region`이 3개 소스의 지역으로 재사용되고 검색 상태 LLM에 전체 profile이 전달됨 | 영구 profile, `active_task`, `effective_filters`, `last_search_plan`을 분리 |
| `지역 상관없이` 같은 후속 필터 수정 | Codex 추가, P0 | 현재 CLEAR는 프로필 삭제 표현 중심이고 직전 완료 검색 계획을 충분히 보존하지 않음 | 거주지는 보존하고 현재 채용의 `work_region` 제한만 `any`로 변경한 후 재검색 |
| 명시적 소스 교체 | Codex 추가, P0 | `청년정책 말고 고용24 공고`에서 이전 정책 필터가 활성 검색 설명에 남을 수 있음 | 강한 소스 신호는 `REPLACE`. 이전 태스크 필터를 활성 검색에서 제거 |
| 후속 질문 `나도 받을 수 있어?` | Codex 추가, P1 | 후보 snapshot 지시어는 처리하지만 일반 설명 후 자격 지시어를 이어줄 `active_subject`가 부족 | 직전 주제·응답 근거 유형을 저장. 후보가 없으면 자격 단정 대신 정책명 확인 또는 공식 검색 제안 |
| 원시 warnings·제외 건수의 사용자 노출 | Codex 추가, P1 | 검색 상태 LLM에 전체 profile과 warnings가 전달되어 내부 gate 사유를 자연어로 재생성할 수 있음 | LLM에는 소스 관련 적용 필터와 공개 가능한 상태만 projection. 내부 건수는 telemetry로만 저장 |
| 고용24 채용 범위 표현 | Codex 추가, P0 | 현재 endpoint는 공채속보·채용행사이며 전체 일반 채용공고 조회가 아님 | 응답·UI·문서에 `고용24 공채속보·채용행사 범위`를 명시. 전체 공고는 별도 권한·endpoint 확보 후만 표방 |

---

## 3. 표준 상태 계약

### 3.1 영구 프로필

세션 간 재사용해도 의미가 바뀌지 않는 사용자 사실만 저장한다.

- `age`
- `residence_region`
- `employment_status`
- 사용자가 명시적으로 장기 관심으로 밝힌 분야

`request_kind`, `policy_topic`, `preferred_support_type`, `desired_job`, 일회성 지역 제한은 원칙적으로 현재 태스크나 검색 계획에 속한다. 장기 프로필로 올리려면 명시적 사용자 표현이 필요하다.

### 3.2 현재 태스크

```text
active_task
├─ task_type: NEW | RESUME | REFINE | REPLACE | FOLLOW_UP | CANCEL
├─ request_kind: youth_policy | training | recruitment
├─ response_mode: recommend | explain | eligibility
├─ original_request
├─ search_query
├─ active_subject
└─ source_explicit: bool
```

### 3.3 소스별 실효 필터

```text
effective_filters
├─ youth_policy
│  ├─ residence_region
│  ├─ age
│  └─ policy_topic
├─ training
│  ├─ training_region
│  ├─ training_region_mode: specific | any | online
│  └─ training_keyword
└─ recruitment
   ├─ work_region
   ├─ work_region_mode: specific | any
   ├─ desired_job
   └─ career_level
```

`"지역 상관없이"`는 `residence_region` 삭제가 아니라 현재 소스의 `region_mode=any`다.

### 3.4 직전 완료 검색

```text
last_search_plan
├─ request_kind
├─ search_query
├─ effective_filters
├─ source_status
├─ presented_candidate_ids
└─ completed_at
```

후보가 0건이어도 이 계획은 보존해야 한다. 그래야 `지역 상관없이`, `신입도 포함해줘`, `데이터 말고 클라우드`를 직전 검색의 `REFINE`으로 처리할 수 있다.

### 3.5 근거 3상태

| 상태 | 의미 | 표시 규칙 |
| --- | --- | --- |
| `verified` | 요청 조건과 후보 근거가 명시적으로 일치 | 정상 카드, 단 신청 가능 최종 확인 안내는 유지 |
| `unverified` | 불일치 근거는 없지만 연령·지역·경력 일부를 확인할 수 없음 | 참고 카드, `원문 확인 필요`, 적격·일치 단정 금지 |
| `mismatch` | 명시적 연령·지역·경력 불일치 또는 마감 | 제외, telemetry에 사유·건수 저장 |

원천에 후보가 있고 `unverified`만 있는 경우를 `NO_MATCH`로 표현하면 안 된다. 사용자 응답은 `일치를 확정할 수 있는 결과는 없지만 확인할 참고 후보가 있음`으로 구분해야 한다.

---

## 4. 소스 범위와 overlap 정책

### 4.1 표준 소스 분류

| 사용자 목적 | 기본 소스 | 범위 |
| --- | --- | --- |
| 지원금·수당·정책제도·정책 자격 | 온통청년 | 청년 정책·제도 5개 분야 |
| 실제 수강할 국비·내일배움 훈련과정 | 고용24 훈련 | 훈련기관·과정·기간·상세 페이지 |
| 실제 공채속보·채용행사 | 고용24 채용 보조정보 | 현재 연동된 두 endpoint의 범위만 |

특히 `취업`, `교육`, `직업훈련`은 정책과 실물 과정의 중첩 키워드다. 단어 하나가 아니라 **사용자가 원하는 결과물**로 분류해야 한다.

### 4.2 1단계 — 분류·범위 안내·확인형 handoff

1단계는 새 노드나 복수 검색 계약 없이 운영할 수 있다.

1. Router가 `제도를 원함` / `실제 과정을 원함` / `채용 보조정보를 원함`을 분리한다.
2. 소스가 명시된 발화는 그 소스를 유지한다.
3. 응답에 현재 소스 범위를 간단히 표시한다.
4. 보완 가능한 다른 소스가 있으면 응답 말미에 결정론 CTA 한 문장만 추가한다.
5. 사용자가 수락하면 다음 턴에 이전 조건을 source-specific filter로 projection해 검색한다.

예시:

- 온통청년 교육지원 정책 결과 후: `실제로 수강할 데이터 훈련과정도 고용24에서 찾아드릴까요?`
- 고용24 훈련과정 후: `훈련비·수당과 관련된 청년 지원정책도 따로 찾아드릴까요?`

이 단계의 핵심은 **안내는 자동, 다른 소스 실행은 사용자 선택**이다.

### 4.3 2단계 — bounded alternate-source search

2단계는 1단계 지표와 timeout 구조가 안정된 후에만 도입한다.

허용 조건:

- 사용자가 `정책과 훈련과정 둘 다`처럼 복수 결과를 명시함
- 또는 요청이 넓고 애매하고 Router가 보조 소스 조회를 계획에 명시함
- 또는 1단계 CTA를 사용자가 수락함

금지 조건:

- `고용24에서 찾아줘`, `온통청년 정책만` 같은 명시적 소스 요청
- 남은 turn 예산이 alternate source timeout보다 적음
- 첫 소스가 `UNAVAILABLE`인데 단순 `NO_MATCH`처럼 다른 소스로 숨기려는 경우

상한:

- 주 소스 1회 + 보조 소스 1회
- alternate source rewrite/retry 금지 또는 별도 전체 1회 예산 내에 포함
- 회답에는 소스별 결과를 섞지 말고 구획화

권장 상태:

```text
source_plan
├─ primary_source
├─ alternate_source
├─ alternate_reason
├─ explicit_source
└─ max_source_count: 1 | 2

search_outcomes: list[SearchOutcome]
```

이 구조는 기존 `retrieve → assess_evidence`를 상한 있게 다시 순환시키면 되므로 반드시 새 노드가 필요한 것은 아니다. 다만 현재의 단일 `SearchOutcome` 계약을 복수 결과 저장이 가능하게 확장해야 한다.

---

## 5. 시간 예산 재설계

### 5.1 현재 모순

일반 검색 성공 경로에는 최소 다음 순차 작업이 있다.

1. Router LLM
2. Profile extraction LLM
3. Source search
4. Search response LLM
5. 검증 실패 시 response LLM 재호출

현재 최댓값을 단순 합산하면 `5 + 5 + 4 + 5 = 19초`고, 응답 재생성이 들어가면 24초가 되어 20초 turn deadline을 넘는다. 소스 retry 1회가 추가되면 더 여유가 없다.

또한 외부 저장소 내부 timeout은 온통청년 10초, 고용24 훈련 15초, 채용 20초인데 graph 경계의 source timeout 4초가 먼저 끝난다. 따라서 내부 timeout과 외부 timeout의 의도가 서로 맞지 않는다.

### 5.2 의사결정 선택지

| 선택 | 조건 | 필요 작업 |
| --- | --- | --- |
| 20초 UX 유지 | 응답 대기를 짧게 유지해야 함 | Router+Profile 통합, 소스 호출 축소·병렬화, 남은 예산 기반 retry 생략, 결정론 fallback 즉시 사용 |
| 30~45초로 상향 | 현재 LLM-first 구조와 회복 루프를 유지해야 함 | 진행 상태를 실제로 전송하는 SSE, 소스별 p95 측정, 만료 직전 재시도 중단 |

어느 쪽을 선택하든 모든 단계는 개별 고정 timeout이 아니라 `turn_deadline - now - response_reserve`로 계산한 남은 예산을 사용해야 한다.

### 5.3 필수 지표

- 전체 latency p50/p95/p99
- LLM operation별 latency·timeout·fallback 비율
- source별 latency·`NO_MATCH`·`UNAVAILABLE`·`PARTIAL` 비율
- retry·rewrite·response revision 발생률
- turn deadline에 의한 전체 중단 비율
- 교차 소스 제안률·수락률·전환 후 성공률

---

## 6. P0~P3 우선순위

우선순위는 `사용자 의도를 다른 작업으로 바꾸는가`, `잘못된 적격·공고 판단을 만드는가`, `실제 후보를 없다고 잘못 단정하는가`, `서비스 전체가 자주 중단되는가`를 우선 기준으로 삼는다.

### P0 — 의도·검색·근거 정확성

1. semantic guard의 LLM `SEARCH` 강등 제거
2. 영구 profile / `active_task` / `effective_filters` / `last_search_plan` 분리
3. `REPLACE`, `REFINE`, `FOLLOW_UP` 전이를 명시적으로 구분
4. `residence_region`, `training_region`, `work_region` 분리
5. 근거 `verified / unverified / mismatch` 3상태화
6. 전체 turn 시간 예산과 source·LLM timeout 정렬
7. 고용24 채용 범위를 공채속보·채용행사로 정확히 표시

### P1 — 대화 회복·답변 품질·평가

1. 수치 질문의 `SEARCH` 승격과 비정량 개념 설명 분리
2. validator 실패를 범용 `중단했어요`가 아닌 의도별 fallback으로 복구
3. `나도 받을 수 있어?`, `그거 조건은?`을 위한 `active_subject` 후속 질문 계약
4. pending 슬롯 충족을 취소보다 우선
5. 원시 warnings·gate 제외 건수를 사용자 프롬프트에서 제거
6. 교차 소스 1단계 분류·CTA
7. 새 구조 기준 Langfuse dataset/experiment 재실행
8. 프로필 CLEAR, 필터 override, 소스 교체 시 사용자 확인 문구 정립

### P2 — 상한 있는 소스 확장·성능

1. 교차 소스 2단계 bounded handoff
2. 소스별 HTTP client pooling
3. 온통청년 순차 exact/broad/복수 검색어 호출 축소 또는 병렬화
4. SSE를 완성 문장 재청크가 아닌 실제 상태·토큰 스트리밍으로 전환
5. 지역 equivalence와 행정구역 경계를 자격 gate와 탐색 확장에서 분리

### P3 — 운영 성숙도·최적화

1. multi-worker 대응 DB optimistic version·distributed lock
2. semantic evaluator 자동화와 release gate
3. 평가 실패 시 자동 베이스라인 비교
4. 소스별 캐시·circuit breaker·장애 감지
5. 프롬프트·계약 버전관리

### 공개 배포 독립 blocker

아래 항목은 기능 우선순위와 상관없이 공개 서비스 전 필수다.

- session owner binding
- 보존 TTL과 세션 삭제 API
- Langfuse 전송 전 allowlist redaction과 로그 PII scan
- 최신 release SHA로 실행한 semantic 평가
- multi-worker 배포 시 세션 갱신 충돌 방지

---

## 7. 완료 기준

### 7.1 P0 완료 기준

- 명시적·자연어 검색 발화 배터리에서 LLM이 올바르게 제안한 `SEARCH`의 오차단이 0건이다.
- 인사·감사·명시적 범위 밖 발화는 검색으로 오승격되지 않는다.
- `청년정책 말고 고용24 공고`가 `REPLACE/recruitment`로 전이하고 이전 정책 필터가 적용 필터에 없다.
- `지역 상관없이`가 직전 검색의 검색어·소스를 유지하고 현재 근무지·훈련지 제한만 해제한다.
- 거주지·훈련지·근무지가 서로 다른 소스에 자동 전파되지 않는다.
- 명시적 mismatch와 마감은 100% 제외된다.
- unverified 후보는 정상 적격 카드로 표시되지 않고 `NO_MATCH`와도 구분된다.
- 온라인 훈련과정은 온라인 근거가 있을 때만 지역 제한 예외로 통과한다.
- 정상 검색 경로가 선택한 p95 turn 목표 내에 있고, 각 단계 timeout 합이 turn deadline을 구조적으로 초과하지 않는다.
- 고용24 채용 답변이 일반 채용공고 전체를 조회했다고 표현하지 않는다.

### 7.2 P1 완료 기준

- 검색 성공 말풍선은 카드 제목·URL·상세를 반복하지 않고 건수·간단한 의미·최종 확인 안내만 제공한다.
- 검색 상태 답변에 내부 rejection reason, API 키 이름, trace, 원시 warning, 제외 건수가 노출되지 않는다.
- `NO_MATCH`, `UNAVAILABLE`, `PARTIAL`, `UNVERIFIED_ONLY`가 서로 다른 응답과 telemetry로 표현된다.
- `나도 받을 수 있어?`가 직전 정책·과정을 안전하게 참조하고 근거 없이 적격을 단정하지 않는다.
- 정량·현행 조건 질문은 공식 검색으로 전환되고, 비정량 개념 질문은 근거 없는 수치를 만들지 않고 설명한다.
- `서울이면 됐어`가 pending 지역 슬롯을 충족하며, 단독 `됐어`만 취소로 처리된다.
- 교차 소스 CTA는 답변당 최대 1개고 사용자가 명시한 소스를 바꾸지 않는다.
- 최신 평가 리포트에 commit/working tree SHA, dataset version, 환경, 소스 상태, p95, semantic score가 있다.

### 7.3 2단계 교차 소스 완료 기준

- 명시적 소스 요청은 자동 교차 검색을 0회 수행한다.
- 광범위 요청·복수 요청·CTA 수락에서만 두 번째 소스를 호출한다.
- 한 turn의 소스 호출 수는 최대 2개다.
- primary `UNAVAILABLE`을 alternate `NO_MATCH`나 `SUCCESS`로 숨기지 않고 두 상태를 모두 구획해 알린다.
- 소스별 카드가 섞이지 않고 출처·목적별로 구분된다.
- alternate search가 turn deadline을 초과할 가능성이 있으면 CTA로 대체된다.

### 7.4 공개 배포 완료 기준

- 다른 사용자가 세션 UUID를 알더라도 조회·갱신·삭제할 수 없다.
- 사용자가 자신의 세션과 피드백을 삭제할 수 있다.
- TTL이 실제 DB cleanup 작업과 함께 검증된다.
- Langfuse·앱 로그·외부 API 전송 payload에 금지된 식별자와 프롬프트 원문이 남지 않는다.
- 두 worker가 동일 세션을 동시에 갱신해도 lost update가 없다.

---

## 8. 필수 회귀 시나리오

| ID | 시나리오 | 기대 경로 | 필수 검증 |
| --- | --- | --- | --- |
| R01 | `안녕` | `RESPOND/general` | 인사에 답하고 정책·구직·훈련·채용정보 질문 제안, 범위 거절 문구 금지 |
| R02 | pending 존재 중 `안녕` | `RESPOND/general`, pending `KEEP` | 인사로 pending이 실행·취소되지 않음 |
| R03 | `월세 지원 받으려면?` | `SEARCH/youth_policy` | 정상 LLM `SEARCH` 강등 0건 |
| R04 | `서울 데이터 국비과정 정보좀 줘` | `SEARCH/training` | `RESPOND/general`로 강등되지 않고 키워드·훈련지역 전달 |
| R05 | `지금 채용공고가 있는 회사 있어?` | `SEARCH/recruitment` | 고용24 채용 보조정보 범위 표시 |
| R06 | 청년정책 후 `청년정책 말고 고용24 공고를 원해` | `REPLACE/recruitment` | 이전 `policy_topic`·지원유형이 활성 채용 필터·상태 답변에 없음 |
| R07 | 직전 채용 검색 후 `지역 상관없이 조회해줘` | `REFINE/recruitment` | 검색어는 유지, `work_region_mode=any`, 거주지는 보존, 즉시 재검색 |
| R08 | `금융관련 지원정책 있어?` → `성남 거주 만 24세` | pending `RESUME` | 한 번에 제공한 두 슬롯을 모두 인식하고 지역을 범위 밖으로 오판하지 않음 |
| R09 | pending 지역 질문 후 `서울이면 됐어` | pending `RESUME` | 지역 슬롯 충족이 취소보다 우선 |
| R10 | pending 중 단독 `됐어` | pending `CANCEL` | 명시적 슬롯 데이터가 없을 때만 취소 |
| R11 | 연령제한이 있으나 상·하한이 누락된 정책 | `unverified reference` | `NO_MATCH`나 적격 카드가 아닌 확인 필요 참고 결과 |
| R12 | 서울 요청에 부산 정책 | `mismatch` 제외 | 명시적 불일치 통과 0건 |
| R13 | 부산 요청에 `온라인 과정` | 온라인 근거에 따라 `nationwide` 또는 `unverified` | 단순 문자열만으로 적격·제외 단정 금지 |
| R14 | 서울 요청에 지역 필드가 없는 공채속보 | `unverified reference` | 서울 일치로 표시하지 않고 지역 원문 확인 안내 |
| R15 | 소스가 0건 정상 응답 | `NO_MATCH` | `조회 실패`로 표현하지 않음 |
| R16 | 소스 timeout·권한 제한 | `UNAVAILABLE` | `공고·정책이 없다`로 단정하지 않음 |
| R17 | 한 endpoint만 성공 | `PARTIAL` | 확인된 결과는 제공하고 전체 결과가 아님을 표시 |
| R18 | 일반 국비지원 설명 후 `나도 받을 수 있어?` | `FOLLOW_UP/eligibility` | 정책명·후보가 없으면 확인 질문 또는 공식 검색 제안, 근거 없는 수치·자격 금지 |
| R19 | `국비지원 조건이 따로 있어?` | 현행 자격이면 `SEARCH`, 개념이면 `RESPOND/explain` | 범용 검증 중단문구 대신 의도별 복구 |
| R20 | 검색 성공 + 3개 카드 | `SEARCH → cards` | 말풍선에 제목·URL·상세 반복 없음, 카드 건수·안내만 표시 |
| R21 | 검색 상태 LLM이 `15건 제외`, API 키 이름을 생성 | validator/fallback | 내부 정보를 제거한 사용자 상태 문구로 복구 |
| R22 | 제목·URL·수치를 지어낸 검색 요약 | response retry → deterministic card summary | 재시도가 실패해도 카드 요약으로 복구하고 범용 중단문구로 가지 않음 |
| R23 | `실제 데이터 과정을 찾아줘` | `training` + 1단계 CTA | 훈련 결과 후 지원제도 검색을 선택지로만 제시 |
| R24 | `고용24 훈련만 보여줘` | `training` | 온통청년으로 자동 전환 0회 |
| R25 | `교육비 지원정책과 실제 훈련과정 둘 다` | 소스 2개 상한 검색 | 소스별 결과를 구획하고 총 호출 수 2개 이하 |
| R26 | source 3.5s + Router/Profile/Answer 지연 조합 | turn SLA | 선택한 SLA 내 완료, 남은 예산이 없으면 retry를 안전하게 생략 |
| R27 | 다른 owner의 세션 UUID로 접근 | API 거부 | 조회·갱신·삭제 모두 차단 |
| R28 | 세션 삭제 후 재조회 | 없음 | 메시지·profile·pending·snapshot·피드백 보존 정책에 따라 삭제 |

---

## 9. 검증 실행 순서

1. 라우팅·태스크 전이 단위 테스트
2. profile·effective filter·last search plan 다중 턴 테스트
3. evidence 3상태·카드 표시·snapshot 안전성 테스트
4. timeout·retry·rewrite 장애 주입 테스트
5. LLM 환각·검증 실패·fallback 테스트
6. 로컬 전체 `pytest`
7. Docker build·ready·실제 채팅 브라우저 회귀
8. 합성 데이터로 Langfuse semantic experiment
9. 합의된 개인정보 범위 내의 제한 베타 실사용 평가

각 검증 결과는 다음을 함께 저장한다.

- commit SHA 또는 working tree hash
- 실행 시각·환경·모델·프롬프트 버전
- 시나리오 버전
- 소스 정상/장애 여부
- 정확도·검색 근거·답변 grounding·다중 턴 성공률
- latency p50/p95/p99
- retry·rewrite·revision·abstention 비율

---

## 10. 배포 판단

### 내부 시연

P0 완료 기준과 R01~R22를 통과하면 가능하다. 단, 고용24 채용 소스 범위를 시연자에게 사전 고지한다.

### 제한 베타

P0·P1, 최신 Langfuse semantic 평가, 소스 상태 공지, 기본 보존 정책을 통과한 후 진행한다.

### 완전 공개

기능 평가와 별개로 session owner binding, TTL/삭제, multi-worker 충돌 방지, Langfuse redaction, 최신 release semantic 평가가 모두 필요하다. 이 조건 중 하나라도 빠지면 답변 품질이 높더라도 완전 공개 배포는 보류한다.
