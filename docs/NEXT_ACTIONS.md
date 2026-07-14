# 다음 개발 작업

최종 갱신: 2026-07-14

세부 배경은 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 먼저 읽는다.

## P0. 외부 API live 연결 검증

- [x] Upstage Solar Router와 통합 Conversation Node 실제 호출
- [x] 온통청년 `getPlcy` JSON API와 `apiKeyNm` 인증, 정책 3건 정규화 확인
- [x] 온통청년 정책명 0건 재검색과 `zipCd` 거주지역 필터 추가
- [x] 행정표준코드 현존 시·군·구 300개를 온통청년 5자리 코드로 연결
- [x] 성남 `41130`, 해운대 `26350`, 전주 `52110` live 호출과 지방자치단체 사업의 전국 코드 오표기 교차 검증
- [x] 기업마당 16/17개 지역 태그 형식과 부산·전북 live 호출, 지역 태그 누락을 전국으로 추정하지 않음
- [x] 기업마당 전 지역 태그를 소재지·본사 이전·전입 조건으로 교차 검증하고 `지역제한 없음`을 전국으로 우선 판정
- [x] 예비/기창업·사업자등록 조건 구조화와 관심 분야 유사어 우선순위 적용
- [x] 정확 지역·전국 결과 부재 시에만 인접 시·도 결과 최대 3건 제공
- [x] 고용24 훈련 Repository 단독 호출과 상세 URL 회귀 확인
- [x] 고용24 채용은 허용 3개 endpoint만 호출하고 제한 endpoint를 호출하지 않음
- [x] 기업마당 Repository 단독 호출과 실제 JSON 필드 확인
- [x] API 오류 로그에 인증키가 포함된 URL/query string을 남기지 않도록 보완

검증 결과에는 HTTP 상태, 정규화 필드, 원문 링크, 제한 사유만 남기고 키 값은 기록하지 않는다.

## P1. Agent 전체 경로 QA

- [x] 일반 고민이 `RESPOND/general`로 분류되고 Tool을 호출하지 않는지 확인
- [x] 청년정책 질문이 `youth_policy`만 호출하는지 확인
- [ ] 훈련 질문이 `training`과 적절한 `search_query`를 만드는지 확인
- [ ] 채용 질문이 `recruitment`만 호출하는지 확인
- [ ] 창업 질문이 `business`만 호출하는지 확인
- [x] 검색 없는 설명과 공식 데이터가 필요한 설명을 `RESPOND/SEARCH`로 구분
- [ ] API 후보 밖 사실을 LLM이 생성하지 않는지 확인

## P2. 대화 품질

- [x] Router 결과에 따라 SSE `status` 메시지를 다르게 표시하고 React 타이핑 영역에 연결
- [x] `interest_fields`를 무조건 합치지 않고 현재 발화의 새 값으로 교체
- [x] 최근 대화와 미완료 검색 계획을 Router/Profile/Conversation에 전달
- [x] 조건 답변 뒤 원래 요청과 검색어로 Tool 검색 재개
- [x] 정책·훈련·채용·창업 유형별 필수 조건 확인
- [x] 고정 검색 실패 문구를 출처·검색어 기반 LLM 응답으로 교체
- [x] 새 관심 분야와 멀티턴 주거정책 요청 회귀 테스트 추가
- [x] 포괄 청년정책 문의에서 공식 5개 분야를 묻고 일자리 추정값을 폐기
- [x] 일자리 외 정책 분야에서 취업·창업 상태를 묻지 않도록 분기
- [x] 채팅 응답에서 Markdown·내부 필드명·형식적 머리말 제거
- [x] 실제 누락 신청 정보만 안내하고 자격 확인 문구 중복 제거
- [x] 종료된 온통청년 정책 제외 및 구체 검색어의 무관한 분야 완화 차단
- [x] 월세·전세·금융 하위 유형 무결과 시 상위 분야·인접 지역 대체 없이 무결과 안내
- [x] `경기도 말고 서울로` 지역 정정과 도 단위 조건의 시 전용 정책 오추천 차단
- [x] 종료된 신청기간 필터와 `0~0세` 연령 제한 없음 정규화
- [x] 전체 평가 기준 기반 점수와 근거 확인률 분리, 지역·연령·사업자 하드 불일치 제외
- [x] 인접 지역 결과를 점수 0점 참고 결과로 분리하고 거리·거주 요건 표시
- [x] 동명이인 시·군·구의 시·도 임의 추정 차단과 확인 질문 후 원래 검색 재개
- [x] LLM이 현재 발화에 없는 시·도를 보완하지 못하도록 결정론적 지역 검증 추가
- [x] 설명형·추천형·일반 대화 경계 fixture 추가
- [x] 새로고침 뒤 채팅 목록·메시지·정책 카드·활성 채팅 복원
- [x] UUID 세션 유지로 새로고침 뒤 멀티턴 주거정책 검색 재개
- [x] `청년 주거 지원 정책에 대해 알려줘`를 추천 검색으로 분류하고 지역·나이 기본값 재사용
- [x] 온통청년 브라우저형 헤더 제거, 5xx 재시도, 장애/무결과 안내 분리
- [x] Router 평가 질문과 기대 결과 표 작성

