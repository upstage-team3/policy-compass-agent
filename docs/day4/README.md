# Project Day4 개발 실행 가이드

작성일: 2026-07-13  
프로젝트: 정책나침반  
오늘의 주제: 배포 완료 환경에서 전체 API 실연동과 응답 품질 개선

현재 코드 기준과 다음 개발 순서는 [../DEVELOPMENT_HANDOFF.md](../DEVELOPMENT_HANDOFF.md)를 우선한다.

## 오늘의 목표

Docker 구성, GitHub Actions CI/CD, Google Cloud 배포와 헬스체크는 3일차까지 완료했다. 오늘은 이 완료된 배포 환경을 기반으로 Upstage Solar, 온통청년, 고용24 훈련과정, 고용24 채용 보조 정보, 기업마당을 실제 연결하고 응답·정규화·Agent·SSE/UI까지 확인한다. 동시에 3일차에서 이월된 일반 대화 LLM 적용, 질문 유형별 SSE 상태 문구, 라우팅 의도 분류, 배포본 반복 QA를 완료한다.

```text
완료된 CI/CD·Google Cloud 배포 환경 확인
-> 5개 외부 API 단독 호출 및 응답 확인
-> 정규화·Tool·Agent 연결
-> 이월 기능 개선과 SSE/UI QA
-> 로컬 테스트와 선택적 Docker 회귀 확인
-> 기존 CI/CD를 통한 변경분 자동 배포
-> Google Cloud 배포본 핵심 시나리오 QA
-> URL·화면·테스트 결과 증빙 정리
```

## 시작 상태

| 영역 | 상태 | 근거 및 주의점 |
| --- | --- | --- |
| 소스 코드 | Day4 구현 완료 | LLM 라우팅 리팩터링과 외부 API 연동 반영 |
| Python 환경 | 준비 완료 | Python 3.11, Ruff lint/format, pytest `78 passed` |
| 로컬 환경변수 | 준비 완료 | `.env`에 필요한 API 키가 설정되어 있으며 값은 문서와 GitHub에 기록하지 않음 |
| 외부 API 키 | 5종 설정 완료 | Upstage, 온통청년, 고용24 훈련·채용, 기업마당 키의 존재를 값 노출 없이 확인함 |
| 핵심 API | 5개 계통 검증 완료 | Solar·온통청년·고용24 훈련·고용24 허용 채용 3종·기업마당 live 성공 |
| Docker 구성 | 완료 | Multi-stage 이미지와 Compose 구성을 사용해 Google Cloud에 배포 완료 |
| CI/CD | 완료 | PR CI 통과, merge, `main` CI 성공 후 CD 자동 배포까지 동작 확인 |
| Google Cloud 배포 | 완료 | GCE VM의 서비스 배포와 외부 `/api/health` 헬스체크 성공 |

## 3일차에서 이어받은 작업

1. 일반 대화 생성 노드에서 LLM 사용을 명확히 적용한다. **완료**
2. SSE 상태 문구를 정책 추천·훈련과정·채용 정보·일반 설명 등 질문 유형별로 다르게 전송한다. **Day5 사전 작업으로 완료**
3. 라우팅 의도 분류를 고도화해 설명형 질문과 실제 검색·추천 질문을 더 정확히 구분한다. **1차 완료**
4. 배포된 서비스에서 핵심 시나리오를 반복 테스트하고 응답 품질 문제를 보완한다.

3일차 이슈 기록에 있던 멀티턴 관심 분야 누적 문제도 함께 확인한다. 새 분야 요청 시 기존 관심 분야를 무조건 누적하지 않고, 전환 의도를 확인하거나 현재 요청을 우선하도록 개선 방향을 정한다.

## 오늘 연결할 API

| API | 오늘의 검증 범위 | 성공 기준 |
| --- | --- | --- |
| Upstage Solar | Router/Profile/Conversation/Response LLM 호출 | 실제 LLM 응답과 실패 시 규칙 기반 fallback 확인 |
| 온통청년 | 청년정책 목록 JSON 호출 및 `YouthPolicyItem` 정규화 | 정책명·대상·기간·신청 방법·원문 링크 확인 |
| 고용24 훈련과정 | 지역·직무 기반 과정 검색 | 과정명·기관·지역·기간·비용·상세 URL 확인 |
| 고용24 채용 | 개인키 허용 범위의 채용행사·공채속보·공채기업정보 | 허용 endpoint 응답 확인, 제한 endpoint는 탐색 가이드로 처리 |
| 기업마당 | 창업·사업자 질문의 지원사업 보조 검색 | 실제 응답 정규화와 빈 필드·원문 링크 처리 확인 |

각 API는 먼저 Repository 수준에서 단독 호출한 뒤 Tool, Agent, SSE/UI 순서로 연결한다. API 키와 원문 응답의 민감한 값은 로그·문서에 기록하지 않는다.

## 오늘의 우선순위

### P0. 모든 API 실연동

- 5개 API 키 설정 여부를 값 노출 없이 확인
- 각 Repository에서 실제 API 호출과 응답 형식 확인
- XML/JSON 필드를 내부 스키마로 정규화
- 빈 필드, 결과 없음, 권한 제한, timeout을 안전하게 처리
- Tool과 Agent가 실제 후보만 사용하고 원문 링크를 포함하는지 확인
- API별 단위 테스트와 수동 QA 결과 기록

