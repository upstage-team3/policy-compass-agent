# Policy Compass Daily Todo

Last updated: 2026-07-13
Current day: Project Day4 completed / Day5 preparation

## 현재 기준선

- [x] 최신 main: `a89d1e3`
- [x] 작업 트리 정리 상태 확인
- [x] Ruff lint/format 통과
- [x] pytest `88 passed`
- [x] React 프런트엔드 프로덕션 빌드 통과
- [x] 프런트엔드 저장·복원 회귀 테스트 `4 passed`
- [x] 최신 main GitHub Actions CI/CD 성공
- [x] GCE 자동 배포 작업 내부 `/api/health` 성공

## 오늘의 핵심 목표

자동 배포까지 완료된 최신 버전을 외부 환경에서 수동 회귀 검증하고, 발표에 사용할 핵심 Agent 경로를 안정화한다.

## P0. 배포본 수동 회귀

- [ ] 외부 `/` 접속과 최신 React UI 확인
- [ ] 외부 `/api/health` 200 확인
- [ ] 외부 `/docs` 접속 확인
- [ ] 같은 `session_id`의 대화 저장·복원 확인

## P1. Agent 전체 경로 QA

- [x] 일반 고민: `RESPOND/general`, Tool 미호출
- [x] 청년정책: `youth_policy` 단일 호출
- [ ] 훈련: `training` 단일 호출과 검색어 확인
- [ ] 채용: `recruitment` 단일 호출과 제한 안내 확인
- [ ] 창업: `business` 단일 호출 확인
- [ ] 모든 검색 답변에서 후보 밖 정책명·금액·날짜·링크 미생성 확인

## P2. 대화와 UI 품질

- [x] Router 결과별 SSE `status` 문구 분리
- [x] 새로고침 뒤 채팅 목록·메시지·정책 카드·활성 채팅 복원
- [x] UUID 세션 유지로 새로고침 뒤 멀티턴 문맥 재개
- [x] 브라우저 저장 전 민감정보 마스킹과 20개 채팅·50개 메시지 보존 한도
- [x] 개별 채팅 삭제와 전체 로컬 기록 삭제
- [ ] SSE에서 정책·훈련·채용·창업 응답 표시 확인
- [ ] API 오류 시 빈 말풍선 없이 사용자 안내 확인
- [x] Router 평가 질문과 기대 결과 표 확장

## P3. 발표 준비

- [ ] 핵심 데모 시나리오 2개 확정
- [ ] 외부 API 장애 fallback 시나리오 1개 확정
- [ ] 발표자료 초안 작성
- [ ] 백업 데모 영상 준비

## Day5 상세 문서

- [실행 TODO](docs/day5/TODO.md)
- [Router·Agent 회귀 평가표](docs/day5/ROUTER_EVALUATION.md)
- [Langfuse 수업 실습 가이드](docs/day5/LANGFUSE_CLASS_GUIDE.md)

## 후속 운영 과제

- [ ] 로그인 기반 `session_id` 소유권 검증
- [x] 브라우저 표시 기록 보존 한도와 사용자 삭제 기능
- [ ] Supabase 서버 로그 보존 기간과 인증 사용자 삭제 API
- [ ] 같은 세션의 동시 요청 충돌 제어
- [ ] Supabase 지연·실패율 운영 지표
- [ ] 실제 LLM token streaming

## 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```
