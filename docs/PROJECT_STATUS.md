# 정책나침반 개발 현황

최종 갱신: 2026-07-14

새 개발 세션은 먼저 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 읽는다.

## 현재 요약

정책나침반은 FastAPI와 LangGraph를 사용하는 청년정책·훈련·채용·창업지원 안내 Agent다. Docker, GitHub Actions CI/CD, Google Cloud Compute Engine 배포는 완료된 기반이다. LLM 중심 라우팅과 Supabase 멀티턴 메모리, React 채팅 UI까지 `main`에 통합됐고, 로컬에서는 전국 지역 정규화·기업마당 지역/자격 교차 검증·근거 기반 스코어링까지 검증했다.

## 진행 상태

| 영역 | 상태 | 현재 기준 |
| --- | --- | --- |
| Docker | 완료 | Multi-stage 이미지와 Compose 구성 완료 |
| CI/CD | 완료 | `a89d1e3` main CI와 후속 CD 성공(2026-07-13) |
| Google Cloud | 완료 | 최신 이미지 GCE 자동 배포와 배포 작업 내 `/api/health` 성공 |
| React UI | 2차 완료 | 새로고침 대화 복원, UUID 유지, 개별·전체 삭제, 프로덕션 빌드 통과 |
| LLM Router | 3차 완료 | 최근 대화와 미완료 요청을 보고 `resume_pending`까지 결정 |
| Conversation | 3차 완료 | 단일 노드 처리와 최근 8개 메시지 문맥 사용 |
| 프로필 추출 | 3차 완료 | 최근 문맥을 참조하고 명시된 정책 분야만 저장 |
| Tool 선택 | 2차 완료 | LLM이 선택한 데이터 Tool 하나만 호출 |
| 조건 확인 | 3차 완료 | 청년정책 분야별 조건 질문과 원래 검색 계획 보존 |
| 응답 생성 | 5차 완료 | 정확/전국 우선, 인접 결과 별도 표시, 거리·거주요건 안내 |
| 대화 메모리 | 3차 완료 | 표시 기록·Supabase 문맥 복원 + 지역·나이 기본 프로필의 새 채팅 재사용 |
| 온통청년 | live 검증 완료 | 전국 지역 코드·오표기·만료 필터 + 요청 헤더 안정화·5xx 재시도·장애 구분 |
| 고용24 훈련 | live 검증 완료 | 실데이터 3건과 상세 URL 확인 |
| 고용24 채용 | live 검증 완료 | 허용된 채용행사·공채속보·공채기업정보 3종 확인 |
| 기업마당 | live 검증 완료 | 16/17개 지역 태그 형식, 지자체 소재지·이전 조건, 사업자 등록 조건, 관심 분야 순위 확인 |
| SSE | 2차 완료 | Router 결과별 상태 문구를 백엔드와 React 타이핑 영역에 연결 |
| Langfuse | 연결 완료 | LangGraph callback, 세션·태그·메타데이터, 종료 시 flush 적용 |
| 테스트 | 통과 | Ruff/포맷, pytest `164 passed`, 프런트 저장 회귀 `8 passed`, production build 통과 |

## Agent 아키텍처

```text
Supabase Memory Load
-> Router LLM + RoutingDecision
├─ RESPOND -> Conversation Node
└─ SEARCH
   -> Profile Extractor
   -> Missing Slot
   -> request_kind별 Tool 하나
   -> Scorer(정책 후보)
   -> Grounded Response Composer
-> Guardrail
-> Supabase Memory Save
```

## 핵심 기술 결정

