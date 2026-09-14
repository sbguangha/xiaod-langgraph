from xiaod.nodes.classify import classify_text, extract_urls


def test_xiaoyuzhou_goes_to_xiaod() -> None:
    result = classify_text("请转录 https://www.xiaoyuzhoufm.com/episode/6a49649f3fb7233cbf43c439")
    assert result.source_type == "xiaoyuzhou"
    assert result.route == "xiaod"


def test_bilibili_and_youtube() -> None:
    assert classify_text("https://www.bilibili.com/video/BV1xx411c7mD").route == "xiaod"
    assert classify_text("https://youtu.be/dQw4w9WgXcQ").source_type == "youtube"


def test_social_is_out_of_scope() -> None:
    douyin = classify_text("https://v.douyin.com/iAbcdefg/")
    assert douyin.route == "human"
    assert douyin.pending_human == "unsupported_social"
    assert classify_text("请转录 https://v.douyin.com/iAbcdefg/").route == "human"
    assert classify_text("https://www.xiaohongshu.com/explore/abc").route == "human"
    assert classify_text("https://mp.weixin.qq.com/s/abcdef").source_type == "wechat_mp"


def test_paywall_and_unknown() -> None:
    assert classify_text("这是付费课程 https://www.xiaoyuzhoufm.com/episode/1").route == "human"
    assert classify_text("你好").route == "human"


def test_status_without_url() -> None:
    assert classify_text("现在进度怎么样了").route == "status"
    from langgraph.graph import END, START, StateGraph

    from xiaod.graph import _route
    from xiaod.nodes.classify import classify_node
    from xiaod.nodes.reply import status_node
    from xiaod.state import JobState, empty_state

    builder = StateGraph(JobState)
    builder.add_node("classify", classify_node)
    builder.add_node("status", status_node)
    builder.add_edge(START, "classify")
    builder.add_conditional_edges(
        "classify",
        _route,
        {"status": "status", "xiaod": END, "human": END},
    )
    builder.add_edge("status", END)
    state = builder.compile().invoke(empty_state("现在进度怎么样了"))
    assert state["route"] == "status"
    assert state["status"] == "idle"
    assert "没有进行中" in state["reply_message"]


def test_extract_local_path() -> None:
    urls = extract_urls(r"用 whisper 转 D:\audio\talk.m4a")
    assert urls
    assert classify_text(urls[0]).source_type == "local"
