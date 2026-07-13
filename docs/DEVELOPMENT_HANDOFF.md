# 정책나침반 개발 인수인계

최종 갱신: 2026-07-13  
기준: LLM 중심 멀티턴 대화·정책 분야별 조건 확인·Supabase 메모리·외부 API 연동 검증 반영

## 새 개발 세션의 읽기 순서

1. 이 문서에서 현재 상태와 다음 작업을 확인한다.
2. [PROJECT_STATUS.md](PROJECT_STATUS.md)에서 구현 범위와 모듈 책임을 확인한다.
3. [NEXT_ACTIONS.md](NEXT_ACTIONS.md)에서 우선순위와 완료 조건을 확인한다.
4. API 스키마가 필요하면 [API_TOOL_SCHEMA_DESIGN.md](API_TOOL_SCHEMA_DESIGN.md)를 읽는다.
5. 배포 작업이면 [day4/DEPLOYMENT_RUNBOOK.md](day4/DEPLOYMENT_RUNBOOK.md)를 따른다.

일일회고 문서는 개발 기준 문서가 아니다. 코드와 이 문서가 다르면 먼저 실제 코드와 테스트를 확인한 뒤 이 문서를 갱신한다.

## 현재 완료된 기반

- Docker Multi-stage 이미지와 Docker Compose 구성 완료
- GitHub Actions CI와 CD 자동 배포 구성 완료
- Google Cloud Compute Engine 배포와 외부 `/api/health` 성공 이력 확인
- Upstage Solar 실제 호출 확인
- 일반 대화와 검색 없는 설명을 하나의 Conversation Node로 통합
- LLM이 `action`, `response_mode`, `request_kind`, `search_query`를 함께 계획하도록 수정
- 청년정책, 훈련, 채용, 기업마당 중 선택된 Tool만 호출하도록 분리
- 키워드와 정규식 규칙을 정상 경로가 아닌 fallback 모듈로 격리
- 검색 결과 응답 생성과 템플릿 fallback을 별도 컴포저로 분리
- 개인회원에 허용된 고용24 채용행사·공채속보·공채기업정보 연동
- 온통청년·기업마당 실제 응답 형식 정규화
- 외부 API 오류 로그에 URL·query string·인증키가 남지 않도록 보완
- 온통청년 정책명 검색이 0건이면 핵심 주제어로 완화해 재검색
- 온통청년 `zipCd` 행정코드를 사용해 사용자 거주지역과 맞는 정책만 필터링
- 온통청년 사업 종료일이 지난 정책은 추천 전에 제외하고 사업기간과 신청기간을 분리
- 구체적인 정책 검색어가 0건일 때 무관한 넓은 정책 분야로 바꾸지 않음
- Supabase에 최근 대화 8개, 프로필, 미완료 검색 계획을 저장·복원
- 정책 검색 전에 유형별 필수 조건을 묻고 원래 요청으로 검색 재개
- 온통청년 정책을 일자리, 주거, 교육·직업·훈련, 금융·복지·문화, 참여·기반으로 구분
- 넓은 청년정책 문의는 관심 분야를 먼저 묻고, 취업 상태는 일자리 분야에서만 추가 확인
- 일반 대화와 Router/Profile LLM에 최근 대화 문맥 전달
- 동일한 고정 검색 실패 문구를 출처·검색어 기반 LLM 응답으로 교체
- LLM Markdown·형식적 머리말·내부 필드명을 일반 채팅용 텍스트로 정리
- 실제 null인 신청 정보만 후보별 `data_notice`로 전달하고 중복 자격 안내 제거
- Ruff lint/format 통과, pytest `78 passed`

## 현재 Agent 흐름

```text
FastAPI /api/chat 또는 /api/chat/stream
-> Supabase에서 recent_history/profile/pending_request 복원
-> Router LLM
   -> RoutingDecision(action, response_mode, request_kind, search_query, resume_pending)
   -> RESPOND
      -> Conversation Node(response_mode: general / explain / out_of_scope)
   -> SEARCH
      -> Profile Extractor LLM
      -> Missing Slot 검사
      -> request_kind에 맞는 Tool 하나 호출
         - youth_policy: 온통청년
         - training: 고용24 훈련
         - recruitment: 고용24 채용 보조
         - business: 기업마당
      -> 정책 후보는 Eligibility Scorer 적용
      -> grounded LLM Response Composer
-> Guardrail
-> 최근 대화·프로필·pending_request를 Supabase에 저장
-> API 응답
```

