# CI/CD · Google Cloud 배포 회귀 가이드

최종 갱신: 2026-07-15

## 1. 배포 불변식

정책나침반 CD는 **CI가 검증한 exact commit**과 **GCE가 실행하는 immutable
image**가 같아야 한다.

1. `workflow_run` 배포의 `RELEASE_SHA`는
   `github.event.workflow_run.head_sha`다.
2. checkout, SHA image tag, `APP_RELEASE_SHA`가 같은 전체 SHA를 사용한다.
3. build output의 digest를 받아 GCE에
   `ghcr.io/.../policy-compass-agent@sha256:...` 형태로 배포한다.
4. `.current_image`, `.previous_image`도 digest reference를 저장한다.
5. 컨테이너와 배포 후 readiness는 `/api/ready`로 확인한다.

`latest`나 SHA tag가 함께 push되더라도 실제 배포 대상은 digest다.

채팅 런타임의 현재 방어 기본값도 배포마다 유지한다.

```env
AGENT_TURN_TIMEOUT_SECONDS=60
LLM_REQUEST_TIMEOUT_SECONDS=8
SOURCE_SEARCH_TIMEOUT_SECONDS=10
SOURCE_HTTP_TIMEOUT_SECONDS=9
CHAT_SESSION_RATE_LIMIT_PER_MINUTE=20
CHAT_IP_RATE_LIMIT_PER_MINUTE=120
FEEDBACK_SESSION_RATE_LIMIT_PER_MINUTE=30
FEEDBACK_IP_RATE_LIMIT_PER_MINUTE=120
```

세션 ID는 UUIDv4만 허용한다. 이 설정은 단일 프로세스 deadline·traffic 방어이며
멀티워커 owner binding이나 분산 rate limit을 대신하지 않는다.

## 2. 배포 전 로컬 점검

프로젝트 루트에서 실행한다. `.env` 값이나 `docker compose config` 전체 출력은
공유하지 않는다.

```bash
git status --short --branch
git check-ignore -v .env
uv run ruff check app tests
uv run ruff format app tests --check
uv run pytest tests -q
cd frontend && pnpm test && pnpm run build
```

통과 기준:

- 예상 브랜치와 변경 범위다.
- `.env`가 Git에서 제외된다.
- backend와 frontend 전체 회귀가 성공한다.
- 테스트는 외부 API 키와 네트워크 없이 결정적으로 통과한다.

## 3. 현재 외부 API 범위

| 의존성 | 용도 |
| --- | --- |
| Upstage Solar | Router/Profile/조건 질문/대화/검색 답변/상태 안내 |
| 온통청년 | 청년정책 |
| Work24 training | 국민내일배움카드 훈련과정 |
| Work24 job | 채용행사·공채속보 보조정보 |
| Supabase | 프로필·최근 8개 이력·pending·allowlist 후보 snapshot의 단일 세션 경계와 피드백 저장 |
| Langfuse | trace와 사용자 feedback score |

기업마당 API Secret은 사용하지 않는다. 창업지원은 LLM `out_of_scope`로 현재 MVP
범위를 안내하며 외부 검색 Tool이나 기업마당·K-Startup 링크를 사용하지 않는다.

Supabase 미설정·장애 시 서버는 최대 2,048세션의 bounded local LRU mirror를
사용한다. 이 mirror는 같은 프로세스에서만 유효하며 재시작·멀티워커 복원을
보장하지 않는다. 같은 프로세스·세션의 load→graph→save는 `SessionLockPool`으로
직렬화한다. DB optimistic version, multi-worker owner binding, 서버 삭제 API·TTL은
아직 배포 완료 조건이 아니다.

live 검증에서는 키 값을 출력하지 않고 다음만 기록한다.

- HTTP 상태와 source 상태
- 정규화 후보 건수와 유형
- requested/applied filter
- 원문 링크 유무
- 제한 또는 장애 사유

## 4. 선택적 Docker 로컬 회귀

```bash
docker info
docker compose build
docker compose up -d
docker compose ps
```

서비스 확인:

```bash
curl -fsS http://127.0.0.1:8000/api/live
curl -fsS http://127.0.0.1:8000/api/ready
```

로컬에서 키를 비운 경우 `/api/ready`의 HTTP 상태는 200이고 전체 상태는
`degraded`가 정상이다. `/api/live`는 외부 의존성과 무관하게 200이어야 한다.

문제 발생 시:

```bash
docker compose logs --tail=100 api
docker compose down
```

로그를 공유하기 전에 credential, authorization header, query string에 키가 없는지
확인한다.

## 5. CI 확인

`Policy Compass Agent CI`는 다음 job을 실행한다.

```text
Ruff lint/format
→ pytest
frontend test + production build
→ 실제 Docker image build
→ PR 결과 comment
```

- 외부 API Secret을 단위 테스트에 주입하지 않는다.
- 문서만 변경하면 paths 조건 때문에 자동 CI가 실행되지 않을 수 있다. 필요하면
  `workflow_dispatch`로 수동 실행한다.
- CD의 `workflow_run.workflows` 이름은 CI의 `name`과 정확히 같아야 한다.

## 6. GitHub Secrets

값은 문서나 터미널 출력에 남기지 않고 이름과 등록 여부만 확인한다.

