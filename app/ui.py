"""Gradio 기반 데모 채팅 UI (선택 사항).

FastAPI 백엔드(app/main.py)의 정적 UI가 기본 데모 화면이며, 이 파일은
Agent 로직을 직접 호출하는 대체 데모 UI다. 백엔드 Agent의 배포/완성도가
프로젝트 평가의 핵심이므로, 프론트엔드는 최소한의 채팅형 UI로 유지한다.

실행: uv sync --extra ui && uv run python -m app.ui
"""

from __future__ import annotations

import uuid

from app.graph.graph import get_agent_graph

_graph = get_agent_graph()
_SESSION_ID = str(uuid.uuid4())


async def _run(message: str) -> str:
    config = {"configurable": {"thread_id": _SESSION_ID}}
    result = await _graph.ainvoke({"user_input": message}, config=config)
    return result.get("final_response", "")


def build_ui():
    import gradio as gr

    async def respond(message: str, chat_history: list[tuple[str, str]]):
        reply = await _run(message)
        chat_history = chat_history + [(message, reply)]
        return "", chat_history

    with gr.Blocks(title="정책나침반") as demo:
        gr.Markdown("## 🧭 정책나침반\n조건에 맞는 정부 지원사업을 찾아드려요.")
        chatbot = gr.Chatbot()
        msg = gr.Textbox(
            placeholder="예: 대학 졸업한지 6개월 됐고 취업 준비 중인데 받을 수 있는 지원금 있어?"
        )
        msg.submit(respond, [msg, chatbot], [msg, chatbot])

    return demo


if __name__ == "__main__":
    build_ui().launch()