Router의 정상 출력 예시:

```json
{
  "action": "SEARCH",
  "response_mode": "recommend",
  "request_kind": "training",
  "search_query": "클라우드 엔지니어",
  "resume_pending": false
}
```

## 모듈 책임

| 파일 | 책임 |
| --- | --- |
| `app/graph/contracts.py` | `Action`, `ResponseMode`, `RequestKind`, `RoutingDecision` 검증 계약 |
| `app/graph/fallbacks.py` | LLM 장애 시 사용할 키워드·정규식 fallback |
| `app/graph/nodes.py` | LangGraph 상태를 읽고 각 컴포넌트를 호출하는 노드 orchestration |
| `app/graph/response_composer.py` | grounded LLM 응답과 결정론적 템플릿 fallback |
| `app/graph/state.py` | `action`, `response_mode`, 호환 `intent`, 검색 계획과 결과 상태 |
| `app/core/prompts.py` | Router, Profile, Conversation, Grounded Response 프롬프트 |
| `app/core/llm.py` | Upstage Solar HTTP 클라이언트와 JSON 추출 |
| `app/tools/executor.py` | Repository 예외를 안전하게 처리하는 Tool 경계 |
| `app/repositories/` | 외부 API 호출과 응답 정규화 |
| `app/repositories/chat_memory.py` | Supabase 최근 대화·프로필·미완료 요청 저장/복원 |
| `data/supabase_schema.sql` | 대화·훈련 캐시·RAG 테이블과 RLS를 포함하는 통합 기준 스키마 |
| `data/chat_memory_schema.sql` | 대화 메모리만 설치할 때 쓰는 최소 스키마 |

`nodes.py`에서 보이는 `_heuristic_*`와 `_extract_training_search_keyword`는 호환용 import다. 실제 규칙은 모두 `fallbacks.py`에 있고 다음 경우에만 사용한다.

- Solar 키가 없음
- Solar 호출 실패
- Router JSON이 `RoutingDecision` 계약을 통과하지 못함
- LLM과 프로필에서 검색어를 모두 얻지 못함

## 실제 API 상태

`.env`에는 아래 외부 API와 Supabase 설정이 있다. 값은 출력하거나 문서에 기록하지 않는다.

| 데이터 소스 | 현재 확인 상태 | 다음 검증 |
| --- | --- | --- |
| Upstage Solar | 실제 Router와 Conversation LangGraph smoke test 성공 | 배포 환경 회귀 확인 |
| 온통청년 | `getPlcy` JSON API 실제 3건 성공 | Agent 전체 경로 회귀 확인 |
| 고용24 훈련 | 실제 호출 성공, 3건과 상세 URL 확인 | Agent 전체 경로 회귀 확인 |
| 고용24 채용 | 허용 3개 endpoint 실제 호출 성공, 3종 결과 확인 | Agent 전체 경로 회귀 확인 |
| 기업마당 | JSON `jsonArray`·날짜·해시태그 정규화, 실제 3건 성공 | Agent 전체 경로 회귀 확인 |
| Supabase | `chat_logs`, `chat_sessions` 저장·복원과 RLS 차단 실제 확인 | 배포 환경 회귀 확인 |

온통청년은 구형 `opi/youthPlcyList.do`/`openApiVlak`가 아니라 `go/ythip/getPlcy`/`apiKeyNm`을 사용한다. 응답은 JSON이며 정책 목록은 `result.youthPolicyList`에 있다.

## 방금 완료한 리팩터링

- `RoutingDecision(action, response_mode, request_kind, search_query)` 계약 추가
- Router LLM 판단을 키워드가 덮어쓰던 로직 제거
- Router가 Tool 입력용 `search_query` 생성
- `search_query`를 훈련·채용·정책 Tool 입력에 우선 사용
- Explain/General 노드를 제거하고 Conversation Node 하나로 통합
- 검색 없는 설명은 `RESPOND/explain`, 공식 데이터 설명은 `SEARCH/explain`으로 분리
- 외부 API 후보 결과도 데이터 범위 안에서 LLM이 설명
- 기업마당과 온통청년 동시 호출 제거
- 창업 질문은 기업마당, 청년정책 질문은 온통청년으로 분리
- 민감할 수 있는 검색어 원문을 로그에 남기지 않고 존재 여부만 기록
- Router에 최근 대화, 누적 프로필, `pending_request`를 전달하고 `resume_pending` 계약 추가
- 조건 확인 질문 시 원래 요청·Tool·검색어를 저장하고 후속 답변 뒤 같은 검색 재개
- 청년정책은 지역·만 나이·정책 분야를 확인하고 일자리 분야만 취업 상태를 추가 확인하며, 훈련/채용은 직무·지역,
  창업지원은 지역·창업 상태·사업자 등록 여부를 필요한 경우 먼저 확인
