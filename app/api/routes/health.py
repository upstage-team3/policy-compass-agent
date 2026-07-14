from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    langfuse_tracing = "enabled" if settings.langfuse_public_key and settings.langfuse_secret_key else "disabled"
    return {
        "status": "ok",
        "app": settings.app_name,
        "env": settings.app_env,
        "langfuse_tracing": langfuse_tracing,
    }
