# API 및 배포 메모

## 실행 기준

현재 프로젝트는 FastAPI 단일 서버 구조다.

```bash
uv sync
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

로컬 확인:

```text
http://localhost:8000/
http://localhost:8000/docs
http://localhost:8000/health
```

## 주요 API

| Method | Endpoint | 설명 |
| --- | --- | --- |
| GET | `/` | 정적 채팅 데모 UI |
| GET | `/health` | 기존 호환 헬스체크 |
| GET | `/api/health` | 현재 구조의 헬스체크 |
| POST | `/api/chat` | 동기 채팅 API |
| POST | `/api/chat/stream` | SSE 스트리밍 채팅 API |
| GET | `/api/policies` | 정책 목록 조회 |
| GET | `/api/policies/{policy_id}` | 정책 상세 조회 |
| POST | `/api/policies/search` | 키워드 기반 RAG-lite 정책 검색 |
| POST | `/api/v1/chat/sync` | 기존 로컬 데모 호환 채팅 API |
| POST | `/api/v1/chat` | 기존 로컬 데모 호환 스트리밍 API |

## 채팅 요청 예시

```bash
curl -X POST http://localhost:8000/api/chat \
  -H "Content-Type: application/json" \
  -d "{\"session_id\":\"demo-session-001\",\"message\":\"서울 사는 만 28세 미취업자인데 구직지원금 받을 수 있어?\"}"
```

`session_id`는 같은 대화 안에서 프로필을 누적하는 데 사용한다.

## MVP 외부 API 우선순위

2026-07-10 revised 기준 MVP 핵심 대상은 대학생, 졸업예정자, 사회초년생, 미취업 청년이다.
서비스 핵심은 청년지원사업 및 취업 관련 청년 정보 챗봇이며, 현재 연결 가능한 API를 기준으로 다음 순서로 연동한다.

| 우선순위 | API | 역할 | 상태 |
| --- | --- | --- | --- |
| 1 | 고용24 국민내일배움카드 훈련과정 API | 취업 준비에 필요한 교육/훈련과정 조회 | 키 설정, 연결 가능 |
| 2 | 고용24 채용정보 API | 채용행사, 공채속보, 공채기업정보 또는 채용 탐색 가이드 | 키 설정, 개인키 제한 있음 |
| 3 | 온통청년 Open API | 청년 취업정책, 청년공간, 청년콘텐츠 조회 | 키 미설정 시 빈 결과 |
| 4 | 기업마당 지원사업정보 API | 창업/사업자/중소기업 지원사업 보조 조회 | 키 설정, MVP 핵심에서 제외 |

취업 MVP에서는 고용24 국민내일배움카드 훈련과정을 우선 실데이터로 연결하고, 온통청년은 키 발급 전까지 내부 대체 데이터로 보완하지 않고 빈 결과로 처리한다. 정규화 스키마와 normalizer만 유지한다.
고용24 채용정보 API는 개인 신청 키에서 채용행사, 공채속보, 공채기업정보만 사용할 수 있다.
채용정보목록과 채용정보상세 API는 개인회원 키로 사용할 수 없으므로,
직접 공고 조회가 필요할 때는 채용 탐색 가이드로 폴백한다.
기업마당은 오늘 핵심 청년 취업 MVP에서는 제외하고, 창업 또는 사업자 관련 질문이 들어올 때만 보조 데이터 소스로 사용한다.
Tool 입력/출력 스키마와 사용자에게 먼저 물어볼 조건은 `docs/API_TOOL_SCHEMA_DESIGN.md`를 기준으로 구현한다.

Day3 revised 구현 상태:

- `YouthPolicySearchInput`, `TrainingCourseSearchInput`, `RecruitmentInfoSearchInput` 스키마 추가
- 고용24 훈련과정 XML normalizer와 탐색 fallback 추가
- 고용24 채용정보 개인회원 권한 제한 감지 및 채용 탐색 가이드 fallback 추가
- 온통청년 키 미설정 시 빈 결과 반환
- 검증 기준: `uv run python -m pytest` 37개 통과

## 온통청년 Open API

문서:

```text
https://www.youthcenter.go.kr/cmnFooter/openapiIntro/oaiDoc
https://www.youthcenter.go.kr/cmnFooter/openapiIntro/oaiGuide
```

신청 방식:

- 온통청년 회원가입
- 로그인 후 마이페이지에서 Open API 인증키 신청
- 담당자 승인 후 인증키 발급

주요 특징:

- HTTPS 기반 API
- 응답 형식은 XML
- 청년정책, 청년공간, 청년콘텐츠 정보를 제공
- 청년정책 목록 예시 URL: `https://www.youthcenter.go.kr/opi/youthPlcyList.do`

