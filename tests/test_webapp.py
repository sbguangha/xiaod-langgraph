import threading

from fastapi.testclient import TestClient

from xiaod.messages import ASK_UNSUPPORTED_SOCIAL, WEB_BUSY, WEB_EMPTY, WEB_INTERRUPTED
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
