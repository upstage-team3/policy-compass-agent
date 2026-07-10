# API Tool Schema 설계

작성일: 2026-07-10

## 목적

취업 대상 청년 MVP에서 Agent가 외부 API를 안정적으로 호출하기 위한 입력/출력 계약을 정리한다.

2026-07-10 revised 기준 핵심 MVP는 청년지원사업 및 취업 관련 청년 정보 챗봇이다.
현재 연결 가능한 API 상태를 기준으로, 오늘 구현 우선순위는 다음과 같다.

| 우선순위 | API | 환경변수 | 현재 기준 | 역할 |
| --- | --- | --- | --- | --- |
| 1 | 고용24 국민내일배움카드 훈련과정 API | `EMPLOYMENT24_TRAINING_API_KEY`, `EMPLOYMENT24_TRAINING_API_URL` | 키 설정, 연결 가능 | 직무별 교육/훈련과정 추천 |
| 2 | 고용24 채용정보 API | `EMPLOYMENT24_JOB_API_KEY`, `EMPLOYMENT24_JOB_API_URL` | 키 설정, 개인키 제한 있음 | 채용행사/공채속보/공채기업정보 제공, 직접 공고는 탐색 가이드 |
| 3 | 온통청년 청년정책 API | `YOUTHCENTER_POLICY_API_KEY`, `YOUTHCENTER_POLICY_API_URL` | 키 미설정 | 청년 취업정책, 지원금, 일경험, 상담, 공간 정보 스키마 준비. 키가 없으면 빈 결과 |

기업마당 API는 오늘 핵심 MVP에서 제외하고, 창업/사업자 질문이 들어올 때만 보조 데이터로 사용한다.

## API 요청 기준

## 실제 호출 확인 결과

확인일: 2026-07-10

온통청년은 인증키 미입력 상태라 호출하지 않았다. 고용24 국민내일배움카드 훈련과정 API와 고용24 채용정보 API는 `.env`의 인증키와 URL로 직접 호출해 확인했다.

### 고용24 국민내일배움카드 훈련과정 API

호출 결과:

- HTTP 200
- 응답 형식: `application/xml;charset=UTF-8`
- 루트 노드: `HRDNet`
- 상위 노드: `pageNum`, `pageSize`, `scn_cnt`, `srchList`
- 반복 레코드 노드: `scn_list`
- 기본 조건으로 5건 요청 시 정상 데이터 반환
- 전체 검색 건수는 `scn_cnt`로 확인 가능

확인된 주요 필드:

| XML 필드 | 의미 | 내부 매핑 후보 |
| --- | --- | --- |
| `trprId` | 훈련과정 ID | `course_id` |
| `trprDegr` | 훈련 회차 | `course_round` |
| `title` | 훈련과정명 | `title` |
| `subTitle` | 훈련기관명 | `institution` |
| `address` | 훈련지역/주소 | `region`, `address` |
| `traStartDate` | 훈련 시작일 | `start_date` |
| `traEndDate` | 훈련 종료일 | `end_date` |
| `courseMan` | 수강 비용 | `cost` |
| `realMan` | 실제 훈련비/비용 관련 값 | `actual_cost` |
| `regCourseMan` | 정부지원/등록 비용 관련 값 | `subsidy_or_registered_cost` |
| `ncsCd` | NCS 코드 | `ncs_code` |
| `trainTarget` | 훈련 대상 | `target` |
| `trainTargetCd` | 훈련 대상 코드 | `target_code` |
| `yardMan` | 정원 | `capacity` |
| `telNo` | 기관 전화번호 | `contact` |
| `titleLink` | 과정 상세 URL | `detail_url` |
| `subTitleLink` | 훈련기관 상세 URL | `institution_url` |
| `trngAreaCd` | 훈련지역 코드 | `training_region_code` |
| `stdgScor` | 만족도/평점 계열 값 | `score` |
| `wkendSe` | 주말/주중 구분 코드 | `schedule_type_code` |

MVP에서 우선 사용할 필드:

- `trprId`
- `title`
- `subTitle`
- `address`
- `traStartDate`
- `traEndDate`
- `courseMan`
- `ncsCd`
- `trainTarget`
- `yardMan`
- `titleLink`

### 고용24 채용정보 API

호출 결과:

- HTTP 200
- 응답 형식: `application/xml;charset=UTF-8`
- 루트 노드: `GO24`
- 응답 내용: `개인회원은 사용할 수 없는 OPEN-API입니다.`

개인회원 API 권한:

