"""채팅 API 라우트.

/api/chat : 동기 방식 (테스트/단순 클라이언트용)
/api/chat/stream : SSE 스트리밍 방식

MVP 범위의 스트리밍은 그래프 실행이 끝난 최종 응답을 자연스러운 청크
단위로 점진 전송하는 방식이다 (LLM 토큰 단위 스트리밍은 추후 개선 과제).
"""

from __future__ import annotations

import json
import logging
from collections.abc import Callable

from fastapi import APIRouter
from fastapi.responses import StreamingResponse

from app.core.observability import create_langfuse_handler, get_langfuse_client, langfuse_trace_context
from app.core.privacy import detect_sensitive_data, privacy_guard_reply, redact_sensitive_text
from app.graph.graph import get_agent_graph
from app.graph.scoring import deadline_status
from app.repositories.chat_memory import SupabaseChatMemoryRepository
from app.repositories.feedback import SupabaseFeedbackRepository
from app.schemas.chat import ChatRequest, ChatTurnResponse, RecommendationFeedbackRequest, UserProfile

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chat", tags=["chat"])

_STREAM_CHUNK_SIZE = 24
_MAX_RECOMMENDATIONS = 3  # app/core/prompts.py의 "최대 3개 결과" 규칙과 맞춘 상한
_chat_memory = SupabaseChatMemoryRepository()
_feedback_repo = SupabaseFeedbackRepository()


def _result_status_message(result: dict) -> str:
    """Return a user-facing progress message from the validated router result."""

    if result.get("privacy_blocked"):
        return "민감정보를 감지해 입력을 보호 처리했어요."

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


def _format_cost(value: str | None) -> str | None:
    """'582560' 같은 순수 숫자 문자열을 '582,560원'으로 바꾼다.
    이미 단위/문자가 섞여 있거나 숫자가 아니면 원본 그대로 둔다."""

    if not value or not value.isdigit():
        return value
    return f"{int(value):,}원"


def _training_to_recommendation(item: dict) -> dict:
    cost_text = _format_cost(item.get("actual_cost")) or _format_cost(item.get("cost")) or "문의 필요"
    policy = {
        "id": item.get("course_id", ""),
        "title": item.get("title", ""),
        "agency": item.get("institution") or "",
        "category": "훈련과정",
        "target_description": item.get("target") or "",
        "region": [item["region"]] if item.get("region") else ["전국"],
        "min_age": None,
        "max_age": None,
        "apply_start": item.get("start_date"),
        "apply_end": item.get("end_date"),
        "apply_method": item.get("contact") or "고용24 참조",
        "support_content": f"훈련비: {cost_text}",
        "source_url": item.get("detail_url") or item.get("institution_url") or "",
        "match_scope": "nationwide",
        "distance_km": None,
    }
    return {
        "policy": policy,
        "match_score": 1.0,
        "evidence_coverage": 1.0,
        "match_reasons": ["검색 조건에 맞는 훈련과정으로 조회됐어요."],
        "follow_up_checks": [],
        "hard_mismatches": [],
        "is_recommendable": True,
        "recommendation_scope": "nationwide",
        "deadline_status": deadline_status(item.get("end_date")),
    }


_YOUTH_SCOPE_TO_RECOMMENDATION_SCOPE = {
    "exact": "exact",
    "nationwide": "nationwide",
    "nearby": "nearby_reference",
    "unknown": "nationwide",
}


def _youth_policy_to_recommendation(item: dict) -> dict:
    match_scope = item.get("match_scope") or "unknown"
    recommendation_scope = _YOUTH_SCOPE_TO_RECOMMENDATION_SCOPE.get(match_scope, "nationwide")
    is_recommendable = match_scope != "nearby"

    reasons = ["조건에 맞는 청년정책으로 검색됐어요."]
    if match_scope == "nearby":
        distance = item.get("distance_km")
        distance_text = f" 약 {distance:g}km" if isinstance(distance, int | float) else ""
        reasons = [f"요청 지역에서{distance_text} 떨어진 지역의 참고 결과예요."]

    policy = {
        "id": item.get("policy_id", ""),
        "title": item.get("title", ""),
        "agency": item.get("organization") or "",
        "category": "청년정책",
        "target_description": item.get("target_summary") or "",
        "region": [item["region"]] if item.get("region") else ["전국"],
        "min_age": None,
        "max_age": None,
        "apply_start": item.get("application_period"),
        "apply_end": None,
        "apply_method": item.get("application_method") or "",
        "support_content": item.get("support_summary") or "",
        "source_url": item.get("detail_url") or "",
        "match_scope": match_scope,
        "distance_km": item.get("distance_km"),
    }
    return {
        "policy": policy,
        "match_score": 1.0 if is_recommendable else 0.0,
        "evidence_coverage": 1.0,
        "match_reasons": reasons,
        "follow_up_checks": [],
        "hard_mismatches": [],
        "is_recommendable": is_recommendable,
        "recommendation_scope": recommendation_scope,
        "deadline_status": deadline_status(item.get("business_end_date")),
    }


