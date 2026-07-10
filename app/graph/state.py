from __future__ import annotations

from typing import TypedDict


class AgentState(TypedDict, total=False):
    """LangGraph 그래프에서 노드 간에 전달되는 상태.

    `profile` 은 session_id(thread_id) 기준으로 checkpointer에 누적 저장되어,
    같은 대화 내에서 거주지역/취업상태 등을 반복해서 묻지 않도록 한다.
    """

    session_id: str
    user_input: str
    intent: str
    request_kind: str
    profile: dict
    missing_slots: list[str]
    search_results: list[dict]
    youth_policy_results: list[dict]
    training_results: list[dict]
    recruitment_results: list[dict]
    scored_results: list[dict]
    final_response: str
    guardrail_notes: list[str]