| 구분 | 개인회원 키 사용 가능 여부 | MVP 활용 |
| --- | --- | --- |
| 채용행사 API | 가능 | 취업박람회, 채용설명회, 박람회 일정 안내 |
| 공채속보 API | 가능 | 신입/공채 중심 채용 소식 안내 |
| 공채기업정보 API | 가능 | 공채 기업 개요와 기업 정보 보조 |
| 채용정보목록 API | 불가 | 직접 채용공고 목록 조회 불가 |
| 채용정보상세 API | 불가 | 특정 채용공고 상세 조회 불가 |

현재 판단:

- URL과 인증키 형식은 호출 가능한 상태다.
- 개인회원 키로는 채용행사, 공채속보, 공채기업정보 API만 사용할 수 있다.
- 채용정보목록, 채용정보상세 API는 개인회원 키로 사용할 수 없다.
- 따라서 직접 채용공고 추천은 MVP 핵심 데이터가 아니라 보조/확장 데이터로 둔다.
- 권한 제한 응답이 오면 실패로 처리하지 않고 채용 탐색 가이드로 폴백한다.

다음 확인 작업:

1. 개인키로 사용 가능한 채용행사/공채속보/공채기업정보 API의 요청 URL과 파라미터를 확인한다.
2. 채용정보목록/상세가 꼭 필요하면 기업회원 또는 별도 권한 신청 가능성을 확인한다.
3. 권한 조정 전까지는 직접 채용공고 조회를 optional로 두고 fallback 문구를 준비한다.
4. 공채속보와 채용행사 데이터는 “채용 탐색 보조 정보”로 활용한다.

### 1. 온통청년 청년정책 API

요청 URL:

```text
https://www.youthcenter.go.kr/opi/youthPlcyList.do
```

주요 파라미터:

| 파라미터 | 설명 | 내부 매핑 |
| --- | --- | --- |
| `openApiVlak` | 인증키 | `YOUTHCENTER_POLICY_API_KEY` |
| `pageIndex` | 페이지 번호 | `page` |
| `display` | 페이지 크기 | `page_size` |
| `query` | 검색어 | `keywords` |
| `bizTycdSel` | 사업 유형 코드 | `support_type_codes` |
| `srchPolyBizSecd` | 정책 분야 코드 | `policy_category_codes` |
| `keyword` | 키워드 | `keywords`, `desired_job`, `interest_fields` |

가져와야 할 정보:

- 정책명
- 주관기관/운영기관
- 지원 대상
- 연령 조건
- 지역 조건
- 취업 상태 조건
- 졸업/재학 조건
- 지원 내용
- 신청 기간
- 신청 방법
- 상세/원문 URL
- 문의처

### 2. 고용24 국민내일배움카드 훈련과정 API

요청 URL:

```text
https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
```

스크린샷 기준 사용 예시:

```text
?authKey=[인증키]&returnType=XML&outType=1&pageNum=1&pageSize=20&srchTraStDt=20141001&srchTraEndDt=20141231&sort=ASC&sortCol=2
```

선택 조건 추가 예시:

```text
&srchTraArea1=[훈련지역 대분류]
```

주요 파라미터:

| 파라미터 | 설명 | 내부 매핑 |
| --- | --- | --- |
| `authKey` | 인증키 | `EMPLOYMENT24_TRAINING_API_KEY` |
| `returnType` | 응답 형식 | 기본 `XML` |
| `outType` | 출력 유형 | 기본 `1` |
| `pageNum` | 페이지 번호 | `page` |
| `pageSize` | 페이지 크기 | `page_size` |
| `srchTraStDt` | 훈련 시작일 검색 시작 | `training_start_date_from` |
| `srchTraEndDt` | 훈련 시작일 검색 종료 | `training_start_date_to` |
| `srchTraArea1` | 훈련지역 대분류 | `training_region_code` |
| `sort` | 정렬 방향 | 기본 `ASC` |
| `sortCol` | 정렬 컬럼 | 기본 `2` |

가져와야 할 정보:

- 훈련과정명
- 훈련기관명
- 훈련지역
- 훈련 시작일/종료일
- 훈련 시간
- 수강 비용
- 자비부담액
- NCS/직무 분야
- 온라인/오프라인 여부
- 상세 URL
- 모집 상태

주의:

- 요청 파라미터 입력 시 대괄호 `[]`는 제외한다.
- 날짜는 `YYYYMMDD` 형식으로 보낸다.
- 사용자가 날짜를 말하지 않으면 기본 검색 기간은 `오늘부터 6개월`로 둔다.
- 사용자가 지역을 말하지 않으면 MVP에서는 지역을 한 번 되묻는 흐름을 권장한다.

### 3. 고용24 채용정보 API

요청 URL:

```text
https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
```

스크린샷 기준 기본 검색 예시:

```text
?authKey=[인증키]&callTp=L&returnType=XML&startPage=1&display=10
```

다중 검색 예시:

