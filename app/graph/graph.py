"""LangGraph StateGraph 조립.

Router -> (Conversation | Profile Extractor -> Missing Slot -> Search ->
Eligibility Scorer -> Response) -> Guardrail 순서로 흐른다.
session_id 를 thread_id 로 사용하는 MemorySaver는 실행 중 상태를 유지하고,
API 경계의 Supabase 메모리는 재시작 뒤 최근 대화와 검색 계획을 복원한다.
"""

from __future__ import annotations

from langgraph.checkpoint.memory import MemorySaver
from langgraph.graph import END, StateGraph

from app.graph import edges as E
from app.graph import nodes as N
from app.graph.state import AgentState


def build_agent_graph():
    graph = StateGraph(AgentState)

    graph.add_node("route_intent", N.router_node)
    graph.add_node("extract_profile", N.profile_extractor_node)
    graph.add_node("check_missing_slots", N.missing_slot_node)
    graph.add_node("ask_clarification", N.clarification_node)
    graph.add_node("search_policy", N.policy_search_node)
    graph.add_node("score_eligibility", N.eligibility_scorer_node)
    graph.add_node("compose_response", N.response_node)
    graph.add_node("conversation", N.conversation_node)
    graph.add_node("guardrail", N.guardrail_node)

    graph.set_entry_point("route_intent")

    graph.add_conditional_edges(
        "route_intent",
        E.route_after_router,
        {
            "extract_profile": "extract_profile",
            "conversation": "conversation",
        },
    )

    graph.add_edge("extract_profile", "check_missing_slots")
    graph.add_conditional_edges(
        "check_missing_slots",
        E.route_after_missing_slot,
        {
            "ask_clarification": "ask_clarification",
            "search_policy": "search_policy",
        },
    )
    graph.add_edge("search_policy", "score_eligibility")
    graph.add_edge("score_eligibility", "compose_response")

    for terminal in ("ask_clarification", "compose_response", "conversation"):
        graph.add_edge(terminal, "guardrail")

    graph.add_edge("guardrail", END)

    return graph.compile(checkpointer=MemorySaver())


_agent_graph = None


def get_agent_graph():
    global _agent_graph  # noqa: PLW0603
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
