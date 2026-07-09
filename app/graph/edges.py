from __future__ import annotations

from app.graph.state import AgentState


def route_after_router(state: AgentState) -> str:
    intent = state.get("intent", "GENERAL")
    if intent in ("RECOMMEND", "ELIGIBILITY_CHECK"):
        return "extract_profile"
    if intent == "EXPLAIN":
        return "explain"
    if intent == "OUT_OF_SCOPE":
        return "out_of_scope"
    return "general"


def route_after_missing_slot(state: AgentState) -> str:
    return "ask_clarification" if state.get("missing_slots") else "search_policy"
