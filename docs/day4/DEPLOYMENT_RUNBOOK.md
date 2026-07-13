# Day4 기존 CI/CD · Google Cloud 배포 환경 회귀 가이드

작성일: 2026-07-13

## 1. 배포 전 안전 점검

Docker 구성, GitHub Actions CI/CD, Google Cloud 배포와 외부 헬스체크는 3일차까지 완료했다. Day4에는 새 인프라를 구축하지 않는다. 현재 `main`과 운영 중인 외부 URL을 기준선으로 삼고, API 연동과 기능 개선분이 기존 자동 배포 경로에 정상 반영되는지만 확인한다. 프로젝트 루트에서 실행하며 `.env` 값이나 `docker compose config` 전체 출력은 공유하지 않는다.

```bash
git status --short --branch
git check-ignore -v .env
uv run --python /Users/seongmin/.local/bin/python3.11 ruff check app tests
uv run --python /Users/seongmin/.local/bin/python3.11 ruff format app tests --check
uv run --python /Users/seongmin/.local/bin/python3.11 pytest tests -q
```

통과 기준:

- 브랜치가 `main...origin/main` 기준으로 예상한 상태다.
- `.env`가 `.gitignore`에 의해 제외된다.
- Ruff와 pytest가 모두 성공한다.

## 2. 외부 API 사전 검증

로컬 `.env`에는 Upstage Solar, 온통청년, 고용24 훈련, 고용24 채용, 기업마당 키가 모두 설정되어 있다. 값은 출력하지 않고 설정 여부와 실제 호출 결과만 확인한다.

검증 순서:

1. Repository 단독 호출로 HTTP 상태와 XML/JSON 응답을 확인한다.
2. normalizer 결과에서 이름·대상·기간·지역·링크 필드를 확인한다.
3. Tool 입력/출력 스키마와 실제 결과가 일치하는지 확인한다.
4. `/api/chat`과 `/api/chat/stream`에서 요청 유형별 결과를 확인한다.
5. 실패·결과 없음·권한 제한 시 fallback 이유가 사용자에게 표시되는지 확인한다.

고용24 채용은 개인키 허용 범위와 제한 범위를 분리한다. 채용행사·공채속보·공채기업정보는 실제 호출을 확인하고, 채용정보목록·상세 제한은 없는 공고를 생성하지 않는 탐색 가이드로 처리한다.

## 3. 선택적 Docker 로컬 회귀 검증

Google Cloud에서는 3일차에 Docker 배포가 성공했다. 로컬 Docker 검증은 배포 완료 조건이 아니라 API 연동 문제를 컨테이너 환경에서 재현해야 할 때 수행하는 선택적 회귀 검사다. 필요하면 Docker Desktop을 실행하고 엔진이 준비될 때까지 기다린다.

```bash
docker info
docker compose build
docker compose up -d
docker compose ps
```

서비스 확인:

```bash
curl -f http://127.0.0.1:8000/api/health
curl -f http://127.0.0.1:8000/health
```

브라우저 확인 주소:

```text
http://127.0.0.1:8000/
http://127.0.0.1:8000/docs
```

문제 발생 시:

```bash
docker compose logs --tail=100 api
docker compose down
```

API 키가 포함될 수 있으므로 로그를 공유하기 전에 값이 노출되지 않았는지 확인한다.

컨테이너 실행 뒤에는 API별 핵심 질문을 한 번씩 호출해 `.env`가 컨테이너에 전달되는지 확인한다.

## 4. 기존 GitHub Actions CI 사용

3일차에 PR CI 통과, merge, `main` CI 성공, CD 자동 실행까지 완료했다. Day4에는 파이프라인을 새로 만들지 않고 API 연동 변경분에 동일한 흐름을 사용한다. CI는 Python 3.11에서 다음 순서로 실행된다.

```text
Ruff lint
-> Ruff format check
-> pytest
-> PR 결과 코멘트
-> 선택적 AI 리뷰
```

확인 항목:

- `uv sync --group dev`가 현재 `pyproject.toml`과 호환된다.
- `scripts/ai_reviewer.py`가 없으면 AI Review 단계가 조건에 따라 건너뛴다.
- 테스트는 외부 API 호출 없이도 통과한다.
- `main`의 CI 이름이 CD의 `workflow_run.workflows` 값과 정확히 일치한다.

문서만 변경하면 현재 `paths` 조건상 CI가 자동 실행되지 않을 수 있다. 배포 검증이 필요하면 Actions의 `workflow_dispatch`로 CI를 수동 실행한다.

