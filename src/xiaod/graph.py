"""Parent router graph: official Xiao D audio/video loop only."""

from __future__ import annotations

from functools import lru_cache
import sqlite3

from langgraph.checkpoint.sqlite import SqliteSaver
from langgraph.graph import END, START, StateGraph

from xiaod.graphs.xiaod import build_xiaod_graph
from xiaod.nodes.classify import classify_node
from xiaod.nodes.reply import ack_route, ask_human, status_node
from xiaod.settings import get_settings
from xiaod.state import JobState, empty_state
from xiaod.tracing import configure_langsmith, trace_metadata, traceable


def _route(state: JobState) -> str:
    return state.get("route") or "human"


def build_parent_graph(checkpointer: SqliteSaver | None = None):
    builder = StateGraph(JobState)
    builder.add_node("classify", classify_node)
    builder.add_node("ack", ack_route)
    builder.add_node("xiaod", build_xiaod_graph())
    builder.add_node("human", ask_human)
    builder.add_node("status", status_node)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        _route,
        {
            "xiaod": "ack",
            "human": "human",
            "status": "status",
        },
    )
    builder.add_edge("ack", "xiaod")
    builder.add_edge("xiaod", END)
    builder.add_edge("human", END)
    builder.add_edge("status", END)
    return builder.compile(checkpointer=checkpointer)


def open_checkpointer() -> tuple[SqliteSaver, sqlite3.Connection]:
    settings = get_settings()
    db_path = settings.data_dir / "checkpoints.db"
    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(db_path), check_same_thread=False)
    return SqliteSaver(conn), conn


@lru_cache(maxsize=1)
def get_app():
    configure_langsmith()
    checkpointer, _conn = open_checkpointer()
    return build_parent_graph(checkpointer)


@traceable(name="xiaod")
def run_job(state: JobState, *, thread_id: str | None = None) -> JobState:
    configure_langsmith()
    app = get_app()
    config = {
        "configurable": {"thread_id": thread_id or state.get("thread_id") or "cli"},
        "metadata": trace_metadata(state),
        "run_name": state.get("route") or "xiaod",
    }
    result = app.invoke(state, config=config)
    return result


def run_text(text: str, *, open_id: str = "", chat_id: str = "", thread_id: str = "") -> JobState:
    state = empty_state(text, open_id=open_id, chat_id=chat_id, thread_id=thread_id)
    return run_job(state, thread_id=state["thread_id"])
