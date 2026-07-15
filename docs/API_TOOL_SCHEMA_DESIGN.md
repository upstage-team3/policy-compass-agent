# API Tool 및 SearchOutcome 계약

최종 갱신: 2026-07-15

## 목적

정책나침반의 세 활성 외부 API를 같은 실패·필터·후보 언어로 다루고, 조회 장애를
정책 후보로 오인하지 않도록 Tool 경계를 정의한다. 실제 기준은
`app/tools/schemas.py`, `app/tools/executor.py`, `app/graph/search_contracts.py`,
`app/graph/evidence.py`다.

## 활성 범위

| request kind | Tool | 데이터 소스 | 사용자 제공 범위 |
| --- | --- | --- | --- |
| `youth_policy` | `YouthPolicySearchTool` | 온통청년 | 청년정책 |
| `training` | `TrainingCourseSearchTool` | 고용24 | 국민내일배움카드 훈련과정 |
| `recruitment` | `RecruitmentInfoTool` | 고용24 | 채용행사·공채속보 보조정보 |

- 검색 요청당 정확히 하나의 Tool만 실행한다.
- 기업마당 Tool과 `PolicyItem`은 제거됐다.
- 창업·사업자 지원 질문은 검색 없이 LLM `out_of_scope`로 처리하며 외부 창업 사이트를
  제품 연동처럼 안내하지 않는다.
- 가중 점수는 없다. 후보 채택은 source별 결정론적 gate로 결정한다.

## 공통 Tool 결과

Tool의 그래프용 메서드는 단순 후보 list가 아니라 `SearchOutcome`을 반환한다.

```python
class SearchStatus(StrEnum):
    SUCCESS = "success"
    NO_MATCH = "no_match"
    UNAVAILABLE = "unavailable"
    PARTIAL = "partial"


class SearchOutcome(BaseModel):
    source: Literal["youth_policy", "training", "recruitment"]
    status: SearchStatus
    items: list[dict]
    requested_filters: dict
    applied_filters: dict
    warnings: list[str]
    retryable: bool
```

### 상태 의미

| status | 의미 | 후보 | 그래프 동작 |
| --- | --- | --- | --- |
| `success` | 정상 조회와 사용 가능한 후보 | 있음 | evidence gate |
| `no_match` | 정상 조회했지만 결과가 없거나 gate 뒤 0건 | 없음 | 허용된 rewrite 1회 또는 무결과 안내 |
| `unavailable` | 키·권한·네트워크·파싱 문제로 정책 유무를 확인하지 못함 | 없음 | retryable이면 조회 총 2회 이내 재시도 |
| `partial` | 후보는 있으나 경고·부분 실패·일부 gate 제외가 있음 | 있음 | 남은 후보로 진행하고 공개 PARTIAL 경고와 warnings 유지 |

Repository가 과거 호환용 guide 레코드를 반환해도 `outcome_from_raw()`가 이를
`warnings/status`로 옮기며 `items`에는 넣지 않는다. 오류 안내를 카드로 렌더링하면
안 된다. `PARTIAL` 답변은 내부 예외를 노출하지 않고 “일부 하위 조회가 완료되지
않았다”는 공개 경고를 답변 앞에 표시한다.

`requested_filters`는 사용자가 요청해 Tool에 전달한 조건이고,
`applied_filters`는 upstream 또는 후처리에 실제 적용한 조건이다. pagination은
필터가 아니므로 기록 대상에서 제외한다.

## 입력 스키마

### 온통청년

```python
class YouthPolicySearchInput(BaseModel):
    region: str | None = None
    age: int | None = None
    employment_status: str | None = None
    support_types: list[str] = []
    interest_fields: list[str] = []
    keywords: str = ""
    page: int = 1
    page_size: int = 10
```

최소 조건:

- 지역
- 만 나이
- 정책 분야
- 일자리 정책일 때만 취업 상태

공식 endpoint는 `https://www.youthcenter.go.kr/go/ythip/getPlcy`이며 인증키는
`apiKeyNm`, 정책명 검색은 `plcyNm`, 지역은 공식 5자리 `zipCd`를 사용한다.

### 고용24 훈련

