"""Upstage Solar API 클라이언트.

API 키가 없거나 호출이 실패하면 LLMUnavailableError 를 발생시켜, 상위
LangGraph 노드가 규칙 기반 fallback 로직으로 안전하게 전환할 수 있도록 한다.
(기획서: "기업마당 API 호출이 실패하거나 API 키가 없는 경우에도 데모 흐름이
중단되지 않도록 한다" 원칙을 LLM 계층에도 동일하게 적용)
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import AsyncIterator

import httpx

from app.core.config import get_settings

logger = logging.getLogger(__name__)


class LLMUnavailableError(RuntimeError):
    """LLM API 키가 없거나 호출이 불가능한 상태."""


class SolarLLMClient:
    def __init__(self) -> None:
        self._settings = get_settings()

    @property
    def is_configured(self) -> bool:
        return bool(self._settings.upstage_api_key)

    async def complete(
        self,
        messages: list[dict[str, str]],
        *,
        temperature: float = 0.3,
        response_format_json: bool = False,
    ) -> str:
        if not self.is_configured:
            raise LLMUnavailableError("UPSTAGE_API_KEY 가 설정되지 않았습니다.")

        payload: dict = {
            "model": self._settings.upstage_model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format_json:
            payload["response_format"] = {"type": "json_object"}

        headers = {"Authorization": f"Bearer {self._settings.upstage_api_key}"}
        url = f"{self._settings.upstage_base_url}/chat/completions"

        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(url, json=payload, headers=headers)
            response.raise_for_status()
            data = response.json()
            return data["choices"][0]["message"]["content"]

    async def stream_complete(self, messages: list[dict[str, str]], *, temperature: float = 0.3) -> AsyncIterator[str]:
        if not self.is_configured:
            raise LLMUnavailableError("UPSTAGE_API_KEY 가 설정되지 않았습니다.")

        payload = {
            "model": self._settings.upstage_model,
            "messages": messages,
            "temperature": temperature,
            "stream": True,
        }
        headers = {"Authorization": f"Bearer {self._settings.upstage_api_key}"}
        url = f"{self._settings.upstage_base_url}/chat/completions"

        async with (
            httpx.AsyncClient(timeout=60) as client,
            client.stream("POST", url, json=payload, headers=headers) as response,
        ):
            response.raise_for_status()
            async for line in response.aiter_lines():
                if not line or not line.startswith("data:"):
                    continue
                data_str = line.removeprefix("data:").strip()
                if data_str == "[DONE]":
                    break
                try:
                    chunk = json.loads(data_str)
                except json.JSONDecodeError:
                    continue
                delta = chunk.get("choices", [{}])[0].get("delta", {}).get("content")
                if delta:
                    yield delta


def extract_json(text: str) -> dict:
    """LLM 응답에서 JSON 블록만 추출한다. 실패 시 빈 dict 반환."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        return {}
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        logger.warning("LLM 응답에서 JSON 파싱에 실패했습니다: %s", text)
        return {}
