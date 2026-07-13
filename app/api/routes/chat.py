"""채팅 API 라우트.

/api/chat : 동기 방식 (테스트/단순 클라이언트용)
/api/chat/stream : SSE 스트리밍 방식

MVP 범위의 스트리밍은 그래프 실행이 끝난 최종 응답을 자연스러운 청크
단위로 점진 전송하는 방식이다 (LLM 토큰 단위 스트리밍은 추후 개선 과제).
"""

from __future__ import annotations

import json
import logging

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.graph.graph import get_agent_graph
from app.repositories.chat_memory import SupabaseChatMemoryRepository
from app.schemas.chat import ChatRequest, ChatTurnResponse, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_STREAM_CHUNK_SIZE = 24
_chat_memory = SupabaseChatMemoryRepository()


async def _run_agent(payload: ChatRequest) -> dict:
    graph = get_agent_graph()
    config = {"configurable": {"thread_id": payload.session_id}}
    memory = await _chat_memory.load(payload.session_id)
    initial_state: dict = {
        "session_id": payload.session_id,
        "user_input": payload.message,
    }
    if memory.messages:
        initial_state["conversation_history"] = memory.messages
    if memory.profile:
        initial_state["profile"] = memory.profile
    if memory.pending_request:
        initial_state["pending_request"] = memory.pending_request

    result = await graph.ainvoke(initial_state, config=config)
    await _chat_memory.save_turn(
        session_id=payload.session_id,
        user_message=payload.message,
        assistant_message=result.get("final_response", ""),
        intent=result.get("intent", "GENERAL"),
        profile=result.get("profile") or {},
        pending_request=result.get("pending_request") or {},
    )
    return result


@router.post("", response_model=ChatTurnResponse)
async def chat(payload: ChatRequest) -> ChatTurnResponse:
    result = await _run_agent(payload)
    return ChatTurnResponse(
        session_id=payload.session_id,
        intent=result.get("intent", "GENERAL"),
        reply=result.get("final_response", ""),
        profile=UserProfile(**(result.get("profile") or {})),
        missing_slots=result.get("missing_slots", []),
        recommendations=result.get("scored_results", []),
    )


@router.post("/stream")
async def chat_stream(payload: ChatRequest) -> StreamingResponse:
    async def event_generator():
        status_event = {"type": "status", "message": "조건을 확인하고 추천 후보를 찾고 있어요."}
        yield f"event: status\ndata: {json.dumps(status_event, ensure_ascii=False)}\n\n"

        try:
            result = await _run_agent(payload)
        except Exception:  # noqa: BLE001 - 스트림 중 에러도 SSE로 전달
            logger.exception("Agent 실행 중 오류가 발생했습니다.")
            error_event = {
                "type": "error",
                "message": "일시적인 오류가 발생했어요. 잠시 후 다시 시도해주세요.",
            }
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        reply = result.get("final_response", "")
        if not reply:
            error_event = {
                "type": "error",
                "message": "답변을 만들지 못했어요. 조건을 조금 더 구체적으로 입력해 다시 시도해주세요.",
            }
            yield f"event: error\ndata: {json.dumps(error_event, ensure_ascii=False)}\n\n"
            return

        for i in range(0, len(reply), _STREAM_CHUNK_SIZE):
            chunk = {"type": "token", "content": reply[i : i + _STREAM_CHUNK_SIZE]}
            yield f"event: token\ndata: {json.dumps(chunk, ensure_ascii=False)}\n\n"

        done_payload = {
            "type": "done",
            "intent": result.get("intent", "GENERAL"),
            "missing_slots": result.get("missing_slots", []),
            "recommendations": result.get("scored_results", []),
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
