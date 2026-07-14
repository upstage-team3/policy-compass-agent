from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.http import log_external_api_error
from app.core.privacy import redact_sensitive_structure, redact_sensitive_text

logger = logging.getLogger(__name__)

_MAX_HISTORY_MESSAGES = 8
_MAX_MESSAGE_LENGTH = 4000
_REQUEST_TIMEOUT_SECONDS = 3


@dataclass
class ChatMemoryContext:
    messages: list[dict[str, str]] = field(default_factory=list)
    profile: dict[str, Any] = field(default_factory=dict)
    pending_request: dict[str, Any] = field(default_factory=dict)


def _safe_content(content: str) -> str:
    return redact_sensitive_text(content[:_MAX_MESSAGE_LENGTH])


class SupabaseChatMemoryRepository:
    """Persist recent chat context through Supabase REST without blocking chat failures."""

    def __init__(self) -> None:
        settings = get_settings()
        self._base_url = (settings.supabase_url or "").rstrip("/")
        self._key = settings.supabase_key or ""

    @property
    def is_configured(self) -> bool:
        return bool(self._base_url and self._key)

    @property
    def _headers(self) -> dict[str, str]:
        return {
            "apikey": self._key,
            "Authorization": f"Bearer {self._key}",
            "Content-Type": "application/json",
        }

    async def load(self, session_id: str) -> ChatMemoryContext:
        if not self.is_configured:
            return ChatMemoryContext()

        context = ChatMemoryContext()
        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, headers=self._headers) as client:

            async def load_messages() -> None:
                try:
                    response = await client.get(
                        f"{self._base_url}/rest/v1/chat_logs",
                        params={
                            "session_id": f"eq.{session_id}",
                            "select": "role,content,created_at",
                            "order": "created_at.desc",
                            "limit": str(_MAX_HISTORY_MESSAGES),
                        },
                    )
                    response.raise_for_status()
                    rows = response.json()
                    context.messages = [
                        {"role": row["role"], "content": _safe_content(row["content"])}
                        for row in reversed(rows)
                        if row.get("role") in {"user", "assistant"} and row.get("content")
                    ]
                except Exception as exc:  # noqa: BLE001
                    log_external_api_error(logger, "Supabase 대화 이력 조회", exc)

            async def load_session() -> None:
                try:
                    response = await client.get(
                        f"{self._base_url}/rest/v1/chat_sessions",
                        params={
                            "session_id": f"eq.{session_id}",
                            "select": "profile,pending_request",
                            "limit": "1",
                        },
                    )
                    response.raise_for_status()
                    rows = response.json()
                    if rows:
                        context.profile = redact_sensitive_structure(rows[0].get("profile") or {})
                        context.pending_request = redact_sensitive_structure(rows[0].get("pending_request") or {})
                except Exception as exc:  # noqa: BLE001
                    log_external_api_error(logger, "Supabase 세션 상태 조회", exc)

            await asyncio.gather(load_messages(), load_session())
        return context

    async def save_turn(
        self,
        *,
        session_id: str,
        user_message: str,
        assistant_message: str,
        intent: str,
        profile: dict[str, Any],
        pending_request: dict[str, Any],
    ) -> None:
        if not self.is_configured:
            return

        async with httpx.AsyncClient(timeout=_REQUEST_TIMEOUT_SECONDS, headers=self._headers) as client:

            async def save_messages() -> None:
                try:
                    response = await client.post(
                        f"{self._base_url}/rest/v1/chat_logs",
                        json=[
                            {
                                "session_id": session_id,
                                "role": "user",
                                "content": _safe_content(user_message),
                                "intent": intent,
                            },
                            {
                                "session_id": session_id,
                                "role": "assistant",
                                "content": _safe_content(assistant_message),
                                "intent": intent,
                            },
                        ],
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    log_external_api_error(logger, "Supabase 대화 이력 저장", exc)

            async def save_session() -> None:
                try:
                    response = await client.post(
                        f"{self._base_url}/rest/v1/chat_sessions",
                        params={"on_conflict": "session_id"},
                        headers={"Prefer": "resolution=merge-duplicates"},
                        json={
                            "session_id": session_id,
                            "profile": redact_sensitive_structure(profile),
                            "pending_request": redact_sensitive_structure(pending_request),
                            "updated_at": datetime.now(UTC).isoformat(),
                        },
                    )
                    response.raise_for_status()
                except Exception as exc:  # noqa: BLE001
                    log_external_api_error(logger, "Supabase 세션 상태 저장", exc)

            await asyncio.gather(save_messages(), save_session())