### P1. 3일차 이월 품질 개선

- [완료] 일반 대화 생성 노드의 LLM 사용 경로 확인 및 보강
- [완료] 요청 유형별 SSE 상태 문구 적용
- [완료] `RESPOND/SEARCH` 기반 `RoutingDecision`과 통합 Conversation Node 적용
- 멀티턴에서 관심 분야가 잘못 누적되는지 확인
- 관련 단위·회귀 테스트 추가

### P2. 완료된 배포 환경에서 회귀 확인

- 3일차 GCE 외부 URL과 `/api/health` 재확인
- 필요할 때만 Docker Desktop으로 맥북의 컨테이너 재현성 확인
- 구현 변경분이 기존 CI/CD를 통해 Google Cloud에 자동 반영되는지 확인
- 실제 API 키가 GitHub Secrets와 GCE 환경변수로 전달되는지 이름 기준으로 점검
- 공개 URL, CI/CD 화면, 핵심 QA 결과를 증빙으로 정리

### P3. 배포본 사용자 QA

- 훈련과정 검색, 조건 부족 되묻기, 일반 설명, 채용 보조 질문을 외부 URL에서 검증
- SSE의 `status`, `token`, `done`, `error` 이벤트와 UI 표시 확인
- 후보 데이터 밖 사실 생성 여부와 상세 URL 제공 여부 확인
- 로그에 API 키나 민감정보가 출력되지 않는지 확인

DB 도입, 전체 RAG 구조 변경, 발표자료 제작은 오늘 P0·P1·P2 완료 전에는 시작하지 않는다.

## 권장 작업 순서

1. 3일차 배포 URL과 CI/CD 성공 상태를 기준선으로 확인한다.
2. 5개 API를 Repository 수준에서 하나씩 실제 호출해 응답과 권한 범위를 기록한다.
3. normalizer와 Tool을 보강하고 Agent·SSE/UI에서 API별 결과를 확인한다.
4. 완료된 일반 대화 LLM·라우팅을 기준으로 SSE 상태 문구와 멀티턴 관심 분야를 개선한다.
5. Python 3.11에서 Ruff와 pytest를 실행한다.
6. Docker Desktop을 실행하고 맥북의 로컬 컨테이너에서 모든 API를 재검증한다.
7. 구현 변경의 CI/CD 재통과와 GCE 배포본 핵심 시나리오를 확인한다.
8. 공개 URL, API별 결과, CI/CD 화면, 문제와 해결 내용을 일일회고에 기록한다.

명령과 배포 절차는 [DEPLOYMENT_RUNBOOK.md](DEPLOYMENT_RUNBOOK.md), 테스트 질문과 멘토링 준비는 [QA_AND_MENTORING.md](QA_AND_MENTORING.md)를 따른다.

## 완료 기준

- [x] 일반 대화 생성 노드에서 LLM 사용 경로가 명확히 동작
- [x] Upstage Solar 실제 Router·Conversation 호출과 fallback 단위 테스트 확인
- [x] 온통청년 실제 정책 응답과 내부 스키마 매핑 확인
- [x] 고용24 훈련과정 실제 응답과 상세 URL 확인
- [x] 고용24 채용 개인키 허용 endpoint 및 제한 fallback 확인
- [x] 기업마당 실제 응답과 빈 필드·원문 링크 처리 확인
- [ ] 모든 API 결과가 Agent와 SSE UI에서 요청 유형에 맞게 표시
- [x] 질문 유형별 SSE 상태 문구 표시
- [x] 설명형 질문과 검색·추천 질문 라우팅 회귀 테스트 통과
- [x] Docker Multi-stage 이미지와 Docker Compose API/FE 구성 완료
- [x] 기본 GitHub Actions CI/CD 구축 및 자동 배포 성공
- [x] Google Cloud 배포와 외부 `/api/health` 헬스체크 성공
- [x] 최신 main `a89d1e3` 변경분이 기존 CI/CD를 통해 정상 반영
- [ ] 기존 Google Cloud 외부 URL에서 `/`, `/api/health`, `/docs` 회귀 확인
- [ ] 외부 URL에서 핵심 시나리오 2개 이상 정상 동작
- [x] `.env`가 Git에 추적되지 않고 실제 키가 로그·문서에 노출되지 않음
- [ ] 선택 LLMOps 항목으로 Retry·Fallback·Guardrail 중 현재 적용 상태와 증빙 정리
- [ ] 배포 URL과 검증 결과를 일일회고에 기록

## 중단 기준

다음 상황에서는 기능 개발을 멈추고 배포 문제부터 해결한다.

- 일반 대화·설명 질문이 잘못 검색 Tool로 라우팅됨
- SSE 상태 문구가 질문 유형과 맞지 않음
- Docker 이미지가 빌드되지 않음
- 컨테이너가 시작 직후 종료됨
- `/api/health`가 200을 반환하지 않음
- CI lint 또는 test가 실패함
- 기존 GCE 배포본이 더 이상 외부에서 접속되지 않음
- 배포 환경에 API 키가 전달되지 않아 핵심 시나리오가 모두 fallback으로만 동작함
- 실제 API 응답 필드가 정규화 스키마와 달라 잘못된 정보가 표시됨
- API 권한 제한이나 빈 결과를 임의 데이터로 보완함