```python
class TrainingCourseSearchInput(BaseModel):
    desired_job: str | None = None
    training_region: str | None = None
    training_region_code: str | None = None
    training_start_date_from: str | None = None
    training_start_date_to: str | None = None
    keywords: str = ""
    page: int = 1
    page_size: int = 10
```

최소 조건은 관심 직무/키워드와 훈련지역이다. `training_region`은 Repository의
공식 Work24 resolver가 `srchTraArea1` 코드로 바꾸며, 적용한 코드를
`applied_filters.training_region_code`에 기록한다. 결과 주소/지역도 gate에서 다시
확인한다.

### 고용24 채용 보조정보

```python
class RecruitmentInfoSearchInput(BaseModel):
    desired_job: str | None = None
    preferred_work_region: str | None = None
    career_level: str | None = None
    keywords: str = ""
    page: int = 1
    page_size: int = 10
```

현재 Agent가 호출하는 endpoint는 채용행사와 공채속보다. 사용자 직무·지역을 제대로
적용하지 못하는 공채기업정보 endpoint와 이를 다시 켜는 입력 옵션은 계약에서 제거했고,
gate도 `event`, `open_recruitment`만 허용한다.
서비스 문구는 실제 채용공고 전체가 아니라 **채용 보조정보**로 유지한다.

계약에는 upstream 요청이나 결정론적 후처리에서 실제로 적용되는 필드만 둔다. 현재
적용하지 못하는 졸업상태·온라인 여부·고용형태·학력·직종코드는 입력 계약에서 제외해
필터 적용 여부를 오인하지 않도록 한다. `career_level`은 명시적인 `신입` 또는 `인턴`
표현일 때 공채속보 API 파라미터로 전달한다.

## 출력 후보 스키마

### `YouthPolicyItem`

주요 필드:

```text
policy_id, title, organization, region
min_age, max_age, age_restricted
target_summary, support_summary
business_period, business_end_date
application_period, application_method, detail_url
match_scope, distance_km
```

여기서 `business_period`는 청년정책의 **사업 운영 기간** 필드명이다. 제거된
기업마당/사업자 시나리오를 뜻하지 않는다. `0~0세` 또는 연령 제한 없음 표시는
`age_restricted=False`, `min_age/max_age=None`으로 정규화한다.

### `TrainingCourseItem`

주요 필드:

```text
course_id, course_round, title, institution
region, address, start_date, end_date
cost, actual_cost, ncs_code, target, capacity, contact
detail_url, institution_url
```

### `RecruitmentInfoItem`

주요 필드:

```text
item_id, item_type, title, company, region
start_date, end_date, summary, detail_url
```

`item_type=guide`는 호환 adapter 입력으로만 존재할 수 있고 최종
`SearchOutcome.items`에 남으면 안 된다. `company`는 기본 검색에서 제외한다.

## 결정론적 evidence gate

`assess_evidence`는 가중 점수 없이 다음 후보를 제외한다.

| source | gate |
| --- | --- |
| 온통청년 | 사용자 나이가 구조화 min/max 밖, 시·도/시·군·구 불일치, 지역 검증 불가, 구체 질의 관련성 불일치 |
| 고용24 훈련 | 구조화 주소/지역의 시·도/시·군·구 불일치 또는 지역 검증 불가 |
| 고용24 채용 | 허용되지 않은 item type, 구조화 지역의 시·도/시·군·구 불일치 또는 지역 검증 불가 |

gate는 upstream에서 적용한 필터를 다시 기록하고 `before_count`, `after_count`,
`rejection_reasons`를 남긴다. 사용자가 지역을 요청했다면 후보의 구조화 지역이
없거나 해석되지 않는 경우 `region_unverified`로 제외한다. 양쪽에 시·군·구가
있으면 시·도 일치만으로 통과시키지 않고 공식 코드까지 비교한다. 지역 이외의
확인할 수 없는 자격 값은 임의로 적합 또는 부적합으로 추정하지 않는다.

## bounded retry/rewrite

- `unavailable && retryable`: 동일 검색을 한 번 더 실행해 총 2회 이내로 끝낸다.
- `no_match`: 등록된 deterministic rewrite가 있을 때만 최대 1회 보정한다.
- youth policy 구체 질의와 지역·나이·상태 같은 hard condition은 rewrite로 완화하지
  않는다.
- 두 경로가 소진되면 `direct_response`의 장애 또는 무결과 안내로 끝낸다.

