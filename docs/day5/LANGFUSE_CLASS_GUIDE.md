# Day5 Langfuse 수업 실습 가이드

목표: 수업 시간에 직접 Langfuse 프로젝트를 만들고, 정책나침반 LangGraph 실행 Trace 1건을 확인한 뒤 증빙 화면을 캡처한다.

이 문서는 2026-07-13 기준 공식 Langfuse의 [LangGraph 연동 가이드](https://langfuse.com/guides/cookbook/integration_langgraph)와 [Observability 시작 문서](https://langfuse.com/docs/observability/get-started)를 기준으로 작성했다. SDK 화면이나 API가 바뀌면 수업 자료와 공식 문서를 우선한다.

## 미리 비워 두는 항목

```text
Langfuse 프로젝트명: ____________________
사용 리전 / Base URL: ____________________
Trace 확인 시각: ____________________
Trace URL: ____________________
캡처 파일명: ____________________
```

키 값은 문서, Git, 터미널 캡처에 절대 기록하지 않는다.

## 1. 수업 중 프로젝트 생성

1. Langfuse에서 새 프로젝트를 만든다.
2. 프로젝트 Settings에서 Public Key와 Secret Key를 발급한다.
3. 계정의 데이터 리전에 맞는 Base URL을 확인한다.
4. 키는 로컬 `.env`에만 넣고 `.env.example`에는 변수 이름만 추가한다.

```dotenv
LANGFUSE_PUBLIC_KEY=
LANGFUSE_SECRET_KEY=
LANGFUSE_BASE_URL=
LANGFUSE_TRACING_ENVIRONMENT=development
```

## 2. SDK 설치

프로젝트 루트에서 실행한다.

```bash
uv add langfuse
```

설치 뒤 `pyproject.toml`과 `uv.lock` 변경만 Git 대상에 포함하고 `.env`는 제외한다.

## 3. 인증 확인

공식 SDK의 `auth_check()`로 연결만 확인한다. 출력에는 키 값을 넣지 않는다.

```python
from langfuse import get_client

langfuse = get_client()
print("Langfuse auth:", "ok" if langfuse.auth_check() else "failed")
```

## 4. LangGraph Trace 연결

공식 LangChain callback handler를 그래프 실행 config의 `callbacks`에 전달한다.

```python
from langfuse.langchain import CallbackHandler

langfuse_handler = CallbackHandler()
config = {
    "configurable": {"thread_id": payload.session_id},
    "callbacks": [langfuse_handler],
}
result = await graph.ainvoke(initial_state, config=config)
```

프로덕션에서는 키가 설정된 경우에만 handler를 생성하고, 키 누락이나 Langfuse 장애가 채팅 실패로 이어지지 않도록 관측 기능을 선택적으로 붙인다.

## 5. 안전한 데모 Trace 생성

실사용자 데이터 대신 아래 합성 질문을 새 세션에서 한 번 실행한다.

```text
서울에서 클라우드 엔지니어 국비과정 찾아줘
```

Trace에서 확인할 항목:

- Router → Profile → Missing Slot/Tool → Response → Guardrail 순서
- `request_kind=training`과 선택 Tool 하나
- 전체 지연 시간과 오류 여부
- 입력·출력에 API 키나 인증 URL이 없는지
- 개인정보가 없는 합성 세션인지

## 6. 증빙 캡처

필수 캡처 1장:

- Trace 상세 화면에서 전체 흐름과 성공 상태가 보이게 캡처
- 브라우저 주소, 프로젝트명, Trace ID는 보여도 되지만 키는 절대 노출하지 않음
- 파일명 예: `day5-langfuse-training-trace.png`

회고에 넣을 문장:

```text
Langfuse를 LangGraph callback으로 연결해 Router, Tool, 응답 생성 흐름과 지연 시간을 Trace에서 확인했다. 실사용자 정보 대신 합성 질문을 사용했고 키와 인증 URL은 캡처에서 제외했다.
```

## 7. 실패 시 체크

- Trace가 안 보임: Base URL 리전과 환경변수 이름을 확인하고 서버를 재시작한다.
- 인증 실패: 키 앞뒤 공백과 프로젝트가 맞는지 확인하되 키를 화면 공유하지 않는다.
- 채팅까지 실패: callback 초기화를 임시로 제거해 본 기능을 복구한 뒤 Langfuse만 별도로 점검한다.
- Trace에 민감정보가 보임: 캡처하지 말고 해당 Trace를 삭제한 뒤 합성 입력으로 다시 실행한다.
