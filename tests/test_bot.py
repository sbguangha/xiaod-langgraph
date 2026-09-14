from xiaod.bot.feishu_ws import ProgressReporter, handle_text, status_for_user
from xiaod.bot.jobs import bot_thread_id, latest_job, remember_job
from xiaod.messages import ACK_GENERIC, STATUS_IDLE, STATUS_RUNNING


def test_bot_thread_id_is_per_message() -> None:
    first = bot_thread_id("ou_1", "om_aaa")
    second = bot_thread_id("ou_1", "om_bbb")
    assert first != second
    assert first.startswith("feishu:ou_1:")
    assert bot_thread_id("ou_1", "om_aaa") == first


def test_handle_text_isolates_threads(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    seen: list[str] = []

    def runner(text: str, *, open_id: str = "", chat_id: str = "", thread_id: str = "", resume: bool = False):
        seen.append(thread_id)
        return {"reply_message": f"完成 {text}", "status": "done", "thread_id": thread_id}

    a = handle_text("https://youtu.be/a", open_id="ou_1", message_id="om_1", runner=runner)
    b = handle_text("https://youtu.be/b", open_id="ou_1", message_id="om_2", runner=runner)
    assert seen[0] != seen[1]
    assert seen[0] == bot_thread_id("ou_1", "om_1")
    assert seen[1] == bot_thread_id("ou_1", "om_2")
    assert "youtu.be/a" in a
    assert "youtu.be/b" in b
    assert latest_job("ou_1")["thread_id"] == seen[1]


def test_status_uses_latest_job_progress(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    assert status_for_user("ou_2") == STATUS_IDLE
    remember_job("ou_2", "feishu:ou_2:om_x", status="running", reply="正在转写，大约已完成 3/10 分钟。")
    assert "已完成 3/10" in status_for_user("ou_2")
    remember_job("ou_2", "feishu:ou_2:om_y", status="done", reply="整理完成，文档已创建。")
    assert "文档已创建" in handle_text("现在进度怎么样了", open_id="ou_2", message_id="om_status")


def test_progress_reporter_throttles_same_stage(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    remember_job("ou_3", "feishu:ou_3:om_z", status="running", reply=ACK_GENERIC)
    sent: list[str] = []
    reporter = ProgressReporter(sent.append, open_id="ou_3", thread_id="feishu:ou_3:om_z", min_interval=30)
    reporter({"stage": "开始处理", "reply": ACK_GENERIC, "progress": 5})
    reporter({"stage": "正在转写", "reply": "正在加载语音识别模型。第一次会下载模型，请稍等。", "progress": 28})
    reporter({"stage": "正在转写", "reply": "正在转写，大约已完成 3/10 分钟。", "progress": 40})
    reporter({"stage": "正在整理文稿", "reply": "正在把转写稿整理成分享式提纯稿。", "progress": 90})
    assert sent == [
        "正在加载语音识别模型。第一次会下载模型，请稍等。",
        "正在把转写稿整理成分享式提纯稿。",
    ]
    job = latest_job("ou_3")
    assert job["stage"] == "正在整理文稿"
    assert job["progress"] == 90
    assert STATUS_RUNNING not in sent