| 구분 | Secret 이름 |
| --- | --- |
| GCE | `GCE_HOST`, `GCE_USERNAME`, `GCE_SSH_KEY` |
| LLM | `UPSTAGE_API_KEY` |
| 온통청년 | `YOUTHCENTER_POLICY_API_KEY`, `YOUTHCENTER_POLICY_API_URL` |
| Work24 훈련 | `EMPLOYMENT24_TRAINING_API_KEY`, `EMPLOYMENT24_TRAINING_API_URL` |
| Work24 채용 | `EMPLOYMENT24_JOB_API_KEY` |
| 세션/피드백 DB | `SUPABASE_URL`, `SUPABASE_KEY` |
| 관측성 | `LANGFUSE_PUBLIC_KEY`, `LANGFUSE_SECRET_KEY`, `LANGFUSE_BASE_URL` |

- `SUPABASE_KEY`는 브라우저에 전달하지 않는 서버 전용 키다.
- Work24 공개 endpoint URL은 기본 설정을 사용할 수 있다.
- `BIZINFO_API_KEY`, `BIZINFO_API_URL`은 현재 배포 설정이 아니다.

## 7. readiness 계약

| endpoint | 계약 |
| --- | --- |
| `/api/health` | 기존 클라이언트 호환 health |
| `/api/live` | process liveness, 항상 200 |
| `/api/ready` | release SHA, app env, 핵심 의존성 구성 상태 |

`/api/ready`는 비밀값 없이 `configured/not_configured`만 반환한다.

- local/CI의 필수 키 누락: HTTP 200, `status=degraded`
- production의 필수 키 누락: HTTP 503, `status=not_ready`
- production 전체 구성: HTTP 200, `status=ready`

현재 readiness는 키/URL **구성 여부**를 확인한다. 실제 upstream 연결이나 circuit
상태까지 확인하는 probe는 후속 범위다.

## 8. CD 실행과 revision 확인

정상 배포는 성공한 main CI의 `workflow_run`으로 시작한다.

확인 항목:

1. Build job checkout ref가 `RELEASE_SHA`인지 확인한다.
2. build summary의 commit과 digest를 기록한다.
3. Deploy log가 `FULL_IMAGE=...@sha256:...`를 pull하는지 확인한다.
4. GCE `.current_image`가 같은 digest인지 확인한다.
5. `/api/ready.release_sha`가 전체 CI head SHA와 같은지 확인한다.

VM 내부:

```bash
cd /home/$USER/policy-compass-agent
cat .current_image
docker compose ps
curl -fsS http://127.0.0.1:8000/api/live
curl -fsS http://127.0.0.1:8000/api/ready
```

`.current_image`에는 `@sha256:`가 있어야 한다. 출력한 image reference에는 비밀값이
없지만, `.env`는 출력하지 않는다.

외부 확인:

```text
http://GCE_EXTERNAL_IP:8000/
http://GCE_EXTERNAL_IP:8000/docs
http://GCE_EXTERNAL_IP:8000/api/live
http://GCE_EXTERNAL_IP:8000/api/ready
```

## 9. 배포 후 제품 smoke

- 일반 인사 → 청년 정책 에이전트 범위 고정 응답, Tool 0회
- 일반 인사·범위 밖 고정 응답도 `verify_answer` 통과
- 청년정책 → 온통청년 Tool 하나와 gate 통과 후보
- 국비 훈련 → Work24 training Tool 하나, 지역 코드/후처리 적용
- 채용 보조 → Work24 job Tool 하나, company 정보 기본 제외
- 시·군·구 불일치 또는 구조화 지역 검증 불가 후보 → 답변·카드에서 제외
- PARTIAL 검색 → 일부 하위 조회 미완료 공개 경고와 검증된 후보만 표시
- 답변 검증 실패 → 추천 카드와 `last_presented_candidates` snapshot 0건
- 창업지원 → Tool 없이 LLM `out_of_scope`, 기업마당·K-Startup 링크 없음
- 검색 뒤 일반 대화 → 이전 카드·disclaimer 0건
- pending 인사/조건/취소/새 검색 → KEEP/RESUME/CANCEL/REPLACE
- 프로필 정정/삭제/무효 값 → 각각 `SET/CLEAR/UNCHANGED` 의미 유지
- UUIDv4 아닌 세션 ID → 422, 정상 UUIDv4 → 같은 대화 문맥 유지
- 같은 세션 동시 요청 → 한 프로세스에서 load→graph→save 순서 직렬화
- 그래프 deadline 초과 → 60초 내 timeout 계약으로 종료
- 세션·IP 분당 한도 초과 → 429와 `Retry-After`

## 10. rollback

다음이면 새 버전을 유지하지 않는다.

- 컨테이너 반복 재시작
- production `/api/ready`가 제한 시간 안에 200이 되지 않음
- `/api/live`는 200인데 채팅 API가 지속적으로 5xx
- `release_sha` 또는 실행 digest가 배포 대상과 다름
- 필수 환경 구성이 누락됨

정상 배포 전 `.current_image`는 `.previous_image`로 복사된다. 자동 또는 수동 rollback은
`.previous_image`의 digest를 pull/run하고 `/api/ready`를 다시 확인한다.

```bash
cat .previous_image
```

롤백 reference에도 `@sha256:`가 있어야 한다.