## P3. 대화 메모리 운영

- [x] Supabase `chat_logs`, `chat_sessions` 스키마와 RLS 적용
- [x] 최근 메시지 8개, 프로필, `pending_request` 저장·복원
- [x] 주민번호·외국인등록번호·연락처·이메일·계좌·카드 형태의 브라우저 전송 전 및 서버 입력 단계 차단
- [x] 민감정보 차단 요청의 LangGraph·LLM·외부 API·Langfuse 호출 방지와 구조화 메모리 재귀 마스킹
- [x] `SUPABASE_URL`, 서버용 secret/service_role `SUPABASE_KEY`를 CD에 전달
- [x] 실제 Supabase 저장·복원 smoke test
- [x] 브라우저 표시 기록의 민감정보 마스킹과 최근 20개 채팅·채팅별 50개 메시지 제한
- [x] 로컬 채팅 개별 삭제와 전체 기록 삭제
- [ ] 로그인 기반 session_id 소유권 검증
- [ ] Supabase 서버 로그 보존 기간과 인증 사용자 삭제 API
- [ ] 같은 세션의 동시 요청 충돌 제어
- [ ] Supabase 지연·실패율 운영 지표

## P4. 배포 회귀

- [x] `git diff`에서 코드와 문서 변경 범위 확인
- [x] Ruff lint/format 통과
- [x] pytest `164 passed` 유지
- [x] 프런트엔드 프로덕션 빌드 통과
- [x] 프런트엔드 저장·복원·전송 전 개인정보 차단 회귀 테스트 `8 passed`
- [x] 최신 main `a89d1e3` CI 성공
- [x] 후속 CD 성공 및 Google Cloud 내부 헬스체크 통과
- [ ] 외부 `/`, `/api/health`, `/docs` 확인
- [ ] 배포본에서 API별 대표 질문 확인

## P5. Langfuse 관측성

- [x] LangGraph callback과 세션별 Trace context 연결
- [x] 키 미설정 시 no-op, 앱 종료 시 pending trace flush
- [x] 합성 질문으로 Router·Tool·Response Trace 생성 및 flush 성공
- [ ] Langfuse 대시보드에서 Trace 상세 화면 수동 확인
- [ ] 운영 배포 환경에 Langfuse secret 주입 방식 결정

## 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

## 현재 최우선 실행 순서

1. 로컬 Supabase 서버 키·RLS와 같은 UUID의 서버 재시작 후 문맥 복원을 재확인한다.
2. 배포 외부 URL에서 `/`, `/api/health`, `/docs`를 수동 확인한다.
3. 훈련·채용·창업 질문의 Agent 전체 경로와 grounded 응답을 검증한다.
4. Router 평가 질문과 기대 결과 표를 확장한다.
5. 로컬·배포 UI에서 질문 유형별 SSE `status` 표시를 캡처한다.
6. 발표용 핵심 시나리오와 장애 시 fallback 시나리오를 확정한다.

## 현재 테스트 질문

| 질문 | 기대 action | 기대 mode | 기대 request_kind |
| --- | --- | --- | --- |
| 요즘 개발 교육을 듣고 있는데 잘하고 있는지 모르겠어 | `RESPOND` | `general` | `general` |
| 국비지원 훈련을 받으면 뭐가 좋아? | `RESPOND` | `explain` | `general` |
| 청년도약계좌의 현재 조건을 설명해줘 | `SEARCH` | `explain` | `youth_policy` |
| 서울에서 클라우드 엔지니어 국비과정 찾아줘 | `SEARCH` | `recommend` | `training` |
| 서울 사는 만 28세 미취업자인데 청년정책 찾아줘 | `SEARCH` | `recommend` | `youth_policy` |
| 서울 데이터 분석 신입 채용정보 찾아줘 | `SEARCH` | `recommend` | `recruitment` |
| 카페 창업 지원사업 추천해줘 | `SEARCH` | `recommend` | `business` |
| 성남시에 사는 만 25세 청년이야. 주거 관련 정책 찾아줘 | `SEARCH` | `recommend` | `youth_policy` |
| 부산 해운대구에 사는 만 25세 청년이야. 주거 정책 찾아줘 | `SEARCH` | `recommend` | `youth_policy` |
| 고성군에 사는 만 25세 청년이야. 주거 정책 찾아줘 | `SEARCH 후 조건 확인` | `recommend` | `youth_policy` |
| 청년 주거 지원 정책에 대해 알려줘 | `SEARCH` | `recommend` | `youth_policy` |

멀티턴 회귀:

```text
사용자: 거주지원을 받고 싶은데 관련 정책 있어?
Agent: 거주 지역, 만 나이 확인
사용자: 서울에 사는 만 25세야
Agent: 원래 요청한 주거 정책 검색 재개
```

## 후순위

- 실제 LLM token streaming
- LangGraph interrupt가 필요해질 때 영속 checkpointer 검토
- API 수집과 DB 조회 계층 분리
- Supabase pgvector 기반 검색
- 정책 공고 Document Parse / Information Extract
- 운영 관측성과 평가 데이터셋
