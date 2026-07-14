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


def _result_status_message(result: dict) -> str:
    """Return a user-facing progress message from the validated router result."""

    request_kind = result.get("request_kind", "general")
    missing_slots = result.get("missing_slots") or []
    labels = {
        "youth_policy": "청년정책",
        "training": "고용24 훈련과정",
        "recruitment": "채용 보조정보",
        "business": "기업마당 지원사업",
    }

    if request_kind in labels:
        label = labels[request_kind]
        if missing_slots:
            return f"{label} 추천에 필요한 조건을 정리했어요."
        return f"{label} 검색 결과를 확인했어요."

    return {
        "EXPLAIN": "질문에 맞는 설명을 정리했어요.",
        "OUT_OF_SCOPE": "지원 가능한 상담 범위를 확인했어요.",
    }.get(result.get("intent", "GENERAL"), "대화 내용을 바탕으로 답변을 정리했어요.")


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
    profile = payload.profile_defaults.model_dump(exclude_none=True) if payload.profile_defaults else {}
    if memory.profile:
        # 같은 채팅에서 확인한 조건이 브라우저 기본값보다 우선한다.
        profile.update(memory.profile)
    if profile:
        initial_state["profile"] = profile
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
        status_event = {"type": "status", "message": "질문 의도와 필요한 정보를 확인하고 있어요."}
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

        routed_status_event = {"type": "status", "message": _result_status_message(result)}
        yield f"event: status\ndata: {json.dumps(routed_status_event, ensure_ascii=False)}\n\n"

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
            "profile_defaults": {
                key: value for key in ("age", "region") if (value := (result.get("profile") or {}).get(key)) is not None
            },
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")
