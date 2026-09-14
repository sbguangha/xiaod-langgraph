"""Xiao D subgraph: subtitle → ASR → purify → Feishu doc."""

from __future__ import annotations

from langgraph.graph import END, START, StateGraph

from xiaod.nodes.xiaod_nodes import deliver_doc, fetch_source, purify, transcribe
from xiaod.state import JobState


def _after_fetch(state: JobState) -> str:
    if state.get("status") == "failed":
        return "end"
    if state.get("used_subtitle"):
        return "purify"
    return "transcribe"


def _after_transcribe(state: JobState) -> str:
    if state.get("status") == "failed":
        return "end"
    return "purify"


def _after_purify(state: JobState) -> str:
    if state.get("qa_ok"):
        return "deliver"
    return "end"


def build_xiaod_graph():
    builder = StateGraph(JobState)
    builder.add_node("fetch_source", fetch_source)
    builder.add_node("transcribe", transcribe)
    builder.add_node("purify", purify)
    builder.add_node("deliver", deliver_doc)
    builder.add_edge(START, "fetch_source")
    builder.add_conditional_edges(
        "fetch_source",
        _after_fetch,
        {"transcribe": "transcribe", "purify": "purify", "end": END},
    )
    builder.add_conditional_edges(
        "transcribe",
        _after_transcribe,
        {"purify": "purify", "end": END},
    )
    builder.add_conditional_edges(
        "purify",
        _after_purify,
        {"deliver": "deliver", "end": END},
    )
    builder.add_edge("deliver", END)
    return builder.compile()