- LLM 판단이 정상이라면 키워드 규칙으로 덮어쓰지 않는다.
- 키워드와 정규식은 `app/graph/fallbacks.py`에만 둔다.
- LLM JSON은 `app/graph/contracts.py`의 Pydantic 모델로 검증한다.
- Tool 검색어는 Router의 `search_query`를 우선 사용한다.
- 외부 API별 Tool을 동시에 무차별 호출하지 않는다.
- 후보 데이터에 없는 정책, 과정, 기업, 금액, 날짜, 링크를 생성하지 않는다.
- 신청 정보 누락은 실제 API null 필드만 `data_notice`로 전달하고 내부 필드명을 노출하지 않는다.
- 구체 검색어 결과가 없으면 무관한 넓은 분야 결과로 대체하지 않는다.
- 월세·전세·금융처럼 하위 유형이 명시된 검색은 상위 분야나 인접 지역 결과로 완화하지 않는다.
- 지역 정정 표현은 전환 표현 뒤의 새 지역을 우선하며, 시·도 조건만으로 시·군·구 전용 정책을 추천하지 않는다.
- 정확 지역과 전국 후보가 있으면 다른 지역 결과를 섞지 않는다.
- 정확 지역과 전국 후보가 모두 없을 때만 가까운 시·도 결과 최대 3건을 `nearby_reference`로 제공한다.
- 인접 거리는 도로 거리가 아닌 사용자 지역과 시·도 대표 좌표 간 직선거리임을 명시한다.
- 지역·연령·취업·창업·사업자 조건의 명시적 불일치는 점수와 무관하게 추천에서 제외한다.
- 점수는 전체 평가 기준 대비 확인된 일치 근거로 계산하고, 알 수 없는 조건은 적합으로 간주하지 않는다.
- 실제 비교 가능한 범위는 근거 확인률로 분리하며 점수를 신청 가능성이나 선정 확률로 표현하지 않는다.
- 기업마당의 전 지역 태그는 소재지·본사 이전·전입 조건과 교차 검증하고, 명시적 `지역제한 없음`은 전국으로 우선 판정한다.
- 창업 질문의 관심 분야는 유사어를 포함해 관련 후보를 우선하고, 사업자등록 상태가 명시적으로 충돌하는 공고는 제외한다.
- 현재 발화에 없는 시·도를 LLM이 상식으로 보완하지 못하게 공식 지역 표현으로 다시 검증한다.
- 동명이인 시·군·구는 시·도를 확인할 때까지 검색하지 않는다.
- 일반 채팅 UI에는 Markdown 기호와 형식적 답변 머리말을 남기지 않는다.
- 민감 식별정보는 브라우저 전송 전과 백엔드 그래프 실행 전 두 단계에서 차단하고, 차단 요청은 LLM·외부 API·Langfuse에 전달하지 않는다.
- Supabase 메시지·프로필·미완료 요청과 브라우저 표시 기록에는 민감정보 원문 대신 삭제 표식만 저장한다.
- 외부 API 장애는 빈 결과 또는 명시적인 안내로 처리한다.
- 부족한 조건을 물을 때 원래 요청과 검색어를 `pending_request`로 보존한다.
- 포괄 청년정책 문의는 공식 5개 분야를 묻고 일자리를 기본값으로 추정하지 않는다.
- 취업 상태는 일자리 정책에서만 필수로 묻고 다른 청년정책 분야에는 강제하지 않는다.
- Supabase에는 최근 8개 메시지, 구조화 프로필, 미완료 요청만 문맥으로 불러온다.
- 브라우저 표시 기록은 `policy-compass.chat-state.v1`에 최근 채팅 20개·채팅별 메시지 50개까지만 저장하고 민감정보를 먼저 마스킹한다.
- React `Chat.id`는 UUID로 만들고 같은 값을 백엔드 `session_id`로 재사용해 새로고침 뒤 멀티턴 문맥을 잇는다.
- 거주 지역과 만 나이만 브라우저 기본 프로필로 분리해 새 채팅에 전달하고, 채팅별 Supabase 프로필을 우선한다.
- 기본 프로필은 다른 기기와 공유하지 않으며 전체 로컬 기록 삭제 시 함께 삭제한다.
- 광범위한 현재 정책 목록을 묻는 `정책을 알려줘`는 추천 검색이고, 특정 정책명의 개념·자격 설명만 explain이다.
- 외부 API가 실패했을 때 빈 결과로 축약하지 않고 실제 무결과와 장애 안내를 구분한다.
- `SUPABASE_KEY`는 RLS를 우회하는 서버용 secret/service_role 키만 사용한다.
- 테스트는 외부 네트워크 없이 통과해야 한다.

## 주요 파일

