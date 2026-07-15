# 정책나침반 문서 안내

최종 갱신: 2026-07-15

코드와 테스트가 최종 사실 기준이다. 문서간 내용이 다르면 아래 순서로
현재 계약을 확인한다.

## 현재 기준 문서

| 문서 | 용도 |
| --- | --- |
| [개발 인수인계](DEVELOPMENT_HANDOFF.md) | 현재 제품 범위, 8-node 그래프, 세션·응답·배포 불변식 |
| [개발 현황](PROJECT_STATUS.md) | 완료된 구현, 주요 기술 결정, 남은 위험 |
| [다음 개발 작업](NEXT_ACTIONS.md) | 우선순위별 미완료 작업과 회귀 질문 |
| [API Tool 계약](API_TOOL_SCHEMA_DESIGN.md) | 세 활성 소스, `SearchOutcome`, 입출력·gate 계약 |
| [API·배포 메모](API_AND_DEPLOYMENT_NOTES.md) | 환경변수, API 요약, readiness, GCP 배포 구성 |
| [배포 회귀 가이드](day4/DEPLOYMENT_RUNBOOK.md) | exact SHA·GHCR digest 배포, smoke, rollback 절차 |
| [로드맵](ROADMAP.md) | 완료 이력과 중장기 grounding·보안·운영 방향 |

## 현재 MVP 한 눈에 보기

- 활성 검색: 온통청년 청년정책, 고용24 국민내일배움카드 훈련과정,
  고용24 채용행사·공채속보 보조정보
- 온통청년 분야: 일자리, 주거, 교육·직업·훈련, 금융·복지·문화, 참여·기반
- 범위 밖: 창업·사업자·소상공인 지원 검색, 기업마당·K-Startup 링크 안내
- 그래프: `prepare_request`, `direct_response`, `retrieve`, `assess_evidence`,
  `rewrite_query`, `build_answer`, `verify_answer`, `finalize`
- 시간 예산: turn 60초, LLM 8초, source 10초, Repository HTTP 9초
- 추천 계약: 점수 없는 결정론적 gate, 최대 3개 카드, 공식 원문 재확인

## 설계·감사 문서

아래 문서는 설계 결정의 근거와 과거 문제를 보존한다. `현재` 코드 설명으로
읽지 않고 상단의 현재 기준 문서와 함께 사용한다.

- [통합 구조 이슈·개선 기준](INTEGRATED_ARCHITECTURE_ISSUES.md)
- [시스템 아키텍처 감사·리팩터링 계획](SYSTEM_ARCHITECTURE_AUDIT_AND_REFACTOR_PLAN.md)
- [Claude 아키텍처 피어 리뷰](CLAUDE_ARCHITECTURE_PEER_REVIEW.md)
- [개발 일지](DAILY_LOG.md)
- [초기 협업 규칙](COLLABORATION.md)
- [Day 4 자료](day4/README.md)
- [Day 5 자료](day5/TODO.md)

## 문서 갱신 규칙

1. 제품 범위·노드·세션·API 계약이 바뀌면 `DEVELOPMENT_HANDOFF.md`와
   `PROJECT_STATUS.md`를 같이 갱신한다.
2. 완료·미완료 상태가 바뀌면 `NEXT_ACTIONS.md`의 체크박스를 조정한다.
3. 환경변수·health·CI/CD가 바뀌면 `API_AND_DEPLOYMENT_NOTES.md`와
   `day4/DEPLOYMENT_RUNBOOK.md`를 같이 갱신한다.
4. 실제 정책명·금액·날짜·자격·URL을 문서 예시로 임의 생성하지 않는다.
5. 실제 API 키·인증 URL·authorization header를 문서와 로그에 남기지 않는다.
