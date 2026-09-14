import json
import threading
from pathlib import Path

from fastapi.testclient import TestClient

from xiaod.messages import ASK_UNSUPPORTED_SOCIAL, WEB_BUSY, WEB_EMPTY, WEB_INTERRUPTED, WEB_STOPPED
from xiaod.nodes.xiaod_nodes import job_dir_name
from xiaod.webapp import create_app


def test_config_has_no_secrets() -> None:
    client = TestClient(create_app(runner=lambda text: {"status": "done", "reply_message": "ok"}))
    res = client.get("/api/config")
    assert res.status_code == 200
    body = res.json()
    assert "feishu_app_secret" not in body
    assert "api_key" not in str(body).lower()
    assert body["agent"].startswith("音视频")
    assert isinstance(body["has_ytdlp"], bool)
    assert isinstance(body["has_ffmpeg"], bool)
    assert isinstance(body["has_whisper"], bool)


def test_create_and_poll_job() -> None:
    client = TestClient(create_app(runner=lambda text: {
        "status": "done",
        "reply_message": "整理完成，文档已创建。请点开确认目录和权限是否正常。",
        "title": "整理稿",
        "feishu_url": "https://feishu.cn/docx/abc",
        "article": "## 访谈里的判断\n亦仁说生财有术要做分享式提纯稿。",
        "used_subtitle": True,
        "permission_granted": True,
        "errors": [],
    }))
    created = client.post("/api/jobs", json={"text": "请转录 https://www.xiaoyuzhoufm.com/episode/abc"})
    assert created.status_code == 200
    job_id = created.json()["id"]
    body = created.json()
    for _ in range(40):
        detail = client.get(f"/api/jobs/{job_id}")
        assert detail.status_code == 200
        body = detail.json()
        if body["status"] != "running":
            break
        threading.Event().wait(0.05)
    assert body["status"] == "done"
    assert body["feishu_url"].startswith("https://")
    assert "404" not in body["reply"]
    assert "Traceback" not in body["reply"]


def test_empty_and_busy() -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked(text: str) -> dict:
        started.set()
        release.wait(timeout=2)
        return {"status": "done", "reply_message": "好了"}

    client = TestClient(create_app(runner=blocked))
    empty = client.post("/api/jobs", json={"text": "  "})
    assert empty.status_code == 400
    assert empty.json()["detail"] == WEB_EMPTY
    first = client.post("/api/jobs", json={"text": "请转录 https://youtu.be/abc"})
    assert first.status_code == 200
    assert started.wait(timeout=1)
    second = client.post("/api/jobs", json={"text": "请转录 https://youtu.be/def"})
    assert second.status_code == 400
    assert second.json()["detail"] == WEB_BUSY
    release.set()


def test_missing_job_is_human() -> None:
    client = TestClient(create_app(runner=lambda text: {"status": "done"}))
    res = client.get("/api/jobs/not-found")
    assert res.status_code == 404
    assert "没有找到" in res.json()["detail"]


def test_social_copy_constant() -> None:
    assert "小宇宙" in ASK_UNSUPPORTED_SOCIAL


def test_job_dir_name_is_windows_safe(tmp_path) -> None:
    name = job_dir_name("cli:18860e1b54")
    assert ":" not in name
    assert name == "cli-18860e1b54"
    created = tmp_path / "jobs" / name
    created.mkdir(parents=True)
    assert created.is_dir()


def test_poll_sees_mid_progress() -> None:
    from xiaod.progress import report_progress

    started = threading.Event()
    release = threading.Event()

    def runner(text: str) -> dict:
        report_progress(stage="正在转写", reply="正在转写，大约已完成 3/30 分钟。", progress=40)
        started.set()
        release.wait(timeout=2)
        return {"status": "done", "reply_message": "整理完成，文档已创建。请点开确认目录和权限是否正常。"}

    client = TestClient(create_app(runner=runner))
    created = client.post("/api/jobs", json={"text": "请转录 https://www.bilibili.com/video/BV1xx411c7mD"})
    job_id = created.json()["id"]
    assert created.status_code == 200
    assert started.wait(timeout=1)
    mid = client.get(f"/api/jobs/{job_id}").json()
    assert mid["status"] == "running"
    assert mid["stage"] == "正在转写"
    assert mid["progress"] == 40
    assert "已完成 3/30 分钟" in mid["reply"]
    release.set()
    body = mid
    for _ in range(40):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != "running":
            break
        threading.Event().wait(0.05)
    assert body["status"] == "done"
    assert body["progress"] == 100


