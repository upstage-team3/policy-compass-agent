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
