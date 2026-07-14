# 정책나침반 개발 인수인계

최종 갱신: 2026-07-14
기준: 지역 정규화·근거 기반 스코어링·새 채팅 기본 프로필·온통청년 장애 구분·로컬 UI 검증 반영

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
- 온통청년 사업 종료일과 종료된 신청기간을 추천 전에 제외하고 사업기간과 신청기간을 분리
- 온통청년의 전국 `zipCd` 오표기를 등록·주관 지자체명으로 교차 검증하고 `0~0세`는 연령 제한 없음으로 정규화
- 2026-07-14 행정표준코드 현존 시·군·구 300개를 공식 5자리 코드와 연결한 전국 지역 정규화기 추가
- 성남 `41130`, 해운대구 `26350`, 전주 `52110` 등 시·군·구를 온통청년 코드와 기업마당 시·도 태그로 일관되게 변환
- `중구`, `고성군`처럼 여러 시·도에 같은 이름이 있으면 임의 추정하지 않고 시·도를 다시 확인
- 정확 지역과 전국 결과를 우선하고, 둘 다 없을 때만 가까운 시·도 결과 최대 3건을 별도 참고 결과로 제공
- 기업마당의 `전남광주` 결합형 16개 태그와 `광주`·`전남` 분리형 17개 태그를 모두 전국 범위로 정규화
- 기업마당의 전 지역 태그를 그대로 신뢰하지 않고 공고 본문의 소재지·본사 이전·전입 조건을 교차 검증해 지자체 제한 공고를 재분류
- `지역제한 없음`은 지자체 기관명·지역 태그보다 우선하고, 태그 누락은 전국으로 추정하지 않음
- 기업마당 본문의 `예비창업자`, `창업 N년`, `업력`, `사업자등록` 조건을 구조화해 사업자 등록 불일치를 추천 전에 제외
- 기업마당 조회 폭을 최대 5배로 넓히고 관심 분야 유사어를 우선 정렬해 뒤쪽의 관련 후보도 점수화
- 점수는 전체 평가 기준 대비 확인된 일치 근거로 계산하고, 실제 비교 가능한 범위는 `evidence_coverage`로 분리
- 구체적인 정책 검색어가 0건일 때 무관한 넓은 정책 분야로 바꾸지 않음
- Supabase에 최근 대화 8개, 프로필, 미완료 검색 계획을 저장·복원
- 정책 검색 전에 유형별 필수 조건을 묻고 원래 요청으로 검색 재개
- 온통청년 정책을 일자리, 주거, 교육·직업·훈련, 금융·복지·문화, 참여·기반으로 구분
- 넓은 청년정책 문의는 관심 분야를 먼저 묻고, 취업 상태는 일자리 분야에서만 추가 확인
- 일반 대화와 Router/Profile LLM에 최근 대화 문맥 전달
- 동일한 고정 검색 실패 문구를 출처·검색어 기반 LLM 응답으로 교체
- LLM Markdown·형식적 머리말·내부 필드명을 일반 채팅용 텍스트로 정리
- 실제 null인 신청 정보만 후보별 `data_notice`로 전달하고 중복 자격 안내 제거
- React 채팅 메시지 렌더링 수정과 프런트엔드 변경 CI 트리거 반영
- Router 결과·부족 조건에 따른 SSE 상태 문구와 React 타이핑 영역 표시
- React 채팅 목록·메시지·정책 카드를 로컬 저장소에서 복원하고 UUID 세션을 유지
- 브라우저에서 확인된 거주 지역·만 나이를 최소 기본 프로필로 별도 저장해 새 채팅에도 전달
- 광범위한 `청년 주거 정책을 알려줘` 요청을 특정 제도 설명과 구분해 추천 검색으로 라우팅
- 설명 모드로 분류되더라도 주거 등 정책 분야 목록 요청은 지역·나이 조건을 확인하도록 방어 로직 추가
- 온통청년 요청에서 오류를 유발하던 브라우저형 헤더를 제거하고 5xx를 한 번 재시도
- 온통청년 호출 실패를 실제 결과 0건과 구분해 `정책이 없다`고 잘못 안내하지 않는 결정론적 장애 안내 추가
- 브라우저 저장 전 민감정보 마스킹, 최근 20개 채팅·채팅별 50개 메시지 제한, 개별·전체 삭제
- Ruff lint/format, pytest `149 passed`, 프런트 저장 회귀 `7 passed`, 프로덕션 빌드 통과
- 최신 main `a89d1e3`의 GitHub Actions CI/CD와 GCE 내부 헬스체크 성공

## 현재 Agent 흐름