MVP 활용:

- 청년 취업 지원정책 검색
- 지역, 연령, 취업 상태, 졸업 여부, 키워드 기반 필터링
- 추천 답변의 정책명, 지원 대상, 신청 기간, 신청 방법, 원문 링크 근거 제공

예상 환경변수:

```env
YOUTHCENTER_POLICY_API_KEY=
YOUTHCENTER_POLICY_API_URL=https://www.youthcenter.go.kr/opi/youthPlcyList.do
```

## 고용24/HRD-Net 국민내일배움카드 훈련과정 API

MVP 활용:

- 국민내일배움카드로 수강 가능한 훈련과정 조회
- 취업 준비 청년에게 직무별 교육/훈련과정 추천
- 채용공고와 연결해 "필요 역량 -> 추천 훈련과정 -> 지원 가능한 공고" 흐름 구성

예상 환경변수:

```env
EMPLOYMENT24_TRAINING_API_KEY=
EMPLOYMENT24_TRAINING_API_URL=https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
```

연동 시 확인할 것:

- 응답 형식(JSON/XML), 필수 파라미터, 호출 제한 확인
- 과정명, 훈련기관, 지역, 훈련기간, 자비부담액, 상세 URL 필드 매핑

## 고용24 채용정보 API

개인회원 키 권한:

| API 항목 | 개인회원 키 사용 |
| --- | --- |
| 채용행사 API | 가능 |
| 공채속보 API | 가능 |
| 공채기업정보 API | 가능 |
| 채용정보목록 API | 불가 |
| 채용정보상세 API | 불가 |

MVP 활용:

- 채용행사, 공채속보, 공채기업정보 조회
- 신입/공채 중심 채용 소식 보조
- 채용정보목록/상세 제한 시 "정책 + 훈련과정 + 채용 탐색 가이드" 형태로 폴백

예상 환경변수:

```env
EMPLOYMENT24_JOB_API_KEY=
EMPLOYMENT24_JOB_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
```

연동 시 확인할 것:

- 채용행사/공채속보/공채기업정보 API의 요청 URL과 파라미터 확인
- 기업회원/기관회원 키가 필요한 API인지 확인
- 응답 형식(JSON/XML), 필수 파라미터, 호출 제한 확인
- 채용공고 원문 URL, 회사명, 직무명, 지역, 마감일 필드 매핑

## 기업마당 지원사업정보 API

공식 URL:

```text
https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
```

필수 파라미터:

```text
crtfcKey
```

주요 선택 파라미터:

```text
dataType=json
searchCnt
searchLclasId
hashtags
pageUnit
pageIndex
```

분야 코드:

| 코드 | 분야 |
| --- | --- |
| 01 | 금융 |
| 02 | 기술 |
| 03 | 인력 |
| 04 | 수출 |
| 05 | 내수 |
| 06 | 창업 |
| 07 | 경영 |
| 09 | 기타 |

현재 코드는 기업마당 API 호출 결과를 `PolicyItem` 스키마로 1차 정규화한다. 호출 실패, 키 누락, 응답 필드 부족 시 대체 정책 데이터로 보완하지 않고 빈 결과를 반환한다.
취업 MVP에서는 기업마당을 핵심 데이터로 두지 않고, 창업/사업자 관련 질문에 대응하는 보조 데이터로 유지한다.

## 환경변수

`.env.example`에는 키 이름만 둔다. 실제 `.env`는 로컬/VM에만 둔다.

