from __future__ import annotations

from app.graph.state import AgentState


def route_after_router(state: AgentState) -> str:
    return "extract_profile" if state.get("action") == "SEARCH" else "conversation"


def route_after_missing_slot(state: AgentState) -> str:
    return "ask_clarification" if state.get("missing_slots") else "search_policy"
