from __future__ import annotations

from fastapi import APIRouter

from app.core.config import get_settings

router = APIRouter(tags=["health"])


@router.get("/health")
async def health_check() -> dict[str, str]:
    settings = get_settings()
    return {"status": "ok", "app": settings.app_name, "env": settings.app_env}
