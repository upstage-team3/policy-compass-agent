from pathlib import Path

import pytest

from app.core.config import get_settings

PROJECT_ROOT = Path(__file__).resolve().parents[1]


@pytest.fixture(autouse=True)
def _clear_settings_cache():
    get_settings.cache_clear()
    yield
    get_settings.cache_clear()


def test_docker_image_builds_and_serves_react_frontend():
    dockerfile = (PROJECT_ROOT / "Dockerfile").read_text()
    dockerignore = (PROJECT_ROOT / ".dockerignore").read_text().splitlines()

    assert "FROM node:22-alpine AS frontend-builder" in dockerfile
    assert "RUN npm run build" in dockerfile
    assert "COPY --from=frontend-builder /frontend/dist ./app/static" in dockerfile
    assert "frontend/node_modules" in dockerignore
    assert "frontend/dist" in dockerignore


def test_cd_injects_langfuse_configuration_into_deployed_environment():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "cd.yml").read_text()

    assert "LANGFUSE_PUBLIC_KEY=${{ secrets.LANGFUSE_PUBLIC_KEY }}" in workflow
    assert "LANGFUSE_SECRET_KEY=${{ secrets.LANGFUSE_SECRET_KEY }}" in workflow
    assert "LANGFUSE_BASE_URL=${{ secrets.LANGFUSE_BASE_URL" in workflow
    assert "LANGFUSE_TRACING_ENVIRONMENT=production" in workflow


def test_cd_confirms_readiness_before_recording_current_image_and_rechecks_rollback():
    workflow = (PROJECT_ROOT / ".github" / "workflows" / "cd.yml").read_text()

    health_check = 'if [ "$HTTP_STATUS" -eq 200 ]; then'
    record_current = 'echo "${FULL_IMAGE}" > .current_image'
    assert workflow.index(record_current) > workflow.index(health_check)
    assert 'if [ "$ROLLBACK_STATUS" -eq 200 ]; then' in workflow
    assert 'echo "${PREV_IMAGE}" > .current_image' in workflow


def test_health_reports_when_langfuse_tracing_is_disabled(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["langfuse_tracing"] == "disabled"


def test_liveness_does_not_depend_on_external_configuration(client):
    response = client.get("/api/live")

    assert response.status_code == 200
    assert response.json() == {"status": "alive"}


def test_readiness_is_degraded_but_available_without_keys_outside_production(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "local")
    monkeypatch.setenv("APP_RELEASE_SHA", "local-build")

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "degraded",
        "release_sha": "local-build",
        "app_env": "local",
        "dependencies": {
            "upstage": {"status": "not_configured"},
            "youthcenter": {"status": "not_configured"},
            "work24_training": {"status": "not_configured"},
            "work24_job": {"status": "not_configured"},
            "supabase": {"status": "not_configured"},
        },
        "missing_dependencies": [
            "upstage",
            "youthcenter",
            "work24_training",
            "work24_job",
            "supabase",
        ],
    }


def test_readiness_is_not_ready_without_required_keys_in_production(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")

    response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["status"] == "not_ready"
    assert response.json()["app_env"] == "production"


def test_readiness_rejects_present_key_with_invalid_source_url(client, monkeypatch):
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("EMPLOYMENT24_TRAINING_API_KEY", "training-secret")
    monkeypatch.setenv("EMPLOYMENT24_TRAINING_API_URL", "")

    response = client.get("/api/ready")

    assert response.status_code == 503
    assert response.json()["dependencies"]["work24_training"] == {"status": "not_configured"}


def test_readiness_reports_only_status_and_never_exposes_configured_secrets(client, monkeypatch):
    secret_values = {
        "UPSTAGE_API_KEY": "upstage-secret-value",
        "YOUTHCENTER_POLICY_API_KEY": "youth-secret-value",
        "EMPLOYMENT24_TRAINING_API_KEY": "training-secret-value",
        "EMPLOYMENT24_JOB_API_KEY": "job-secret-value",
        "SUPABASE_URL": "https://private-project.supabase.co",
        "SUPABASE_KEY": "supabase-secret-value",
    }
    for name, value in secret_values.items():
        monkeypatch.setenv(name, value)
    monkeypatch.setenv("APP_ENV", "production")
    monkeypatch.setenv("APP_RELEASE_SHA", "abc123")

    response = client.get("/api/ready")

    assert response.status_code == 200
    assert response.json() == {
        "status": "ready",
        "release_sha": "abc123",
        "app_env": "production",
        "dependencies": {
            "upstage": {"status": "configured"},
            "youthcenter": {"status": "configured"},
            "work24_training": {"status": "configured"},
            "work24_job": {"status": "configured"},
            "supabase": {"status": "configured"},
        },
        "missing_dependencies": [],
    }
    for secret in secret_values.values():
        assert secret not in response.text
