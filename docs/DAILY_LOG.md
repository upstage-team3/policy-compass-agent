# 일일 개발 로그

## 2026-07-09

### 오늘의 목표

Mock 기반 정책 추천 Agent MVP를 만들고, 팀원이 공유한 GitHub 구조와 현재 로컬 작업물을 통합해 GitHub 업데이트 가능한 상태로 정리한다.

### 진행한 작업

- 프로젝트 폴더에 `policy-compass` 개발 폴더를 생성했다.
- 제공된 스타터 코드를 기반으로 정책 추천 Agent 방향을 잡았다.
- 의료 QA Agent 스타터 코드를 정책 추천 도메인으로 전환했다.
- 사용자 조건 분석, 부족 조건 확인, 정책 검색, 점수화, 응답 생성 흐름을 1차 구현했다.
- 청년, 창업, 소상공인 시나리오용 Mock 정책 데이터를 작성했다.
- 기업마당 API 인증키를 `BIZINFO_API_KEY`로 받아 실제 API를 호출하는 구조를 추가했다.
- API 호출 실패 또는 키 누락 시 Mock 데이터로 fallback하도록 구현했다.
- 팀원이 공유한 `policy-compass-agent` zip 구조를 검토했다.
- 팀원 구조의 장점인 `app/api/routes`, `app/graph`, `app/repositories`, `app/schemas`, `app/static`, `tests` 구조를 현재 프로젝트에 통합했다.
- 팀원 zip에 누락되어 있던 `data/mock_policies.json`을 현재 데모 시나리오 기준으로 새 스키마에 맞춰 작성했다.
- 기업마당 API 응답을 팀원 스키마로 직접 정규화하는 로직을 `app/repositories/policy.py`에 반영했다.
- FastAPI 단일 서버 구조로 정리하고 실행 포트를 8000으로 통일했다.
- 기존 `/health`, `/api/v1/chat/sync`, `/api/v1/chat` 호환 라우트를 유지했다.
- 기존 Streamlit 8002 구조를 제거하고, FastAPI 정적 UI(`/`) 기준으로 정리했다.
- `pyproject.toml`, `uv.lock`, `.env.example`, `Dockerfile`, `start.sh`, README를 통합 구조 기준으로 갱신했다.
- 개발 현황, 협업 규칙, 로드맵, 다음 작업, 배포 메모 문서를 현재 상태에 맞게 갱신했다.

### 현재 완료된 것

- FastAPI 단일 서버 실행 구조
- 정적 채팅 UI: `http://localhost:8000/`
- API 문서: `http://localhost:8000/docs`
- LangGraph Agent 구조
- 세션 기반 프로필 누적
- LLM 사용 가능 + 규칙 기반 fallback 구조
- Mock 정책 데이터 기반 데모
- 기업마당 API 호출 및 정규화 1차 구현
- 정책 목록/상세/검색 API
- SSE 스트리밍 API
- 테스트 23개 통과

### 검증 결과

```text
uv run python -m pytest
23 passed, 2 warnings
```

확인한 URL:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/health
http://127.0.0.1:8000/docs
```

### 확인된 이슈

- `.env`에 실제 Upstage, 기업마당, Supabase 키가 들어 있으므로 GitHub 업로드 전 반드시 제외해야 한다.
- LLM이 켜진 상태에서는 답변이 자연스러워지는 대신 출처 없는 기준 연도, 금액, 조건을 말할 위험이 있으므로 프롬프트/가드레일을 더 강화해야 한다.
- 기업마당 API 응답 필드는 실제 공고별로 비어 있을 수 있어 정규화 로직 보강이 필요하다.
- `_merge_backup_before_team_structure` 백업 폴더는 GitHub에 포함할지 제외할지 결정해야 한다. 일반적으로는 올리지 않는 편이 좋다.

### 다음 작업

- LLM 응답 가이드라인을 `app/core/prompts.py`에 더 엄격하게 반영
- LLM 사용 시 정책 후보 데이터 밖의 사실을 생성하지 않는지 수동 QA
- 기업마당 API 실제 응답 샘플 기반 필드 매핑 보강
- Docker Compose 실행 검증
- GitHub 업로드 전 `.gitignore`와 불필요한 백업 폴더 확인
- 발표용 데모 시나리오 2개 확정

### 멘토링 때 확인할 질문

- LLM을 정책 추천 응답 생성에 사용할 때 필요한 최소 가드레일이 충분한가?
- 기업마당 API + Mock fallback 구조가 평가 관점에서 적절한가?
- 정책 추천 점수화 기준이 발표 데모 수준에서 충분한가?
- 발표 데모는 청년/창업 2개 시나리오면 충분한가?
- 실제 API 데이터가 불완전할 때 Mock fallback을 어디까지 명시해야 하는가?