```text
&occupation=[직종코드1]|[직종코드2]
```

주요 파라미터:

| 파라미터 | 설명 | 내부 매핑 |
| --- | --- | --- |
| `authKey` | 인증키 | `EMPLOYMENT24_JOB_API_KEY` |
| `callTp` | 호출 타입 | 목록 조회 기본 `L` |
| `returnType` | 응답 형식 | 기본 `XML` |
| `startPage` | 페이지 번호 | `page` |
| `display` | 페이지 크기 | `page_size` |
| `occupation` | 직종 코드 목록 | `occupation_codes` |

가져와야 할 정보:

- 채용공고 ID
- 회사명
- 공고 제목
- 직무/직종
- 근무지역
- 고용형태
- 경력 요건
- 학력 요건
- 급여 조건
- 마감일
- 등록일
- 원문 URL
- 청년/신입/인턴 관련 여부

개인회원 키 기준으로 실제 MVP에서 우선 가져올 수 있는 채용 관련 정보:

- 채용행사명
- 행사 지역
- 행사 기간
- 행사 주최/운영기관
- 행사 상세 URL
- 공채속보 제목
- 기업명
- 공채 접수기간
- 공채 관련 URL
- 공채기업 기본 정보

주의:

- 요청 파라미터 입력 시 대괄호 `[]`는 제외한다.
- `occupation`은 여러 직종코드를 `|`로 연결한다.
- 사용자가 직무명을 말하면 내부 직종코드 매핑 테이블로 변환해야 한다.
- 직종코드가 없으면 키워드 기반 검색 또는 직무 재질문으로 폴백한다.

## 사용자에게 필요한 사전정보

### 공통 프로필

| 정보 | 필수 여부 | 이유 |
| --- | --- | --- |
| 거주지역 | 필수 | 청년정책 지역 조건, 훈련지역, 근무지역 필터링 |
| 나이 | 권장 | 청년정책 연령 조건 비교 |
| 취업 상태 | 필수 | 미취업/재직/학생/졸업예정자에 따라 정책이 달라짐 |
| 졸업 상태 | 권장 | 졸업예정/졸업 후 기간 조건 확인 |
| 관심 직무 | 필수에 가까움 | 훈련과정과 채용공고 검색의 핵심 조건 |
| 희망 근무지역 | 권장 | 채용정보 필터링 |
| 희망 지원 유형 | 권장 | 지원금/상담/교육/일경험/채용 중 무엇을 원하는지 판단 |

민감정보는 받지 않는다. 주민등록번호, 계좌번호, 상세 주소, 고용보험 피보험자 번호, 가족관계 정보는 요청하지 않고 공식 신청 단계에서 확인하도록 안내한다.

## Agent 도구 선택 규칙

| 사용자 의도 | 호출 도구 |
| --- | --- |
| “지원금”, “청년정책”, “취업지원”, “일경험”, “상담” | `YouthPolicySearchTool` |
| “내일배움카드”, “교육”, “훈련”, “강의”, “국비지원” | `TrainingCourseSearchTool` |
| “채용”, “공고”, “인턴”, “신입”, “일자리” | `RecruitmentInfoTool`, 개인키 허용 범위 내 채용행사/공채속보/공채기업정보 제공, 직접 공고는 탐색 가이드 |
| “취업 준비 뭐부터 해야 해?” | 공통 프로필 확인 후 정책/훈련 Tool을 우선 호출, 채용 Tool은 가능할 때만 호출 |
| “창업”, “사업자”, “소상공인” | 기업마당 보조 Tool |

## Tool 입력 스키마 초안

```python
class YouthPolicySearchInput(BaseModel):
    region: str | None = None
    age: int | None = None
    employment_status: str | None = None
    graduation_status: str | None = None
    support_types: list[str] = []
    interest_fields: list[str] = []
    keywords: str = ""
    page: int = 1
    page_size: int = 10


class TrainingCourseSearchInput(BaseModel):
    desired_job: str | None = None
    training_region: str | None = None
    training_region_code: str | None = None
    training_start_date_from: str | None = None
    training_start_date_to: str | None = None
    online_available: bool | None = None
    keywords: str = ""
    page: int = 1
    page_size: int = 20


class RecruitmentInfoSearchInput(BaseModel):
    desired_job: str | None = None
    occupation_codes: list[str] = []
    preferred_work_region: str | None = None
    employment_type: str | None = None
    career_level: str | None = None
    education_level: str | None = None
    include_events: bool = True
    include_open_recruitments: bool = True
    include_company_info: bool = True
    keywords: str = ""
    page: int = 1
    page_size: int = 10
```

## 최소 호출 조건과 되묻기