```text
FastAPI /api/chat 또는 /api/chat/stream
-> 브라우저 기본 프로필 중 region/age 수신
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
| `app/core/administrative_regions.py` | 행정표준코드 현존 시·군·구 300개 정적 스냅샷 |
| `app/core/regions.py` | 사용자 지역·법정코드·기업마당 태그 정규화와 대표 좌표 기반 근접 거리 |
| `app/core/relevance.py` | 관심 분야 유사어와 정책 본문 관련성 판정 |
| `app/tools/executor.py` | Repository 예외를 안전하게 처리하는 Tool 경계 |
| `app/repositories/` | 외부 API 호출과 응답 정규화 |
| `app/graph/scoring.py` | 전체 기준 기반 적합도·근거 확인률·하드 불일치 판정 |
| `app/repositories/chat_memory.py` | Supabase 최근 대화·프로필·미완료 요청 저장/복원 |
| `data/chat_memory_schema.sql` | RLS가 적용된 대화 메모리 전용 스키마 |
| `frontend/src/lib/chatStorage.ts` | React 표시 기록의 버전형 저장·복원, 보존 한도, 민감정보 마스킹 |
| `frontend/src/components/PolicyCard.tsx` | 정확/전국/인접 지역 범위와 참고 거리 표시 |

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
| 온통청년 | 브라우저형 헤더 제거 후 경기·만 24세·주거 live 정상 반환, 5xx 재시도와 장애/무결과 구분 완료 | 다른 정책 분야 대표 질의 회귀 확인 |
| 고용24 훈련 | 실제 호출 성공, 3건과 상세 URL 확인 | Agent 전체 경로 회귀 확인 |
| 고용24 채용 | 허용 3개 endpoint 실제 호출 성공, 3종 결과 확인 | Agent 전체 경로 회귀 확인 |
| 기업마당 | 16/17개 지역 태그 형식, 소재지·이전·등록 조건 교차 검증, 부산 카페 창업 Agent 전체 경로 확인 | 배포 환경 회귀 확인 |
| Supabase | `chat_logs`, `chat_sessions` 저장·복원과 RLS 차단 성공 이력 있음 | 로컬 조회 `401` 1회 원인(키·RLS)과 서버 재시작 복원 재확인 |

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
- React `Chat.id`를 UUID로 생성해 백엔드 `session_id`로 유지하고 새로고침 뒤 화면과 문맥을 함께 복원
- 로컬 표시 기록에 최근 채팅·메시지 보존 한도와 삭제 UI 적용
- 대화 테이블 RLS 활성화, 백엔드 `SUPABASE_KEY`는 secret/service_role 키 사용
- pgvector 4,096차원에서 만들 수 없는 HNSW 인덱스 정의 제거

실제 Solar 확인 결과:

```text
개발 교육에 대한 고민 -> RESPOND / general / search_query 없음
국비훈련 장점 설명 -> RESPOND / explain / search_query 없음
청년도약계좌 현재 조건 설명 -> SEARCH / explain / 청년도약계좌
클라우드 국비과정 검색 -> SEARCH / recommend / 클라우드 엔지니어
```

## 2026-07-14 지역 검색·스코어링 안정화

- `exact`, `nationwide`, `nearby`, `unknown` 범위를 정책 후보 계약에 추가했다.
- 정확 지역·전국 후보가 있으면 타 지역 후보는 응답에서 완전히 제외한다.
- 정확 지역·전국 후보가 하나도 없을 때만 대표 좌표 직선거리 순으로 인접 시·도 결과 최대 3건을 제공한다.
- 인접 결과는 추천 점수 0점의 `nearby_reference`로 분리하고 `인접 지역 참고`, 예상 직선거리, 거주 요건 확인 문구를 표시한다.
- 기업마당 인접 탐색은 가장 가까운 5개 시·도까지만 조회해 불필요한 연속 API 호출을 제한한다.
- 기업마당 API가 지자체 공고에도 모든 지역 태그를 붙이는 사례는 본문의 소재지·이전 조건으로 다시 지역 제한을 판정한다.
- `광주`·`전남` 분리형을 포함한 17개 지역 태그는 전국으로 판정하고, `지역제한 없음`도 전국 근거로 우선한다.
- 사업자 미등록 사용자는 기창업자 전용 공고에서 하드 제외하고, 관심 분야 20%를 포함한 전체 100% 가중치 기준으로 순위를 계산한다.
- 카드에는 `요청 지역 일치`·`전국 대상`·`인접 지역 참고`, 추천 적합도, 근거 확인률을 각각 표시한다.
- 로컬 UI의 부산 해운대구 카페 예비창업자 질의에서 타 지역 제한·기창업자 전용 공고가 제외되고 농식품 관련 전국 공고가 68점으로 1순위에 표시됐다.
- 같은 화면을 새로고침한 뒤 68점과 전국 대상 배지 5개가 그대로 복원되는 것을 확인했다.
- 온통청년의 전국 시군구 코드 목록이 지방자치단체 사업에도 들어오는 사례를 기관명으로 교차 검증한다.
- 고정 신청기간의 마지막 날짜가 지났으면 사업 종료일이 없어도 만료 공고로 제외한다.
- 로컬 UI에서 `성남시에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘`를 재검증했다. 의성군 사업과 2025년 마감 장학금은 제외되고 국토교통부 전국 정책만 표시됐다.
- 행정표준코드관리시스템의 2026-07-14 현존 시·군·구 300개를 정적 스냅샷으로 추가하고 모든 행을 시·도 문맥과 함께 복원하는 회귀 테스트를 추가했다.
- 해운대구 live 검색에서 온통청년 `26350`을 사용하고 부산 정확 정책 2건과 전국 정책만 화면에 표시되는 것을 확인했다.
- 전주시는 온통청년 `52110`, 기업마당 `전북`으로 호출되는 것을 확인했다.
- `고성군` 입력을 강원으로 임의 보완하던 LLM 출력을 현재 발화의 공식 지역 표현으로 덮어쓰도록 변경했다.
- 로컬 UI에서 `고성군`은 시·도 확인 질문을 하고, 후속 `경남 고성군이야` 뒤 원래 주거 검색을 재개하는 것을 확인했다.

## 2026-07-14 새 채팅 프로필·온통청년 조회 안정화

- 프로필은 계속 채팅별 Supabase 문맥으로 유지하되, 비민감 기본값인 `region`, `age`만 브라우저에 별도 저장한다.
- 새 채팅 요청은 브라우저 기본값을 전달하고, 같은 채팅에서 이미 확인한 Supabase 프로필이 있으면 그 값을 우선한다.
- 전체 로컬 기록 삭제 시 기본 프로필도 함께 삭제하며, 다른 기기나 브라우저에는 공유하지 않는다.
- `청년 주거 지원 정책에 대해 알려줘`를 광범위한 현재 정책 목록 요청으로 정의해 `SEARCH / recommend / youth_policy / 주거` 예시를 Router 프롬프트에 추가했다.
- 온통청년 HTTP 요청의 브라우저형 헤더와 `pageSize=10` 조합에서 재현된 500을 제거하고, 실패 시 최대 2회 호출 후 장애 안내로 전환한다.
- 로컬 API에서 새 세션에 `경기·만 24세` 기본값을 전달한 동일 질문이 `RECOMMEND`, 부족 조건 없음, 전국 주거 정책 반환으로 확인됐다.
- 실제 UI에서 기존 `경남 고성군·만 25세` 조건을 동기화한 뒤 새 채팅에서도 조건 재질문 없이 같은 지역·나이로 주거 정책을 추천했다.

## 다음 작업 순서

1. 외부 배포 URL의 `/`, `/api/health`, `/docs`와 API별 대표 질문을 수동 확인한다.
2. 로컬 Supabase 키·RLS를 확인하고 같은 UUID로 서버 재시작 뒤 문맥 복원을 다시 검증한다.
3. 훈련·채용·창업 Agent 전체 경로와 API 후보 밖 사실 생성 여부를 QA한다.
4. Day5 Router 평가표로 질문 유형별 SSE `status`와 Tool 단일 선택을 수동 QA한다.
5. 발표용 핵심 시나리오와 외부 API 장애 fallback 시나리오를 확정한다.
6. 외부 공개 전 로그인 기반 세션 소유권과 Supabase 서버 로그의 보존 기간·삭제 API를 설계한다.
7. 같은 `session_id`의 동시 요청 충돌과 Supabase 장애 지표를 보완한다.

## 로컬 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

현재 기준 기대 결과는 Python `149 passed`, 프런트 저장 회귀 `7 passed`다. 테스트는 외부 키를 비워 네트워크 없이 재현 가능해야 한다.

## 핵심 수동 테스트

```text
요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어
서울에서 클라우드 엔지니어 국비과정 찾아줘
서울 사는 만 28세 미취업자인데 받을 수 있는 청년정책 찾아줘
서울에서 데이터 분석 신입 채용정보를 찾아줘
카페 창업 지원사업을 추천해줘
성남시에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘
부산 해운대구에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘
고성군에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘
경남 고성군이야
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
- 새로고침 뒤 채팅 목록·활성 채팅·메시지·정책 카드가 복원되는지 확인
- 새로고침 뒤 주거 조건 후속 답변이 같은 UUID 세션으로 원래 검색을 재개하는지 확인
- 개별·전체 로컬 기록 삭제가 새로고침 뒤에도 유지되는지 확인
- 정확 지역·전국 결과가 있으면 타 지역 후보가 섞이지 않는지 확인
- 정확 지역·전국 결과가 모두 없을 때만 `인접 지역 참고`와 직선거리가 표시되는지 확인
- 신청기간이 지난 온통청년 공고와 `0~0세` 표현이 추천 응답에 노출되지 않는지 확인
- 시·군·구가 공식 5자리 온통청년 코드와 기업마당 시·도 태그로 변환되는지 확인
- 동명이인 시·군·구는 시·도를 추정하지 않고 확인 질문 뒤 원래 검색을 재개하는지 확인

## 비밀값 및 Git 주의사항

- `.env`는 Git에 추가하지 않는다.
- API 키 값, 전체 인증 URL, 인증 헤더를 로그·문서·캡처에 남기지 않는다.
- 외부 API live 검증 로그에는 상태·건수·정규화 유형만 남긴다.
- `SUPABASE_KEY`에는 publishable/anon 키가 아니라 서버 전용 secret/service_role 키를 넣는다.
- 현재 session_id는 인증된 사용자 식별자가 아니므로 외부 공개 전 소유권 검증이 필요하다.
- 기존 사용자 변경을 되돌리지 않는다.
