# 협업 규칙 및 진행 공유 방식

## 목적

이 문서는 정책나침반 팀원이 같은 코드 구조를 기준으로 작업하고, 충돌 없이 개발·문서화·배포를 이어가기 위한 협업 기준이다.

현재 기준 구조는 팀원이 공유한 `policy-compass-agent` 폴더 구조를 기반으로 하며, 기존 로컬 작업 내용 중 Mock 데이터, 기업마당 API 정규화, 8000 포트 실행, 문서 내용을 통합했다.

## 매일 공유할 내용

각자 작업 시작 전 또는 종료 전에 아래 형식으로 공유한다.

```text
오늘 할 일:
-

진행 중:
-

완료:
-

막힌 점:
-

다음 사람에게 필요한 정보:
-
```

## 역할 분담

| 역할 | 담당 범위 | 우선 담당 |
| --- | --- | --- |
| Agent / LLM | LangGraph 노드, Router/Profile/Response 프롬프트, LLM fallback, 가드레일 | Agent 담당 |
| Data / API | 기업마당 API, Mock 정책 데이터, 정책 스키마, RAG-lite 검색 | Data 담당 |
| Backend / UI | FastAPI 라우트, 정적 UI, SSE 스트리밍, API 응답 구조 | Backend 담당 |
| Infra / Docs | Docker, GCP, README, 개발 문서, GitHub Actions | Infra/Docs 담당 |
| 공통 | 데모 시나리오, 발표자료, 회고, 최종 QA | 둘 다 |

담당자는 고정 소유자가 아니라 우선 책임자다. 막히면 바로 공유하고 같이 푼다.

## 현재 주요 경로

| 경로 | 설명 |
| --- | --- |
| `app/api/routes/` | FastAPI API 라우트 |
| `app/graph/` | LangGraph 상태, 노드, 엣지, 점수화 |
| `app/repositories/` | 정책 데이터 접근 및 RAG-lite 검색 |
| `app/core/` | 환경 설정, LLM 클라이언트, 프롬프트 |
| `app/schemas/` | 채팅/정책 Pydantic 모델 |
| `app/static/index.html` | 데모 채팅 UI |
| `data/mock_policies.json` | 데모 정책 데이터 |
| `docs/` | 개발 현황, 로드맵, 배포 메모, 협업 문서 |
| `tests/` | Agent/API 테스트 |

## 브랜치/커밋 규칙

권장 브랜치:

```text
main
feature/agent-llm-guardrails
feature/bizinfo-api
feature/deploy-gcp
docs/presentation
```

커밋 메시지 예시:

```text
feat: integrate langgraph agent structure
feat: add bizinfo normalization fallback
fix: prevent unsupported LLM policy claims
docs: update project status for team structure
test: add chat and policy api coverage
```

## 환경변수 규칙

`.env`는 개인 로컬/VM에만 둔다. GitHub에 올리지 않는다.

공유 가능한 파일:

```text
.env.example
```

공유 금지:

```text
.env
UPSTAGE_API_KEY 실제 값
BIZINFO_API_KEY 실제 값
Supabase 키
서비스 계정 키
비밀번호
```

현재 필요한 환경변수:

```env
UPSTAGE_API_KEY=
BIZINFO_API_KEY=
BIZINFO_API_URL=https://www.bizinfo.go.kr/uss/rss/bizinfoApi.do
SERVICE_NAME=policy-compass
APP_ENV=local
USE_MOCK_POLICY_DATA=true
CORS_ORIGINS=["*"]
```

## 포트 및 실행 기준

현재 프로젝트는 FastAPI 단일 서버 기준이다.

```text
로컬 UI: http://localhost:8000/
API 문서: http://localhost:8000/docs
헬스체크: http://localhost:8000/health 또는 /api/health
```

기본 실행:

```bash
uv sync
uv run python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

테스트:

```bash
uv run python -m pytest
```

## 파일 충돌 방지 규칙

- `app/graph/nodes.py`, `app/core/prompts.py`, `app/core/llm.py`는 Agent/LLM 담당자가 우선 수정한다.
- `app/repositories/policy.py`, `app/repositories/rag.py`, `data/mock_policies.json`는 Data/API 담당자가 우선 수정한다.
- `app/api/routes/`, `app/static/index.html`, `app/main.py`는 Backend/UI 담당자가 우선 수정한다.
- `Dockerfile`, `docker-compose.yml`, `.env.example`, `.github/workflows/`는 Infra 담당자가 우선 수정한다.
- 같은 파일을 동시에 고쳐야 하면 먼저 팀 채팅에 남긴다.

## LLM 응답 협업 기준

LLM은 정책 사실을 새로 만드는 도구가 아니라, 검색된 후보와 사용자 프로필을 근거로 설명을 정리하는 도구다.

반드시 지킬 것:

- 후보 데이터에 없는 정책명, 금액, 신청기간, 링크를 만들지 않는다.
- 최종 자격 판정을 하지 않는다.
- 단정 표현 대신 가능성/확인 필요 표현을 사용한다.
- 민감 개인정보를 요청하지 않는다.
- 공식 공고문 또는 담당 기관 확인 안내를 포함한다.

프롬프트 수정 후에는 최소 아래 질문으로 수동 QA를 한다.

```text
서울 사는 만 28세 미취업자인데 구직지원금 받을 수 있어?
아직 사업자는 없고 서울에서 AI 서비스 창업 준비 중이야. 창업지원사업 있어?
경기에서 2년째 음식점 운영 중인데 소상공인 지원사업 찾아줘.
취업 준비 중인데 받을 수 있는 지원금 있어?
```

## GitHub 업로드 전 체크리스트

- [ ] `.env`가 포함되지 않았는가?
- [ ] `_merge_backup_before_team_structure` 같은 임시 백업 폴더를 올리지 않을지 결정했는가?
- [ ] `uv run python -m pytest`가 통과하는가?
- [ ] `http://localhost:8000/` UI가 열리는가?
- [ ] `/api/chat`과 `/api/chat/stream`이 응답하는가?
- [ ] 답변에 원문 링크와 확인 필요 조건이 포함되는가?
- [ ] LLM 답변이 출처 없는 날짜/금액/자격 조건을 만들지 않는가?

## 데모 우선순위

1. 미취업 청년 구직지원금 추천
2. 예비창업자 창업지원사업 추천
3. 소상공인 경영/인력 지원사업 추천
4. 조건 부족 시 되묻기
5. 범위 밖 질문 가드레일