def _dedupe_by_title(items: list[dict], *, title_of: Callable[[dict], str]) -> list[dict]:
    """같은 과정/정책이 회차·페이지네이션 등으로 제목이 같은 채 여러 번 나오면
    첫 번째 항목만 남긴다 (예: 같은 훈련과정의 다른 회차)."""

    seen: set[str] = set()
    deduped: list[dict] = []
    for item in items:
        title = title_of(item).strip()
        if title and title in seen:
            continue
        if title:
            seen.add(title)
        deduped.append(item)
    return deduped


def _build_recommendations(result: dict) -> list[dict]:
    """scored_results(기업마당) 외에 training_results/youth_policy_results 경로로
    나온 결과도 프론트 카드용 형태(PolicySearchResult 형태)로 변환해 반환한다.
    fallback_reason이 있는 항목(실제 검색 결과가 아닌 안내용 합성 레코드)은 제외하고,
    답변 텍스트와 동일하게 중복 제거 후 최대 _MAX_RECOMMENDATIONS개로 제한한다.
    """

    scored = result.get("scored_results") or []
    if scored:
        deduped = _dedupe_by_title(scored, title_of=lambda r: r.get("policy", {}).get("title") or "")
        return deduped[:_MAX_RECOMMENDATIONS]

    training = [item for item in result.get("training_results") or [] if not item.get("fallback_reason")]
    if training:
        training = _dedupe_by_title(training, title_of=lambda item: item.get("title") or "")[:_MAX_RECOMMENDATIONS]
        return [_training_to_recommendation(item) for item in training]

    youth = [item for item in result.get("youth_policy_results") or [] if not item.get("fallback_reason")]
    if youth:
        youth = _dedupe_by_title(youth, title_of=lambda item: item.get("title") or "")[:_MAX_RECOMMENDATIONS]
        return [_youth_policy_to_recommendation(item) for item in youth]

    return []


async def _run_agent(payload: ChatRequest) -> dict:
    memory = await _chat_memory.load(payload.session_id)
    profile = payload.profile_defaults.model_dump(exclude_none=True) if payload.profile_defaults else {}
    if memory.profile:
        # 같은 채팅에서 확인한 조건이 브라우저 기본값보다 우선한다.
        profile.update(memory.profile)

    detected_sensitive_data = detect_sensitive_data(payload.message)
    if detected_sensitive_data:
        safe_message = redact_sensitive_text(payload.message)
        reply = privacy_guard_reply(detected_sensitive_data)
        await _chat_memory.save_turn(
            session_id=payload.session_id,
            user_message=safe_message,
            assistant_message=reply,
            intent="PRIVACY_BLOCKED",
            profile=profile,
            pending_request=memory.pending_request,
        )
        return {
            "intent": "PRIVACY_BLOCKED",
            "action": "RESPOND",
            "response_mode": "out_of_scope",
            "request_kind": "general",
            "final_response": reply,
            "profile": profile,
            "pending_request": memory.pending_request,
            "missing_slots": [],
            "search_results": [],
            "youth_policy_results": [],
            "training_results": [],
            "recruitment_results": [],
            "scored_results": [],
            "privacy_blocked": True,
        }

    graph = get_agent_graph()
    config: dict = {
        "configurable": {"thread_id": payload.session_id},
        "run_name": "policy-compass-chat",
    }
    langfuse_client = get_langfuse_client()
    # 그래프 실행이 끝나면 콜백이 만든 span의 컨텍스트가 닫혀서 사후에는 trace_id를
    # 조회할 수 없다. 그래서 미리 하나 만들어 CallbackHandler에 그대로 주입한다
    # (나중에 사용자 피드백을 이 trace_id로 연결하기 위함).
    trace_id = langfuse_client.create_trace_id() if langfuse_client is not None else None
    langfuse_handler = create_langfuse_handler(trace_id=trace_id)
    if langfuse_handler is not None:
        config["callbacks"] = [langfuse_handler]
    initial_state: dict = {
        "session_id": payload.session_id,
        "user_input": payload.message,
    }
    if memory.messages:
        initial_state["conversation_history"] = memory.messages
    if profile:
        initial_state["profile"] = profile
    if memory.pending_request:
        initial_state["pending_request"] = memory.pending_request

    with langfuse_trace_context(payload.session_id, enabled=langfuse_handler is not None):
        result = await graph.ainvoke(initial_state, config=config)
    result["trace_id"] = trace_id if langfuse_handler is not None else None
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
        recommendations=_build_recommendations(result),
        trace_id=result.get("trace_id"),
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
            "recommendations": _build_recommendations(result),
            "profile_defaults": {
                key: value for key in ("age", "region") if (value := (result.get("profile") or {}).get(key)) is not None
            },
            "trace_id": result.get("trace_id"),
        }
        yield f"event: done\ndata: {json.dumps(done_payload, ensure_ascii=False)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")


@router.post("/feedback")
async def submit_recommendation_feedback(payload: RecommendationFeedbackRequest) -> dict[str, bool]:
    saved = await _feedback_repo.save(
        session_id=payload.session_id,
        message_id=payload.message_id,
        trace_id=payload.trace_id,
        rating=payload.rating,
    )

    if payload.trace_id:
        client = get_langfuse_client()
        if client is not None:
            client.create_score(
                trace_id=payload.trace_id,
                name="user-thumbs",
                value=1 if payload.rating == "up" else 0,
                data_type="BOOLEAN",
            )

    return {"saved": saved}
