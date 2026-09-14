from langgraph.graph import END, START, StateGraph

from xiaod.graph import _route, build_parent_graph
from xiaod.nodes.classify import classify_node
from xiaod.nodes.reply import ask_human
from xiaod.state import JobState, empty_state


def test_parent_routes_media_to_ack() -> None:
    builder = StateGraph(JobState)
    builder.add_node("classify", classify_node)
    builder.add_edge(START, "classify")
    builder.add_edge("classify", END)
    only = builder.compile()
    state = only.invoke(empty_state("请转录 https://www.xiaoyuzhoufm.com/episode/abc"))
    assert _route(state) == "xiaod"


def test_parent_rejects_douyin() -> None:
    builder = StateGraph(JobState)
    builder.add_node("classify", classify_node)
    builder.add_node("human", ask_human)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", _route, {"human": "human", "xiaod": END, "status": END})
    builder.add_edge("human", END)
    app = builder.compile()
    state = app.invoke(empty_state("https://v.douyin.com/iAbcdefg/"))
    assert state["route"] == "human"
    assert "只整理公开播客" in state["reply_message"]


def test_build_parent_graph_compiles() -> None:
    app = build_parent_graph()
    assert app is not None