| Tool | 최소 조건 | 부족할 때 질문 |
| --- | --- | --- |
| `YouthPolicySearchTool` | 지역, 취업 상태, 검색 의도 | “어느 지역 기준으로 찾아볼까요?”, “현재 재학/졸업예정/미취업/재직 중 어디에 가까우세요?” |
| `TrainingCourseSearchTool` | 관심 직무 또는 키워드, 훈련지역 | “어떤 직무 훈련을 찾고 계세요?”, “훈련은 어느 지역 기준으로 볼까요?” |
| `RecruitmentInfoTool` | 관심 직무, 관심 기업, 희망 지역 중 하나 | “채용행사, 공채속보, 기업정보 중 어떤 정보를 먼저 볼까요?”, “관심 직무나 기업이 있나요?” |

## 출력 스키마 초안

```python
class YouthPolicyItem(BaseModel):
    source: str = "youthcenter"
    policy_id: str
    title: str
    organization: str | None = None
    region: str | None = None
    target_summary: str | None = None
    support_summary: str | None = None
    application_period: str | None = None
    application_method: str | None = None
    detail_url: str | None = None
    raw: dict = {}


class TrainingCourseItem(BaseModel):
    source: str = "work24_training"
    course_id: str
    title: str
    institution: str | None = None
    region: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    cost: str | None = None
    self_payment: str | None = None
    ncs_field: str | None = None
    detail_url: str | None = None
    raw: dict = {}


class RecruitmentInfoItem(BaseModel):
    source: str = "work24_recruitment"
    item_id: str
    item_type: str  # event | open_recruitment | company
    title: str
    company: str | None = None
    region: str | None = None
    start_date: str | None = None
    end_date: str | None = None
    summary: str | None = None
    detail_url: str | None = None
    raw: dict = {}
```

## 답변 조합 방식

사용자가 “취업 준비 지원”처럼 넓게 질문하면 다음 순서로 답한다.

1. 조건이 부족하면 지역, 취업/졸업 상태, 관심 직무를 먼저 묻는다.
2. 온통청년에서 취업정책 2~3개를 가져온다.
3. 내일배움카드 API에서 관심 직무 훈련과정 2~3개를 가져온다.
4. 채용 관련 정보는 개인키로 가능한 채용행사, 공채속보, 공채기업정보를 우선 가져온다.
5. 직접 채용공고 목록/상세가 필요한 경우에는 권한 제한을 안내하고 관심 직무 기준 채용 탐색 키워드, 고용24 검색 조건, 확인할 공고 조건을 안내한다.
6. 답변은 “정책 → 훈련 → 채용행사/공채속보 또는 채용 탐색 가이드 → 확인 필요 조건” 순서로 정리한다.

## 구현 순서

1. [x] `app/tools/schemas.py`에 3개 입력 스키마를 추가한다.
2. [x] 정책, 훈련과정, 채용행사/공채속보/공채기업정보 출력 스키마를 추가한다.
3. [x] `app/repositories/youthcenter.py`를 추가해 온통청년 XML 응답을 정규화한다.
4. [x] `app/repositories/work24_training.py`를 추가해 훈련과정 XML 응답을 정규화한다.
5. [x] `app/repositories/work24_recruitment.py`를 추가해 고용24 채용정보 응답을 정규화하고 권한 제한을 감지한다.
6. [x] 채용정보목록/상세 호출은 권한 제한 응답을 감지해 fallback reason을 반환한다.
7. [x] `app/tools/executor.py`에 청년정책/훈련/채용 보조 Tool을 추가한다.
8. [x] Missing Slot Node가 Tool 호출 전 필수 조건을 확인하도록 보강한다.
9. [x] Response Node가 정책/훈련/채용 탐색 가이드를 한 답변 안에서 구분해 설명하도록 수정한다.

현재 남은 구현:

- [ ] 고용24 채용행사/공채속보/공채기업정보 세부 endpoint 확인 및 추가
- [ ] 온통청년 키 발급 후 실제 호출 결과 검증
- [ ] 새 Tool 결과의 SSE/UI 수동 QA

## MVP 주의사항

- API 응답 필드가 비어 있을 수 있으므로 모든 필드는 optional로 정규화한다.
- 원문 URL이 없으면 해당 항목은 “원문 링크 확인 필요”로 표시한다.
- LLM은 정책명, 훈련과정명, 회사명, 마감일을 생성하지 않는다.
- API 결과가 없으면 조건을 넓히는 질문을 한다.
- 채용정보목록/상세 API가 권한 제한 응답을 주면 “현재 개인회원 API 권한으로 직접 공고 목록/상세 조회는 어렵다”고 설명하고 채용행사/공채속보/탐색 가이드로 대체한다.
- 최종 신청 가능 여부나 합격 가능성을 단정하지 않는다.