## 5. GitHub Secrets 점검

실제 값은 이 문서에 적지 않는다. 저장소의 Settings > Secrets and variables > Actions에서 이름만 확인한다.

| 구분 | Secret 이름 |
| --- | --- |
| GCE 접속 | `GCE_HOST`, `GCE_USERNAME`, `GCE_SSH_KEY` |
| LLM | `UPSTAGE_API_KEY` |
| 온통청년 | `YOUTHCENTER_POLICY_API_KEY`, `YOUTHCENTER_POLICY_API_URL` |
| 고용24 훈련 | `EMPLOYMENT24_TRAINING_API_KEY`, `EMPLOYMENT24_TRAINING_API_URL` |
| 고용24 채용 | `EMPLOYMENT24_JOB_API_KEY` |

채용행사·공채속보·공채기업정보 URL은 공개 기본값으로 관리한다. 권한이 없는 `210L01` 채용정보목록 URL은 Secret으로 등록하지 않는다.
| 기업마당 | `BIZINFO_API_KEY`, `BIZINFO_API_URL` |
| 선택 DB | `SUPABASE_URL`, `SUPABASE_KEY` |

빈 Secret이 있으면 CD가 `.env` 파일은 만들더라도 해당 기능은 fallback으로 동작할 수 있다.

로컬 키가 모두 존재하더라도 GitHub Secrets는 별도 저장소이므로 이름별 등록 상태를 각각 확인한다.

## 6. 기존 Google Cloud 배포본 상태 확인

권장 기준:

- Ubuntu 22.04 LTS 또는 24.04 LTS
- `e2-medium`
- 30GB 디스크
- Docker Engine과 Docker Compose plugin 설치
- 방화벽: SSH 22, 데모 8000, 필요 시 HTTP 80

새 VM을 만드는 단계가 아니라 3일차에 배포 완료한 VM에서 API 연동 변경 후에도 서비스가 정상인지 확인한다. VM에서 확인:

```bash
docker --version
docker compose version
curl -f http://127.0.0.1:8000/api/health
```

외부 접속이 안 될 때는 다음 순서로 분리해서 확인한다.

1. 컨테이너가 실행 중인지 확인한다.
2. VM 내부 `127.0.0.1:8000/api/health`가 200인지 확인한다.
3. Docker 포트가 `0.0.0.0:8000->8000`으로 열렸는지 확인한다.
4. GCP VPC 방화벽에 TCP 8000 허용 규칙이 있는지 확인한다.
5. 인스턴스 네트워크 태그와 방화벽 대상 태그가 일치하는지 확인한다.

## 7. CD 재실행과 외부 검증

CD는 성공한 `main` CI 뒤에 GHCR 이미지를 만들고 기존 GCE에 SSH 배포한다. 3일차에 이 자동 경로가 성공했으므로 Day4에는 기능 개선 커밋 기준으로 다시 통과하는지 확인한다. 수동 실행도 가능하다.

배포 후 외부 확인:

```text
http://GCE_EXTERNAL_IP:8000/
http://GCE_EXTERNAL_IP:8000/api/health
http://GCE_EXTERNAL_IP:8000/docs
```

완료 기준:

- Build & Push to GHCR 성공
- Deploy to Compute Engine 성공
- CD 헬스체크 `/api/health` HTTP 200
- 외부 브라우저에서 UI와 API 문서 접근 가능
- 외부 배포본에서 5개 API의 대표 질문과 fallback 시나리오 확인

## 8. 80 포트가 필요한 경우

제출 폼에서 `http://IP:8000`을 받지 않으면 Nginx를 사용한다.

```text
외부 요청 :80
-> Nginx
-> 127.0.0.1:8000
```

Nginx 적용 뒤에는 `http://GCE_EXTERNAL_IP/`와 `http://GCE_EXTERNAL_IP/api/health`를 다시 확인한다.

## 9. 롤백 기준

다음 중 하나면 새 버전을 유지하지 않는다.

- 컨테이너가 반복 재시작됨
- `/api/health`가 60초 안에 200이 되지 않음
- 정적 UI가 열리지만 핵심 채팅 API가 5xx를 반환함
- 환경변수가 전달되지 않아 기존 정상 기능이 모두 실패함

CD의 수동 `rollback` 입력 또는 VM의 `.previous_image` 기록을 사용해 이전 이미지로 복구하고 원인을 기록한다.
