from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parents[1]


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


def test_health_reports_when_langfuse_tracing_is_disabled(client):
    response = client.get("/api/health")

    assert response.status_code == 200
    assert response.json()["langfuse_tracing"] == "disabled"