| 파일 | 역할 |
| --- | --- |
| `app/graph/contracts.py` | Router의 구조화된 출력 계약 |
| `app/graph/fallbacks.py` | 키워드·정규식 장애 fallback |
| `app/graph/nodes.py` | LangGraph 노드 orchestration |
| `app/graph/response_composer.py` | LLM 응답과 결정론적 템플릿 |
| `app/graph/graph.py` | 노드 연결과 MemorySaver |
| `app/graph/state.py` | Agent 상태 계약 |
| `app/core/privacy.py` | 민감 식별정보 탐지·마스킹·입력 차단 응답 |
| `app/core/administrative_regions.py` | 2026-07-14 현존 시·군·구 300개와 공식 5자리 코드 |
| `app/core/regions.py` | 지역명·법정코드·기업마당 태그 정규화와 근접 거리 |
| `app/core/relevance.py` | 관심 분야 유사어와 정책 관련성 판정 |
| `app/graph/scoring.py` | 근거 기반 적합도와 하드 불일치 판정 |
| `app/repositories/chat_memory.py` | Supabase 대화 메모리 저장/복원과 민감정보 마스킹 |
| `app/repositories/youthcenter.py` | 온통청년 API |
| `app/repositories/work24_training.py` | 고용24 훈련 API |
| `app/repositories/work24_recruitment.py` | 고용24 채용 보조 API |
| `app/repositories/policy.py` | 기업마당 API |
| `app/api/routes/chat.py` | 동기 채팅과 SSE API |
| `frontend/src/lib/chatStorage.ts` | 버전이 있는 로컬 채팅 저장·복원, 보존 한도, 민감정보 마스킹 |
| `frontend/src/components/PolicyCard.tsx` | 정책 지역 범위·인접 참고 배지·거리 표시 |
| `data/chat_memory_schema.sql` | 대화 메모리 테이블과 RLS 스키마 |

## 남은 주요 위험

1. `session_id`는 난수 UUID를 전제로 하지만 로그인 기반 소유권 검증이 없다.
2. 브라우저 표시 기록 삭제는 구현됐지만 Supabase 서버 로그의 보존 기간·사용자 삭제 API는 아직 없다.
3. 같은 세션의 동시 요청에 대한 충돌 제어가 없다.
4. SSE 상태 문구는 유형별로 표시하지만 실제 LLM token stream은 아니다.
5. Supabase 장애 시 현재 프로세스 대화는 가능하지만 재시작 후 복원은 보장되지 않으며, 이번 로컬 브라우저 검증에서 문맥 조회 `401`이 1회 보여 키·RLS 재확인이 필요하다.
6. 배포 자동화는 성공했지만 외부 `/`, `/docs`와 대표 질문의 수동 회귀 결과는 아직 기록되지 않았다.
7. 전국 시·군·구 코드는 지원하지만 근접 거리는 일부 검증 좌표 외에는 시·도 대표 좌표를 사용하는 근사치다.
8. 행정구역 개편 시 `administrative_regions.py` 스냅샷을 행정표준코드 현존 목록과 다시 비교해야 한다.
9. 새 채팅 기본 프로필은 현재 브라우저에만 저장되므로 로그인 전에는 기기 간 동기화되지 않는다.

## 현재 완료 조건

- [x] 단일 Conversation Node와 Solar 호출
- [x] LLM 중심 의도·Tool·검색어 계획
- [x] fallback 규칙 모듈 격리
- [x] grounded 응답 컴포저 분리
- [x] Tool 단일 선택
- [x] Ruff와 pytest 164개 통과
- [x] Upstage, 온통청년, 고용24 훈련·허용 채용 3종, 기업마당 Repository live 검증
- [ ] 외부 API 5종 Agent 전체 경로 QA
- [x] 질문 유형별 SSE 상태 문구와 React UI 연결
- [x] 멀티턴 관심 분야 전환과 원래 검색 요청 재개
- [x] Supabase 대화·프로필·미완료 요청 저장/복원
- [x] 새로고침 뒤 채팅 목록·메시지·정책 카드·활성 채팅 복원
- [x] UUID 세션 유지, 전송 전·서버 입력 단계 민감정보 차단, 개별·전체 기록 삭제
- [x] 최신 main 변경분 CI/CD와 GCE 내부 헬스체크 회귀 확인
- [x] 성남시 지역 호출·정확/전국 우선·인접 지역 참고 결과 회귀 확인
- [x] 전체 기준 점수·근거 확인률·하드 불일치·만료 신청기간 필터 회귀 확인
- [x] 전국 현존 시·군·구 300개 코드 복원과 기업마당 16/17개 지역 태그 회귀 확인
- [x] 기업마당 소재지·이전·사업자등록 교차 검증과 관심 분야 우선순위 확인
- [x] 동명이인 지역 확인 질문과 멀티턴 검색 재개 확인
- [x] 기존 지역·나이를 새 채팅에서 재사용하고 광범위한 주거 정책 요청을 추천 검색으로 처리
- [x] 온통청년 5xx 재시도와 실제 무결과/호출 장애 안내 분리
- [ ] 배포본 외부 `/`, `/docs`와 API별 대표 질문 수동 QA
