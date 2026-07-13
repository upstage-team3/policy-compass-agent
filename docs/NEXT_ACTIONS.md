# 다음 개발 작업

최종 갱신: 2026-07-13

세부 배경은 [DEVELOPMENT_HANDOFF.md](DEVELOPMENT_HANDOFF.md)를 먼저 읽는다.

## P0. 외부 API live 연결 검증

- [x] Upstage Solar Router와 통합 Conversation Node 실제 호출
- [x] 온통청년 `getPlcy` JSON API와 `apiKeyNm` 인증, 정책 3건 정규화 확인
- [x] 온통청년 정책명 0건 재검색과 `zipCd` 거주지역 필터 추가
- [x] 고용24 훈련 Repository 단독 호출과 상세 URL 회귀 확인
- [x] 고용24 채용은 허용 3개 endpoint만 호출하고 제한 endpoint를 호출하지 않음
- [x] 기업마당 Repository 단독 호출과 실제 JSON 필드 확인
- [x] API 오류 로그에 인증키가 포함된 URL/query string을 남기지 않도록 보완

검증 결과에는 HTTP 상태, 정규화 필드, 원문 링크, 제한 사유만 남기고 키 값은 기록하지 않는다.

## P1. Agent 전체 경로 QA

- [x] 일반 고민이 `RESPOND/general`로 분류되고 Tool을 호출하지 않는지 확인
- [ ] 청년정책 질문이 `youth_policy`만 호출하는지 확인
- [ ] 훈련 질문이 `training`과 적절한 `search_query`를 만드는지 확인
- [ ] 채용 질문이 `recruitment`만 호출하는지 확인
- [ ] 창업 질문이 `business`만 호출하는지 확인
- [x] 검색 없는 설명과 공식 데이터가 필요한 설명을 `RESPOND/SEARCH`로 구분
- [ ] API 후보 밖 사실을 LLM이 생성하지 않는지 확인

## P2. 대화 품질

- [ ] Router 결과에 따라 SSE `status` 메시지를 다르게 표시
- [ ] `interest_fields`를 무조건 합치지 않고 유지·교체 의도를 처리
- [ ] 새 관심 분야 요청 시 현재 요청을 우선하는 회귀 테스트 추가
- [x] 설명형·추천형·일반 대화 경계 fixture 추가
- [ ] Router 평가 질문과 기대 결과 표 작성

## P3. 배포 회귀

- [ ] `git diff`에서 코드와 문서 변경 범위 확인
- [ ] Ruff lint/format 통과
- [x] pytest `57 passed` 유지
- [ ] 기존 CI를 통해 변경분 검증
- [ ] 기존 CD를 통해 Google Cloud에 변경분 반영
- [ ] 외부 `/`, `/api/health`, `/docs` 확인
- [ ] 배포본에서 API별 대표 질문 확인

## 검증 명령

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
```

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

## 후순위

- 실제 LLM token streaming
- Redis 또는 DB checkpointer
- API 수집과 DB 조회 계층 분리
- Supabase pgvector 기반 검색
- 정책 공고 Document Parse / Information Extract
- 운영 관측성과 평가 데이터셋
