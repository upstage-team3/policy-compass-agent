# 일일 개발 로그

> 날짜별 구현 이력을 보존하는 문서다. 현재 상태 판단에는 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 사용한다.

## 2026-07-09

### 오늘의 목표

실제 API 연동 중심의 정책 추천 Agent MVP를 만들고, 팀원이 공유한 GitHub 구조와 현재 로컬 작업물을 통합해 GitHub 업데이트 가능한 상태로 정리한다.

### 진행한 작업

- 프로젝트 폴더에 `policy-compass` 개발 폴더를 생성했다.
- 제공된 스타터 코드를 기반으로 정책 추천 Agent 방향을 잡았다.
- 의료 QA Agent 스타터 코드를 정책 추천 도메인으로 전환했다.
- 사용자 조건 분석, 부족 조건 확인, 정책 검색, 점수화, 응답 생성 흐름을 1차 구현했다.
- 고용24 국민내일배움카드 훈련과정 API를 핵심 실데이터 소스로 연결했다.
- 기업마당 API 인증키를 `BIZINFO_API_KEY`로 받아 실제 API를 호출하는 구조를 추가했다.
- API 호출 실패 또는 키 누락 시 데모용 대체 정책 데이터로 보완하지 않고 빈 결과 또는 안내 fallback으로 드러나도록 구현했다.
- 팀원이 공유한 `policy-compass-agent` zip 구조를 검토했다.
- 팀원 구조의 장점인 `app/api/routes`, `app/graph`, `app/repositories`, `app/schemas`, `app/static`, `tests` 구조를 현재 프로젝트에 통합했다.
- 배포/연동 테스트 기준으로 데모용 정책 JSON 의존을 제거했다.
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
- 고용24 훈련과정 실데이터 기반 데모
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
- 기업마당 API 실패 시 빈 결과로 처리하는 구조가 평가 관점에서 적절한가?
- 정책 추천 점수화 기준이 발표 데모 수준에서 충분한가?
- 발표 데모는 청년/창업 2개 시나리오면 충분한가?
- 실제 API 데이터가 불완전할 때 빈 결과/안내 fallback을 어디까지 명시해야 하는가?

## 2026-07-10

### 오늘의 결정

MVP 핵심 대상을 취업 준비 청년으로 재확정했다. 대학생, 졸업예정자, 사회초년생, 미취업 청년을 우선 사용자로 두고, 취업 지원정책과 채용정보 추천을 중심으로 개발한다.

### 데이터 소스 방향

- 온통청년 Open API를 청년 취업정책의 핵심 데이터 소스로 신청한다.
- 고용24 국민내일배움카드 훈련과정 API를 실데이터 핵심으로 사용하고, 고용24 채용정보 API는 권한 허용 범위에서 보조로 사용한다.
- 이미 확보한 기업마당 API는 창업/사업자 관련 질문에 대응하는 보조 데이터로 유지한다.

### 문서 반영

- README의 MVP 설명을 취업 대상 청년 중심으로 수정했다.
- API 및 배포 메모에 온통청년, 고용24 훈련과정, 고용24 채용정보, 기업마당의 역할과 예상 환경변수를 정리했다.
- 개발 현황, 로드맵, 다음 작업 체크리스트에 API 신청과 필드 매핑 작업을 추가했다.

### 다음 작업

- 온통청년 Open API 인증키 신청
- 고용24 국민내일배움카드 훈련과정 API 인증키 신청
- 고용24 채용정보 API 개인키 조회 제한 확인
- 온통청년 JSON 응답을 내부 `YouthPolicyItem` 스키마로 매핑
- 채용정보 API는 제한 응답 시 채용 탐색 가이드로 폴백하도록 설계
- 취업 MVP 데모 질문 3개 확정

### Day3 개발 진행

- LLM 응답 프롬프트에 후보 데이터 밖의 정책명, 금액, 날짜, 자격 조건, 링크 생성 금지 규칙을 더 명확히 반영했다.
- 템플릿 응답도 추천 이유, 지원 대상, 신청 기간, 신청 방법, 신청 전 확인 필요 조건, 원문 링크가 항상 드러나도록 보강했다.
- `/api/chat/stream`이 답변 생성 전 `status` 이벤트를 먼저 보내고, 빈 답변이나 서버 오류는 SSE 오류 이벤트로 반환하도록 개선했다.
- 정적 채팅 UI에서 빈 말풍선 대신 진행 상태를 보여주고, 첫 토큰 수신 시 실제 답변으로 교체하도록 수정했다.
- 기업마당 API 정규화에서 `response > body > items > item` 형태와 일부 빈 필드를 안전하게 처리하도록 보강했다.
- 조건 부족 실패 케이스와 기업마당 필드 누락 케이스 회귀 테스트를 추가했다.

### Day3 검증 결과

```text
uv run python -m pytest
26 passed, 2 warnings
```

로컬 서버 검증:

```text
/health 200
/ 200
/docs 200
/api/chat/stream 200, event: token / event: done 확인
```

Docker Compose 설정은 유효하지만 Docker Desktop 데몬이 실행 중이지 않아 빌드는 확인하지 못했다. Docker Desktop 실행 후 `docker compose build`와 `docker compose up` 검증이 필요하다.

### Day3 개발 가이드 수정

- 오늘 핵심 MVP를 청년지원사업 및 취업 관련 청년 정보 챗봇으로 재정의했다.
- 현재 연결 상태를 기준으로 고용24 국민내일배움카드 훈련과정 API를 우선 실데이터 연동 대상으로 잡았다.
- 고용24 채용정보 API는 개인키 권한 제한을 전제로 채용행사/공채속보/공채기업정보 또는 채용 탐색 가이드 fallback 중심으로 정리했다.
- 온통청년 청년정책 API는 키 미설정 상태이므로 실제 호출을 오늘 blocker로 두지 않고, 키가 없으면 빈 결과로 처리하며 스키마/normalizer 준비 작업으로 분리했다.
- 기업마당 API는 오늘 핵심 MVP에서 제외하고 창업/사업자 질문의 보조 데이터로 유지하기로 했다.
- 발표자료와 발표용 데모 시나리오 확정은 오늘 개발 가이드에서 제외했다.

### Day3 revised 구현 진행

- `PolicySearchInput`에 나이, 졸업 상태, 관심 직무, 희망 지원 유형 필드를 보강했다.
- `YouthPolicySearchInput`, `TrainingCourseSearchInput`, `RecruitmentInfoSearchInput`과 각 출력 스키마를 추가했다.
- 고용24 국민내일배움카드 훈련과정 XML normalizer를 추가하고, 과정명/기관명/지역/기간/비용/NCS/상세 URL 매핑을 구현했다.
- 고용24 훈련과정 API는 기본 조회에서 결과가 반환되는 것을 확인했다. 특정 키워드 결과가 없을 때는 훈련과정 탐색 가이드로 fallback한다.
- 고용24 채용정보 API의 개인회원 권한 제한 문구를 감지하고, 직접 공고를 생성하지 않는 채용 탐색 가이드로 변환하도록 구현했다.
- 온통청년 키 미설정 상태에서는 내부 정책 데이터로 청년지원사업 fallback이 이어지도록 `YouthCenterRepository`를 추가했다.
- Agent에 `request_kind`를 추가해 청년지원사업, 훈련과정, 채용 보조 정보 흐름을 구분하도록 했다.
- 훈련과정/채용 fallback API 라우트 테스트와 normalizer 단위 테스트를 추가했다.

검증 결과:

```text
uv run python -m pytest
37 passed, 2 warnings
```