```env
UPSTAGE_API_KEY=
YOUTHCENTER_POLICY_API_KEY=
YOUTHCENTER_POLICY_API_URL=https://www.youthcenter.go.kr/opi/youthPlcyList.do
EMPLOYMENT24_TRAINING_API_KEY=
EMPLOYMENT24_TRAINING_API_URL=https://www.work24.go.kr/cm/openApi/call/hr/callOpenApiSvcInfo310L01.do
EMPLOYMENT24_JOB_API_KEY=
EMPLOYMENT24_JOB_API_URL=https://www.work24.go.kr/cm/openApi/call/wk/callOpenApiSvcInfo210L01.do
BIZINFO_API_KEY=
BIZINFO_API_URL=https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
SERVICE_NAME=policy-compass
APP_ENV=local
CORS_ORIGINS=["*"]
```

주의:

- 실제 API 키를 문서, README, GitHub에 올리지 않는다.
- `.env`를 새 파일로 덮어쓰지 않는다.
- 배포/연동 테스트 기준으로 데모용 대체 정책 데이터 fallback은 사용하지 않는다.
- 실제 온통청년/고용24/기업마당 API를 확인하려면 VM/로컬 `.env`에
  해당 API 키를 넣는다.

## LLM 사용 메모

Upstage Solar API 키가 있으면 LLM 기반 Router/Profile/Response를 사용할 수 있다. 키가 없거나 호출에 실패하면 규칙 기반 fallback이 동작한다.

정책 추천에서 LLM은 다음 역할로 제한한다.

- 사용자 조건 추출 보조
- 후보 정책을 사용자 관점으로 설명
- 확인 필요 조건을 자연어로 정리

LLM이 하면 안 되는 것:

- 후보 데이터에 없는 정책명 생성
- 출처 없는 금액, 날짜, 자격 조건 생성
- 최종 자격 판정
- 민감 개인정보 요청

## Docker

```bash
docker compose up --build
```

현재 Docker 기준 포트:

```text
host 8000 -> container 8000
```

## GCP VM 권장 설정

초기 추천:

```text
Machine type: e2-medium
OS: Ubuntu 22.04 LTS 또는 24.04 LTS
Disk: Balanced Persistent Disk 30GB
Region: asia-northeast3-a 또는 asia-northeast3-b
```

방화벽:

- 개발/실습 단계: 8000 허용
- URL 제출/정식 접근: 80 허용
- HTTPS 적용 시: 443 허용
- SSH: 22 허용

외부 확인:

```text
http://VM_EXTERNAL_IP:8000/
http://VM_EXTERNAL_IP:8000/health
http://VM_EXTERNAL_IP:8000/docs
```

## URL 신청 시 주의

어떤 신청 폼은 `http://IP:8000`처럼 포트가 붙은 URL을 거부할 수 있다.

그 경우 다음 중 하나로 처리한다.

1. 신청란에는 `http://VM_EXTERNAL_IP`만 입력한다.
2. VM에서 Nginx를 설치해 80번 포트를 8000번으로 프록시한다.

Nginx 구성 방향:

```text
외부 http://VM_EXTERNAL_IP
-> VM 80번 포트
-> 내부 http://127.0.0.1:8000
```

## 배포 전 확인할 것

- [ ] `.env`에 필요한 키가 있는가?
- [ ] `.env`가 GitHub에 올라가지 않는가?
- [ ] `/health`와 `/api/health`가 정상 응답하는가?
- [ ] `/` UI가 정상 표시되는가?
- [ ] `/api/chat`이 정상 응답하는가?
- [ ] 기업마당 API 실패 시 대체 데이터로 보완하지 않고 빈 결과/안내 흐름으로 처리되는가?
- [ ] 온통청년 API 신청 상태와 키 발급 여부를 확인했는가?
- [ ] 고용24 채용정보 API 개인키 조회 제한에 대한 fallback이 준비되어 있는가?
- [ ] 추천 응답에 원문 링크가 포함되는가?
- [ ] 신청 가능 여부를 확정적으로 말하지 않는가?
