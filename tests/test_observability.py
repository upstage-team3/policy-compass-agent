from __future__ import annotations

from app.core import observability


def test_langfuse_is_disabled_without_both_keys(monkeypatch):
    monkeypatch.setenv("LANGFUSE_PUBLIC_KEY", "")
    monkeypatch.setenv("LANGFUSE_SECRET_KEY", "")
    observability.get_settings.cache_clear()
    observability.get_langfuse_client.cache_clear()

    assert observability.get_langfuse_client() is None
    assert observability.create_langfuse_handler() is None


def test_noop_trace_context_does_not_hide_application_errors():
    try:
        with observability.langfuse_trace_context("test-session", enabled=False):
            raise RuntimeError("graph failed")
    except RuntimeError as exc:
        assert str(exc) == "graph failed"
    else:
        raise AssertionError("application errors must leave the tracing context")
