from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient

# LLM/외부 API 키 없이 규칙 기반 fallback 경로로 테스트가 항상 동작하도록 강제한다.
os.environ.setdefault("UPSTAGE_API_KEY", "")
os.environ.setdefault("BIZINFO_API_KEY", "")
os.environ.setdefault("YOUTHCENTER_POLICY_API_KEY", "")
os.environ.setdefault("EMPLOYMENT24_TRAINING_API_KEY", "")
os.environ.setdefault("EMPLOYMENT24_JOB_API_KEY", "")

from app.core.config import get_settings  # noqa: E402
from app.main import app  # noqa: E402

get_settings.cache_clear()


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)