def test_jobs_reload_from_disk(tmp_path: Path) -> None:
    path = tmp_path / "console_jobs.json"
    path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "keep123abc",
                        "text": "请转录 https://www.bilibili.com/video/BV1xx411c7mD",
                        "status": "done",
                        "stage": "已交付",
                        "reply": "整理完成，文档已创建。请点开确认目录和权限是否正常。",
                        "progress": 100,
                        "title": "整理稿",
                        "feishu_url": "https://feishu.cn/docx/abc",
                        "article": "## 访谈里的判断",
                        "used_subtitle": True,
                        "permission_granted": True,
                        "errors": [],
                        "created_at": "2026-09-14T00:00:00+00:00",
                        "updated_at": "2026-09-14T00:01:00+00:00",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    client = TestClient(create_app(runner=lambda text: {"status": "done"}, persist=path))
    listed = client.get("/api/jobs").json()
    assert listed[0]["id"] == "keep123abc"
    assert listed[0]["feishu_url"].startswith("https://")
    assert listed[0]["progress"] == 100
    detail = client.get("/api/jobs/keep123abc").json()
    assert detail["title"] == "整理稿"


def test_running_job_resumes_after_reload(tmp_path: Path) -> None:
    path = tmp_path / "console_jobs.json"
    path.write_text(
        json.dumps(
            {
                "jobs": [
                    {
                        "id": "run123abcde",
                        "text": "请转录 https://www.bilibili.com/video/BV1xx411c7mD",
                        "status": "running",
                        "stage": "正在转写",
                        "reply": "正在转写，大约已完成 3/30 分钟。",
                        "progress": 40,
                        "title": "",
                        "feishu_url": "",
                        "article": "",
                        "used_subtitle": False,
                        "permission_granted": False,
                        "errors": [],
                        "created_at": "2026-09-14T00:00:00+00:00",
                        "updated_at": "2026-09-14T00:01:00+00:00",
                    }
                ]
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    seen: list[bool] = []

    def runner(text: str, thread_id: str = "", resume: bool = False) -> dict:
        seen.append(resume)
        return {"status": "done", "reply_message": "整理完成，文档已创建。请点开确认目录和权限是否正常。"}

    client = TestClient(create_app(runner=runner, persist=path))
    body = client.get("/api/jobs/run123abcde").json()
    for _ in range(40):
        if body["status"] != "running":
            break
        threading.Event().wait(0.05)
        body = client.get("/api/jobs/run123abcde").json()
    assert True in seen
    assert body["status"] == "done"
    assert body["progress"] == 100


def test_stop_job_releases_queue() -> None:
    started = threading.Event()
    release = threading.Event()

    def blocked(text: str) -> dict:
        started.set()
        release.wait(timeout=2)
        return {"status": "done", "reply_message": "好了"}

    client = TestClient(create_app(runner=blocked))
    first = client.post("/api/jobs", json={"text": "请转录 https://youtu.be/abc"})
    job_id = first.json()["id"]
    assert started.wait(timeout=1)
    stopped = client.post(f"/api/jobs/{job_id}/stop")
    assert stopped.status_code == 200
    assert stopped.json()["status"] == "stopped"
    assert stopped.json()["reply"] == WEB_STOPPED
    second = client.post("/api/jobs", json={"text": "请转录 https://youtu.be/def"})
    assert second.status_code == 200
    release.set()


def test_runner_exception_is_human() -> None:
    def boom(text: str) -> dict:
        raise RuntimeError("directory name is invalid")

    client = TestClient(create_app(runner=boom))
    created = client.post("/api/jobs", json={"text": "请转录 https://www.bilibili.com/video/BV1xx411c7mD"})
    job_id = created.json()["id"]
    body = created.json()
    for _ in range(40):
        body = client.get(f"/api/jobs/{job_id}").json()
        if body["status"] != "running":
            break
        threading.Event().wait(0.05)
    assert body["status"] == "failed"
    assert body["reply"] == WEB_INTERRUPTED
    assert "换一条公开链接" not in body["reply"]
