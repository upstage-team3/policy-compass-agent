from __future__ import annotations

from types import SimpleNamespace

import pytest
from pydantic import ValidationError

from app.core.config import (
    MAX_LLM_REQUESTS_PER_TURN,
    MAX_SOURCE_ATTEMPTS_PER_TURN,
    TURN_RUNTIME_RESERVE_SECONDS,
    Settings,
    minimum_agent_turn_timeout,
    source_http_timeout,
)


def test_default_timeout_budget_contains_bounded_worst_case():
    settings = Settings(_env_file=None)

    required = minimum_agent_turn_timeout(
        llm_request_timeout_seconds=settings.llm_request_timeout_seconds,
        source_search_timeout_seconds=settings.source_search_timeout_seconds,
    )

    assert settings.agent_turn_timeout_seconds >= required
    assert settings.source_http_timeout_seconds < settings.source_search_timeout_seconds
    assert required == (
        MAX_LLM_REQUESTS_PER_TURN * settings.llm_request_timeout_seconds
        + MAX_SOURCE_ATTEMPTS_PER_TURN * settings.source_search_timeout_seconds
        + TURN_RUNTIME_RESERVE_SECONDS
    )


def test_settings_reject_repository_timeout_not_owned_by_graph_boundary():
    with pytest.raises(ValidationError, match="SOURCE_HTTP_TIMEOUT_SECONDS must be smaller"):
        Settings(
            _env_file=None,
            agent_turn_timeout_seconds=60,
            llm_request_timeout_seconds=8,
            source_search_timeout_seconds=10,
            source_http_timeout_seconds=10,
        )


def test_settings_reject_turn_deadline_smaller_than_bounded_worst_case():
    with pytest.raises(ValidationError, match="requires at least 60s"):
        Settings(
            _env_file=None,
            agent_turn_timeout_seconds=59,
            llm_request_timeout_seconds=8,
            source_search_timeout_seconds=10,
            source_http_timeout_seconds=9,
        )


def test_source_http_timeout_supports_lightweight_repository_test_settings():
    assert source_http_timeout(SimpleNamespace()) == 9.0
    assert source_http_timeout(SimpleNamespace(source_http_timeout_seconds=3.5)) == 3.5
