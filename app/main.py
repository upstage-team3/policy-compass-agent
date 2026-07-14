from __future__ import annotations

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.api.routes import chat, health, policies
from app.core.config import get_settings
from app.core.observability import get_langfuse_client, shutdown_langfuse
from app.schemas.chat import ChatRequest

logging.basicConfig(level=logging.INFO)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)

STATIC_DIR = Path(__file__).resolve().parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):  # noqa: ARG001
    logger = logging.getLogger("app")
    settings = get_settings()
    logger.info("%s 시작 (env=%s)", settings.app_name, settings.app_env)
    get_langfuse_client()
    yield
    shutdown_langfuse()
    logger.info("%s 종료", settings.app_name)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title=settings.app_name, version="0.1.0", lifespan=lifespan)

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(health.router, prefix="/api")
    app.include_router(chat.router, prefix="/api")
    app.include_router(policies.router, prefix="/api")

    app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

    @app.get("/")
    async def root() -> FileResponse:
        return FileResponse(str(STATIC_DIR / "index.html"))

    @app.get("/health")
    async def legacy_health() -> dict[str, str]:
        return {"status": "ok", "service": "policy-compass"}

    @app.post("/api/v1/chat/sync")
    async def legacy_chat_sync(payload: ChatRequest) -> dict:
        result = await chat._run_agent(payload)  # noqa: SLF001 - compatibility wrapper
        return {
            "answer": result.get("final_response", ""),
            "intent": result.get("intent", "GENERAL"),
            "profile": result.get("profile") or {},
            "recommendations": result.get("scored_results", []),
            "citations": [
                {
                    "title": item.get("policy", {}).get("title"),
                    "url": item.get("policy", {}).get("source_url"),
                    "source": item.get("policy", {}).get("agency"),
                }
                for item in result.get("scored_results", [])
            ],
        }

    @app.post("/api/v1/chat")
    async def legacy_chat_stream(payload: ChatRequest):
        return await chat.chat_stream(payload)

    return app


app = create_app()
