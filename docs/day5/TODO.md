# Project Day5 실행 TODO

> **역사 문서:** 2026-07-14 당시 체크리스트다. 현재 구조와 남은 작업은
> `../DEVELOPMENT_HANDOFF.md`와 `../NEXT_ACTIONS.md`를 기준으로 한다. 아래의 기업마당
> 검색 및 고정 테스트 개수는 현재 계약이 아니다.

날짜: 2026-07-14
목표: 핵심 Agent 경로 안정화, 예외 처리, 회귀 테스트, 증빙 확보

## 시작 기준선

- [x] LLM 중심 Router와 Tool 단일 선택 구조
- [x] 온통청년·고용24 훈련·허용 채용 3종·기업마당 live Repository 검증
- [x] Supabase 멀티턴 메모리와 조건 확인 후 검색 재개
- [x] Docker·GitHub Actions CI/CD·GCE 자동 배포
- [x] Ruff/pytest 78개와 React 프로덕션 빌드 통과

## P0. 유형별 SSE 상태 문구

- [x] 첫 상태를 중립적인 의도 확인 문구로 변경
- [x] Router 결과의 `request_kind`와 `missing_slots`로 후속 상태 문구 생성
- [x] 청년정책·훈련·채용·기업마당·일반 설명·범위 밖 문구 분리
- [x] React UI가 `status` 이벤트를 받아 타이핑 영역에 표시
- [x] 기존 정적 UI의 `status` 처리와 호환 유지
- [x] 상태 문구 매핑 회귀 테스트 추가

완료 기준: 질문 유형과 맞지 않는 공통 추천 문구가 표시되지 않는다.

## P1. 핵심 경로와 예외 처리 회귀

- [x] Docker 이미지가 React production build 결과를 `app/static`에 포함하도록 수정
- [x] Dockerfile의 React 빌드·복사 계약과 context 제외 항목 회귀 테스트 추가
- [ ] 외부 배포본 `/`, `/api/health`, `/docs` 수동 확인
- [ ] 로컬 Supabase 문맥 조회 `401` 1회 원인(키·RLS) 확인 후 서버 재시작 복원 재검증
- [ ] 훈련 질문이 `training` Tool 하나만 호출하는지 확인
- [ ] 채용 질문이 `recruitment` Tool 하나만 호출하고 권한 제한을 안내하는지 확인
- [ ] 창업 질문이 `business` Tool 하나만 호출하는지 확인
- [ ] 후보에 없는 정책명·금액·날짜·링크를 만들지 않는지 확인
- [x] Agent 예외가 SSE `error` 이벤트와 안전한 사용자 문구로 바뀌는 테스트 추가
- [x] fallback이 `클라우드 엔지니어`를 놓쳐 직무를 재질문하던 회귀 수정
- [x] 조건 확인 fallback의 잘못된 한국어 조사(`만 나이을`) 수정
- [x] React 새로고침 시 모든 채팅이 초기화되던 문제 수정
- [x] UUID 세션과 로컬 채팅 복원으로 새로고침 뒤 멀티턴 문맥 유지
- [x] 브라우저 저장 전 민감정보 마스킹, 20개 채팅·50개 메시지 제한
- [x] 개별 채팅·전체 기록 삭제와 새로고침 뒤 삭제 유지 확인
- [x] API 실패 또는 결과 없음 화면에서 빈 말풍선이 생기지 않는지 확인
- [x] 지역·나이 기본 프로필을 새 채팅에서 재사용하고 전체 기록 삭제 시 함께 제거
- [x] 광범위한 주거 정책 `알려줘` 요청을 추천 검색으로 처리
- [x] 온통청년 5xx 재시도와 실제 무결과/호출 장애 안내 분리

수동 QA 질문과 기대 결과는 [ROUTER_EVALUATION.md](ROUTER_EVALUATION.md)를 사용한다.

## P2. 전체 자동 검증

```bash
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

- [x] Ruff lint 통과
- [x] Ruff format check 통과
- [x] pytest `149 passed`
- [x] React production build 통과
- [x] 프런트 저장·복원 회귀 테스트 `7 passed`
- [x] `.env`가 Git 추적 대상이 아님을 확인

## P3. 증빙 캡처

- [x] 전체 테스트 통과 화면
- [x] React 프로덕션 빌드 통과 화면
- [x] 청년정책 조건 확인 상태 문구 화면
- [x] 훈련과정 검색 상태 문구 화면
- [x] 오류 fallback 또는 권한 제한 안내 화면
- [ ] 외부 배포본 `/api/health` 화면
- [ ] 선택: Langfuse Trace 화면

증빙 파일은 `docs/day5/evidence/`에 모으고, 공개 문서에는 API 키·인증 URL·사용자 민감정보를 넣지 않는다.

## Langfuse 수업 중 작업

코드와 키 입력은 미리 하지 않는다. 수업 중 [LANGFUSE_CLASS_GUIDE.md](LANGFUSE_CLASS_GUIDE.md)를 따라 프로젝트 생성, 환경변수 설정, Trace 1건 확인과 캡처만 수행한다.

## Day5 종료 조건

- [x] 핵심 시나리오 2개 이상 로컬 반복 재현
- [x] 로컬 검증 기준 치명적 오류 0건
- [x] 오류/예외 대응 증빙 1건 이상
- [x] 전체 자동 검증 통과
- [x] 로컬 필수 증빙 캡처 완료
- [ ] 5일차 일일회고의 진행률·링크·캡처 칸 최종 확정
