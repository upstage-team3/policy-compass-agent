from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 그래프에서 노드 간에 전달되는 상태.

    `profile`, `conversation_history`, `pending_request`는 session_id 기준으로
    Supabase에도 저장되어 재시작 뒤 같은 조건을 반복해서 묻지 않도록 한다.
    """

    session_id: str
    user_input: str
    intent: str
    action: str
    response_mode: str
    request_kind: str
    search_query: str | None
    routing_source: str
    resumed_pending: bool
    profile: dict
    conversation_history: list[dict[str, str]]
    pending_request: dict
    search_context: dict
    missing_slots: list[str]
    search_results: list[dict]
    youth_policy_results: list[dict]
    training_results: list[dict]
    recruitment_results: list[dict]
    scored_results: list[dict]
    final_response: str
    guardrail_notes: list[str]
    privacy_blocked: bool
