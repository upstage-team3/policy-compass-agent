# 정책나침반 개발 현황

최종 갱신: 2026-07-13

새 개발 세션은 먼저 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 읽는다.

## 현재 요약

정책나침반은 FastAPI와 LangGraph를 사용하는 청년정책·훈련·채용·창업지원 안내 Agent다. Docker, GitHub Actions CI/CD, Google Cloud Compute Engine 배포는 완료된 기반이다. 현재 개발 중심은 모든 외부 API의 실제 연결 검증과 LLM 중심 라우팅·응답 품질 개선이다.

## 진행 상태

| 영역 | 상태 | 현재 기준 |
| --- | --- | --- |
| Docker | 완료 | Multi-stage 이미지와 Compose 구성 완료 |
| CI/CD | 완료 | PR CI, main CI, GHCR build, GCE 자동 배포 성공 이력 |
| Google Cloud | 완료 | GCE 배포와 외부 `/api/health` 성공 이력 |
| LLM Router | 2차 완료 | Solar가 `action`, `response_mode`, `request_kind`, `search_query` 생성 |
| Conversation | 2차 완료 | 일반 대화·검색 없는 설명·범위 밖 응답을 단일 노드로 처리 |
| 프로필 추출 | 1차 완료 | Solar 우선, 실패 시 규칙 기반 추출 |
| Tool 선택 | 2차 완료 | LLM이 선택한 데이터 Tool 하나만 호출 |
| 응답 생성 | 2차 완료 | grounded LLM composer와 템플릿 fallback 분리 |
| 온통청년 | live 검증 완료 | `apiKeyNm`, `pageNum`, `pageSize`, `plcyNm` JSON API와 실제 3건 확인 |
| 고용24 훈련 | live 검증 완료 | 실데이터 3건과 상세 URL 확인 |
| 고용24 채용 | live 검증 완료 | 허용된 채용행사·공채속보·공채기업정보 3종 확인 |
| 기업마당 | live 검증 완료 | `jsonArray`·신청기간·해시태그 정규화 후 3건 확인 |
| SSE | 1차 완료 | `status`, `token`, `done`, `error`; 유형별 status는 미완료 |
| 테스트 | 통과 | Ruff 통과, pytest `53 passed` |

## Agent 아키텍처

```text
Router LLM + RoutingDecision
├─ RESPOND -> Conversation Node
└─ SEARCH
   -> Profile Extractor
   -> Missing Slot
   -> request_kind별 Tool 하나
   -> Scorer(정책 후보)
   -> Grounded Response Composer
-> Guardrail
```

## 핵심 기술 결정

- LLM 판단이 정상이라면 키워드 규칙으로 덮어쓰지 않는다.
- 키워드와 정규식은 `app/graph/fallbacks.py`에만 둔다.
- LLM JSON은 `app/graph/contracts.py`의 Pydantic 모델로 검증한다.
- Tool 검색어는 Router의 `search_query`를 우선 사용한다.
- 외부 API별 Tool을 동시에 무차별 호출하지 않는다.
- 후보 데이터에 없는 정책, 과정, 기업, 금액, 날짜, 링크를 생성하지 않는다.
- 외부 API 장애는 빈 결과 또는 명시적인 안내로 처리한다.
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
| `app/repositories/youthcenter.py` | 온통청년 API |
| `app/repositories/work24_training.py` | 고용24 훈련 API |
| `app/repositories/work24_recruitment.py` | 고용24 채용 보조 API |
| `app/repositories/policy.py` | 기업마당 API |
| `app/api/routes/chat.py` | 동기 채팅과 SSE API |

## 남은 주요 위험

1. 멀티턴 프로필의 `interest_fields`가 새 관심 분야와 기존 분야를 무조건 합친다.
2. SSE 상태 메시지가 아직 질문 유형과 무관하게 동일하다.
3. SSE는 실제 LLM token stream이 아니라 완성된 답변을 청크로 나눈다.
4. MemorySaver는 프로세스 재시작과 다중 인스턴스를 지원하지 않는다.

## 현재 완료 조건

- [x] 단일 Conversation Node와 Solar 호출
- [x] LLM 중심 의도·Tool·검색어 계획
- [x] fallback 규칙 모듈 격리
- [x] grounded 응답 컴포저 분리
- [x] Tool 단일 선택
- [x] Ruff와 pytest 53개 통과
- [x] Upstage, 온통청년, 고용24 훈련·허용 채용 3종, 기업마당 Repository live 검증
- [ ] 외부 API 5종 Agent 전체 경로 QA
- [ ] 질문 유형별 SSE 상태 문구
- [ ] 멀티턴 관심 분야 전환 처리
- [ ] 리팩터링 변경분 CI/CD와 GCE 회귀 확인
