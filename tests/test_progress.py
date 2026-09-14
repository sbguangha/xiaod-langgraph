from xiaod.progress import report_progress, reset_progress_handler, set_progress_handler


def test_report_progress_is_noop_without_handler() -> None:
    report_progress(stage="正在转写", reply="正在转写。", progress=40)


def test_report_progress_clamps_and_skips_empty() -> None:
    seen: list[dict] = []
    token = set_progress_handler(seen.append)
    try:
        report_progress()
        report_progress(stage="正在转写", progress=140)
        report_progress(reply="还在处理", progress=-3)
    finally:
        reset_progress_handler(token)
    assert seen == [
        {"stage": "正在转写", "progress": 100},
        {"reply": "还在处理", "progress": 0},
    ]