## Tool 선택과 최소 조건

| 사용자 의도 | request kind | 최소 질문 |
| --- | --- | --- |
| 청년정책·주거·복지·문화·참여·취업지원 | `youth_policy` | 지역, 나이, 분야; 일자리면 취업 상태 |
| 내일배움카드·국비·직업훈련 | `training` | 직무/키워드, 훈련지역 |
| 채용행사·공채속보·신입 채용 보조 | `recruitment` | 직무 또는 관심 정보, 희망지역 |
| 창업·사업자·소상공인 지원 | 검색 없음 | LLM `out_of_scope`, Tool 미호출 |

pending에는 `required_slots`를 기록한다. 후속 발화가 실제 required slot을 채웠을
때만 `RESUME`, 무관 발화는 `KEEP`, 취소는 `CANCEL`, 새 검색은 `REPLACE`한다.

세션 프로필은 자유 형식 dict를 직접 merge하지 않는다.
`app/graph/profile_contracts.py`의 Pydantic `ProfileState` allowlist로 필드별 변경을
검증하고 다음 의미를 적용한다.

| mutation | 의미 |
| --- | --- |
| `SET` | 사용자가 명시한 유효한 값을 저장 |
| `CLEAR` | 사용자가 해당 조건 삭제를 명시해 기존 값을 제거 |
| `UNCHANGED` | 미언급, 빈 값, 잘못된 값은 기존 값을 유지 |

같은 턴에서 충돌하면 명시적 `CLEAR`가 우선하며, allowlist 밖 필드는 저장하지 않는다.

## 답변 계약

```text
SearchOutcome
→ assess_evidence
→ gate 통과 후보
→ build_answer
→ verify_answer
→ finalize
```

검색 없는 경로도 `direct_response → verify_answer → finalize`를 사용한다.
`direct_response` 검증 실패는 `validation_fatal` 안전 문구로 수렴한 뒤 다시
검증하며, 검증되지 않은 고정 문구도 바로 내보내지 않는다.

- LLM은 후보에 없는 정책명·과정명·기업·금액·날짜·자격·URL을 만들지 않는다.
- 사실 문장은 후보 데이터와 원문 링크를 사용한다.
- 검증 실패 시 같은 후보로 최대 1회 다시 작성하고 반드시 재검증한다.
- 두 번째 실패는 검증되지 않은 답변을 내보내지 않고 안전 종료한다.
- 최종 자격이나 합격 가능성을 단정하지 않는다.
- 추천 카드와 allowlist된 `last_presented_candidates` snapshot은 답변 검증을 통과한
  `success`/`partial` 검색 턴에서만 만든다. 검증 실패 턴은 둘 다 갱신하지 않는다.

## 환경변수

```env
YOUTHCENTER_POLICY_API_KEY=
YOUTHCENTER_POLICY_API_URL=https://www.youthcenter.go.kr/go/ythip/getPlcy
EMPLOYMENT24_TRAINING_API_KEY=
EMPLOYMENT24_TRAINING_API_URL=https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
EMPLOYMENT24_JOB_API_KEY=
EMPLOYMENT24_JOB_EVENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L11.do
EMPLOYMENT24_OPEN_RECRUITMENT_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L21.do
```

기업마당 API key/URL은 활성 설정이 아니다. 실제 비밀값은 문서·테스트 출력·로그에
기록하지 않는다.

## 필수 contract 테스트

1. 정상 빈 응답 → `no_match`
2. 예외/호출 실패 guide → `unavailable`, 후보 0건
3. 후보+경고 → `partial`
4. retryable 장애 → 조회 총 2회 뒤 종료
5. 등록된 rewrite → 1회만 실행, hard filters 유지
6. 연령·지역·관련성·채용 유형 mismatch → 답변/UI 후보에서 제외
7. 시·군·구 mismatch와 지역 검증 불가 → `region_mismatch`/`region_unverified`로 제외
8. `partial` → 공개 경고 포함, 내부 오류 문구와 guide 카드 없음
9. 답변 검증 실패 → 추천 카드와 세션 후보 snapshot 없음
10. `requested_filters`와 `applied_filters`가 trace 가능한 형태로 유지
11. 키 값과 인증 URL query가 응답·로그에 노출되지 않음