- 새 관심 분야가 확인되면 과거 `interest_fields`를 무조건 합치지 않고 현재 값으로 교체
- 일반 Conversation Node에 최근 8개 메시지를 전달
- LLM 응답 후보에서 큰 `raw` payload를 제거하고 문자열 길이를 제한
- 주민번호·카드번호 형태 마스킹, 메시지 4,000자 제한, Supabase 요청 3초 timeout 적용
- `session_id`를 안전한 문자 128자 이하로 제한
- 대화 테이블 RLS 활성화, 백엔드 `SUPABASE_KEY`는 secret/service_role 키 사용
- pgvector 4,096차원에서 만들 수 없는 HNSW 인덱스 정의 제거

실제 Solar 확인 결과:

```text
개발 교육에 대한 고민 -> RESPOND / general / search_query 없음
국비훈련 장점 설명 -> RESPOND / explain / search_query 없음
청년도약계좌 현재 조건 설명 -> SEARCH / explain / 청년도약계좌
클라우드 국비과정 검색 -> SEARCH / recommend / 클라우드 엔지니어
```

## 다음 작업 순서

1. PR CI 통과 후 main에 병합하고 기존 CD로 Google Cloud에 반영한다.
2. 배포본에서 Supabase 대화 저장·재시작 후 복원과 API별 대표 질문을 확인한다.
3. 질문 유형별 SSE `status` 문구를 Router 결과에 맞춰 다르게 만든다.
4. 외부 공개 전 로그인 기반 세션 소유권, 보존 기간, 삭제 기능을 설계한다.
5. 같은 `session_id`의 동시 요청 충돌과 Supabase 장애 지표를 보완한다.

## 로컬 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
```

현재 기준 기대 결과는 `78 passed`다. 테스트는 `tests/conftest.py`에서 외부 키를 비워 네트워크 없이 재현 가능해야 한다.

## 핵심 수동 테스트

```text
요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어
서울에서 클라우드 엔지니어 국비과정 찾아줘
서울 사는 만 28세 미취업자인데 받을 수 있는 청년정책 찾아줘
서울에서 데이터 분석 신입 채용정보를 찾아줘
카페 창업 지원사업을 추천해줘
국비지원 훈련을 받으면 뭐가 좋아?
거주지원을 받고 싶은데 관련 정책 있어?
서울에 사는 만 25세 취업 준비생이야
청년 지원 정책에 대한 정보를 얻고 싶어
서울 만 24세
거주지원 정책 정보를 원해
```

확인 항목:

- `routing_source=llm`인지 확인
- `request_kind`가 질문 의미와 일치하는지 확인
- `RESPOND` 질문은 Tool을 호출하지 않고 `SEARCH` 질문만 Tool을 호출하는지 확인
- 검색 질문에서 선택된 Tool 하나만 호출하는지 확인
- API 결과에 없는 사실을 만들지 않는지 확인
- 원문 링크와 권한 제한 안내가 유지되는지 확인
- 조건 답변 뒤 원래 정책 주제(예: 주거)로 검색을 재개하는지 확인
- 포괄 청년정책 문의에서 일자리를 추정하지 않고 공식 5개 정책 분야를 묻는지 확인
- 주거·교육·복지·문화·참여 분야에서 취업·창업 상태를 불필요하게 묻지 않는지 확인
- 같은 session_id로 서버 재시작 후 최근 대화와 프로필이 복원되는지 확인

## 비밀값 및 Git 주의사항

- `.env`는 Git에 추가하지 않는다.
- API 키 값, 전체 인증 URL, 인증 헤더를 로그·문서·캡처에 남기지 않는다.
- 외부 API live 검증 로그에는 상태·건수·정규화 유형만 남긴다.
- `SUPABASE_KEY`에는 publishable/anon 키가 아니라 서버 전용 secret/service_role 키를 넣는다.
- 현재 session_id는 인증된 사용자 식별자가 아니므로 외부 공개 전 소유권 검증이 필요하다.
- 기존 사용자 변경을 되돌리지 않는다.
