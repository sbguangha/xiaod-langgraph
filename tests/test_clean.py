from xiaod.nodes.clean import apply_typos, clean_transcript, qa_share_draft, rule_based_purify


def test_typos() -> None:
    assert "生财有术" in apply_typos("升财有数 和 一仁 用飞输")
    assert "亦仁" in apply_typos("一仁")
    assert "飞书" in apply_typos("飞输")


def test_strip_timestamp_and_speaker() -> None:
    raw = "00:12:03 说话人1：嗯那个生财有数真的强\n[01:02] 然后那个继续"
    cleaned = clean_transcript(raw)
    assert "00:" not in cleaned
    assert "说话人" not in cleaned
    assert "生财有术" in cleaned


def test_qa_rejects_summary_and_trash() -> None:
    summary = "\n".join(f"- 要点{i}" for i in range(10))
    ok, reasons = qa_share_draft(summary)
    assert not ok
    assert "summary" in reasons
    trash = "## 其他有效观点\n" + ("这是一段足够长的正文，用来避免 too_short。" * 4)
    ok, reasons = qa_share_draft(trash)
    assert not ok
    assert "trash_title" in reasons


def test_rule_purify_keeps_body() -> None:
    raw = (
        "00:01 亦仁说生财有术要做分享式提纯稿，不是三条要点。"
        "他把一场访谈里真正能复用的方法讲清楚，听众带走的是原话里的做法。"
        "整理时保留完整叙述，不去掉时间线和例子。"
    )
    text = rule_based_purify(raw, platform="小宇宙", title="访谈")
    ok, reasons = qa_share_draft(text)
    assert ok, reasons
    assert "分享式提纯稿" in text
