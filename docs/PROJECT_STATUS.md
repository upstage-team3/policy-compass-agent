# 정책나침반 개발 현황

최종 갱신: 2026-07-13

새 개발 세션은 먼저 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 읽는다.

## 현재 요약

정책나침반은 FastAPI와 LangGraph를 사용하는 청년정책·훈련·채용·창업지원 안내 Agent다. Docker, GitHub Actions CI/CD, Google Cloud Compute Engine 배포는 완료된 기반이다. 현재는 LLM 중심 라우팅에 Supabase 멀티턴 메모리를 연결해 조건 확인, 검색 재개, 일반 대화 문맥을 개선한 상태다.

## 진행 상태

| 영역 | 상태 | 현재 기준 |
| --- | --- | --- |
| Docker | 완료 | Multi-stage 이미지와 Compose 구성 완료 |
| CI/CD | 완료 | PR CI, main CI, GHCR build, GCE 자동 배포 성공 이력 |
| Google Cloud | 완료 | GCE 배포와 외부 `/api/health` 성공 이력 |
| LLM Router | 3차 완료 | 최근 대화와 미완료 요청을 보고 `resume_pending`까지 결정 |
| Conversation | 3차 완료 | 단일 노드 처리와 최근 8개 메시지 문맥 사용 |
| 프로필 추출 | 3차 완료 | 최근 문맥을 참조하고 명시된 정책 분야만 저장 |
| Tool 선택 | 2차 완료 | LLM이 선택한 데이터 Tool 하나만 호출 |
| 조건 확인 | 3차 완료 | 청년정책 분야별 조건 질문과 원래 검색 계획 보존 |
| 응답 생성 | 4차 완료 | 일반 텍스트 정리, 실제 누락 정보 안내, 중복 자격 문구 제거 |
| 대화 메모리 | 1차 완료 | Supabase 최근 대화·프로필·pending 저장/복원 live 성공 |
| 온통청년 | live 검증 완료 | JSON API, 지역·사업 종료일 필터, 구체 검색어 보존을 실제 검증 |
| 고용24 훈련 | live 검증 완료 | 실데이터 3건과 상세 URL 확인 |
| 고용24 채용 | live 검증 완료 | 허용된 채용행사·공채속보·공채기업정보 3종 확인 |
| 기업마당 | live 검증 완료 | `jsonArray`·신청기간·해시태그 정규화 후 3건 확인 |
| SSE | 1차 완료 | `status`, `token`, `done`, `error`; 유형별 status는 미완료 |
| 테스트 | 통과 | Ruff 통과, pytest `78 passed` |

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
- 일반 채팅 UI에는 Markdown 기호와 형식적 답변 머리말을 남기지 않는다.
- 외부 API 장애는 빈 결과 또는 명시적인 안내로 처리한다.
- 부족한 조건을 물을 때 원래 요청과 검색어를 `pending_request`로 보존한다.
- 포괄 청년정책 문의는 공식 5개 분야를 묻고 일자리를 기본값으로 추정하지 않는다.
- 취업 상태는 일자리 정책에서만 필수로 묻고 다른 청년정책 분야에는 강제하지 않는다.
- Supabase에는 최근 8개 메시지, 구조화 프로필, 미완료 요청만 문맥으로 불러온다.
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
| `app/repositories/chat_memory.py` | Supabase 대화 메모리 저장/복원과 민감정보 마스킹 |
| `app/repositories/youthcenter.py` | 온통청년 API |
| `app/repositories/work24_training.py` | 고용24 훈련 API |
| `app/repositories/work24_recruitment.py` | 고용24 채용 보조 API |
| `app/repositories/policy.py` | 기업마당 API |
| `app/api/routes/chat.py` | 동기 채팅과 SSE API |
| `data/chat_memory_schema.sql` | 대화 메모리 테이블과 RLS 스키마 |

## 남은 주요 위험

1. `session_id`는 난수 UUID를 전제로 하지만 로그인 기반 소유권 검증이 없다.
2. 대화 로그 보존 기간과 사용자 삭제 기능이 아직 없다.
3. 같은 세션의 동시 요청에 대한 충돌 제어가 없다.
4. SSE 상태 메시지가 질문 유형과 무관하고 실제 LLM token stream이 아니다.
5. Supabase 장애 시 현재 프로세스 대화는 가능하지만 재시작 후 복원은 보장되지 않는다.

## 현재 완료 조건

- [x] 단일 Conversation Node와 Solar 호출
- [x] LLM 중심 의도·Tool·검색어 계획
- [x] fallback 규칙 모듈 격리
- [x] grounded 응답 컴포저 분리
- [x] Tool 단일 선택
- [x] Ruff와 pytest 78개 통과
- [x] Upstage, 온통청년, 고용24 훈련·허용 채용 3종, 기업마당 Repository live 검증
- [ ] 외부 API 5종 Agent 전체 경로 QA
- [ ] 질문 유형별 SSE 상태 문구
- [x] 멀티턴 관심 분야 전환과 원래 검색 요청 재개
- [x] Supabase 대화·프로필·미완료 요청 저장/복원
- [ ] 리팩터링 변경분 CI/CD와 GCE 회귀 확인
