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


def test_parent_rejects_minutes() -> None:
    builder = StateGraph(JobState)
    builder.add_node("classify", classify_node)
    builder.add_node("human", ask_human)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges("classify", _route, {"human": "human", "xiaod": END, "status": END})
    builder.add_edge("human", END)
    state = builder.compile().invoke(empty_state("https://example.feishu.cn/minutes/obcnxxxxx"))
    assert state["pending_human"] == "unsupported_minutes"
    assert "不处理飞书妙记" in state["reply_message"]


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
    assert "不采集" in state["reply_message"]


def test_build_parent_graph_compiles() -> None:
    app = build_parent_graph()
    assert app is not None


def test_same_user_two_threads_stay_isolated(tmp_path, monkeypatch) -> None:
    from xiaod import graph as g

    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    g.get_app.cache_clear()
    try:
        first = g.run_text("https://v.douyin.com/aaa/", open_id="ou_iso", thread_id="feishu:ou_iso:m1")
        second = g.run_text("https://v.douyin.com/bbb/", open_id="ou_iso", thread_id="feishu:ou_iso:m2")
        assert first["thread_id"] == "feishu:ou_iso:m1"
        assert second["thread_id"] == "feishu:ou_iso:m2"
        stored_first = g.read_thread("feishu:ou_iso:m1")
        stored_second = g.read_thread("feishu:ou_iso:m2")
        assert stored_first is not None and stored_second is not None
        assert "aaa" in stored_first["input_text"]
        assert "bbb" in stored_second["input_text"]
    finally:
        g.get_app.cache_clear()


def test_sqlite_memory_roundtrip(tmp_path, monkeypatch) -> None:
    from xiaod import graph as g

    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    g.get_app.cache_clear()
    try:
        first = g.run_text("https://v.douyin.com/iAbcdefg/", thread_id="web:mem1")
        stored = g.read_thread("web:mem1")
        assert stored is not None
        assert stored["route"] == "human"
        assert stored["reply_message"] == first["reply_message"]
        assert "不采集" in stored["reply_message"]
        again = g.run_text("ignored", thread_id="web:mem1", resume=True)
        assert again["reply_message"] == first["reply_message"]
        assert g.thread_is_open("web:mem1") is False
    finally:
        g.get_app.cache_clear()
