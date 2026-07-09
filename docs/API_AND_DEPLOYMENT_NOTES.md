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

현재 코드는 기업마당 API 호출 결과를 `PolicyItem` 스키마로 1차 정규화한다. 호출 실패, 키 누락, 응답 필드 부족 시 `data/mock_policies.json`로 fallback한다.

## 환경변수

`.env.example`에는 키 이름만 둔다. 실제 `.env`는 로컬/VM에만 둔다.

```env
UPSTAGE_API_KEY=
BIZINFO_API_KEY=
BIZINFO_API_URL=https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
SERVICE_NAME=policy-compass
APP_ENV=local
USE_MOCK_POLICY_DATA=true
CORS_ORIGINS=["*"]
```

주의:

- 실제 API 키를 문서, README, GitHub에 올리지 않는다.
- `.env`를 새 파일로 덮어쓰지 않는다.
- `USE_MOCK_POLICY_DATA=true`이면 Mock 데이터를 우선 사용한다.
- 실제 기업마당 API를 확인하려면 VM/로컬 `.env`에서 `USE_MOCK_POLICY_DATA=false`로 설정하고 `BIZINFO_API_KEY`를 넣는다.

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
- [ ] 기업마당 API 실패 시 Mock fallback이 되는가?
- [ ] 추천 응답에 원문 링크가 포함되는가?
- [ ] 신청 가능 여부를 확정적으로 말하지 않는가?
