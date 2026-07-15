from __future__ import annotations

from types import SimpleNamespace

from app.core import llm as llm_module


async def test_solar_client_records_stage_and_token_usage_without_prompt_contents(monkeypatch):
    recorded: dict = {}

    class FakeGeneration:
        def update(self, **kwargs):
            recorded["update"] = kwargs

    class FakeObservation:
        def __enter__(self):
            return FakeGeneration()

        def __exit__(self, exc_type, exc_value, traceback):  # noqa: ANN001
            return False

    class FakeLangfuse:
        def start_as_current_observation(self, **kwargs):
            recorded["observation"] = kwargs
            return FakeObservation()

    class FakeResponse:
        def raise_for_status(self):
            return None

        def json(self):
            return {
                "choices": [{"message": {"content": "안전한 테스트 응답"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "total_tokens": 18},
            }

    class FakeAsyncClient:
        def __init__(self, *, timeout):
            recorded["timeout"] = timeout

        async def __aenter__(self):
            return self

        async def __aexit__(self, exc_type, exc_value, traceback):  # noqa: ANN001
            return False

        async def post(self, url, *, json, headers):  # noqa: A002
            recorded["request"] = {"url": url, "json": json, "has_authorization": "Authorization" in headers}
            return FakeResponse()

    monkeypatch.setattr(llm_module, "get_langfuse_client", lambda: FakeLangfuse())
    monkeypatch.setattr(llm_module.httpx, "AsyncClient", FakeAsyncClient)
    client = llm_module.SolarLLMClient()
    client._settings = SimpleNamespace(
        upstage_api_key="configured-test-key",
        upstage_base_url="https://upstage.invalid/v1",
        upstage_model="solar-pro2",
        llm_request_timeout_seconds=5.0,
    )

    response = await client.complete(
        [{"role": "user", "content": "민감할 수 있는 사용자 원문"}],
        operation_name="grounded-answer-training",
    )

    assert response == "안전한 테스트 응답"
    assert recorded["observation"]["name"] == "grounded-answer-training"
    assert recorded["observation"]["input"] == {"message_count": 1}
    assert "민감할 수 있는 사용자 원문" not in str(recorded["observation"])
    assert recorded["update"]["usage_details"] == {"input": 11, "output": 7, "total": 18}
    assert recorded["request"]["has_authorization"] is True
