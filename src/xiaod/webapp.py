"""Local FastAPI console for Xiao D. No secrets in responses."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
import logging
import threading

logger = logging.getLogger("xiaod.web")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from xiaod.messages import WEB_BUSY, WEB_EMPTY, WEB_FAILED, WEB_INTERRUPTED
from xiaod.settings import _project_root, get_settings

TERMINAL = frozenset({"done", "failed", "needs_human", "needs_feishu", "idle"})

_STAGE_LABEL = {
    "received": "已收到",
    "classified": "已分类",
    "ack": "开始处理",
    "audio_ready": "已取音频",
    "subtitle_ready": "已取字幕",
    "local_ready": "已读本地文件",
    "transcribed": "已转写",
    "purified": "已提纯",
    "done": "已交付",
    "needs_human": "需要你确认",
    "needs_feishu": "待接通飞书",
    "failed": "未完成",
    "idle": "空闲",
    "running": "处理中",
}


class JobCreate(BaseModel):
    text: str = Field(default="", max_length=4000)


class JobView(BaseModel):
    id: str
    text: str
    status: str
    stage: str
    reply: str
    title: str
    feishu_url: str
    article: str
    used_subtitle: bool
    permission_granted: bool
    errors: list[str]
    created_at: str
    updated_at: str


class ConfigView(BaseModel):
    has_llm: bool
    has_feishu: bool
    has_langsmith: bool
    whisper_model: str
    agent: str
    version: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_label(status: str) -> str:
    return _STAGE_LABEL.get(status, status or "处理中")


class JobStore:
    def __init__(self, runner: Callable[[str], dict[str, Any]]) -> None:
        self._runner = runner
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}

    def create(self, text: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError(WEB_EMPTY)
        with self._lock:
            busy = any(job["status"] not in TERMINAL for job in self._jobs.values())
            if busy:
                raise ValueError(WEB_BUSY)
            job_id = uuid4().hex[:12]
            job = {
                "id": job_id,
                "text": cleaned,
                "status": "running",
                "stage": _stage_label("ack"),
                "reply": "已收到，开始处理。",
                "title": "",
                "feishu_url": "",
                "article": "",
                "used_subtitle": False,
                "permission_granted": False,
                "errors": [],
                "created_at": _now(),
                "updated_at": _now(),
            }
            self._jobs[job_id] = job
        threading.Thread(target=self._run, args=(job_id, cleaned), name=f"xiaod-web-{job_id}", daemon=True).start()
        return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(job) for job in reversed(self._jobs.values())]

    def _apply(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            job.update(fields)
            job["updated_at"] = _now()

    def _run(self, job_id: str, text: str) -> None:
        try:
            result = self._runner(text)
        except Exception:
            logger.exception("job %s failed", job_id)
            self._apply(job_id, status="failed", stage=_stage_label("failed"), reply=WEB_INTERRUPTED)
            return
        status = str(result.get("status") or "failed")
        if status == "qa_failed":
            status = "failed"
        self._apply(
            job_id,
            status=status if status in TERMINAL else "failed",
            stage=_stage_label(status if status in TERMINAL else "failed"),
            reply=str(result.get("reply_message") or WEB_FAILED),
            title=str(result.get("title") or ""),
            feishu_url=str(result.get("feishu_url") or ""),
            article=str(result.get("article") or ""),
            used_subtitle=bool(result.get("used_subtitle")),
            permission_granted=bool(result.get("permission_granted")),
            errors=[str(item) for item in (result.get("errors") or [])],
        )


def _default_runner(text: str) -> dict[str, Any]:
    from xiaod.graph import run_text

    return dict(run_text(text))


def create_app(runner: Callable[[str], dict[str, Any]] | None = None) -> FastAPI:
    settings = get_settings()
    store = JobStore(runner or _default_runner)
    app = FastAPI(title="小D", version="0.1.0")
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[
            "http://127.0.0.1:5173",
            "http://localhost:5173",
            f"http://{settings.web_host}:{settings.web_port}",
        ],
        allow_methods=["GET", "POST"],
        allow_headers=["*"],
    )

    @app.get("/api/health")
    def health() -> dict[str, str]:
        return {"status": "ok"}

    @app.get("/api/config", response_model=ConfigView)
    def config() -> ConfigView:
        live = get_settings()
        return ConfigView(
            has_llm=live.has_llm,
            has_feishu=live.has_feishu,
            has_langsmith=live.has_langsmith,
            whisper_model=live.whisper_model,
            agent="音视频转录整理助理（小D）",
            version="0.1.0",
        )

    @app.post("/api/jobs", response_model=JobView)
    def create_job(body: JobCreate) -> JobView:
        try:
            return JobView.model_validate(store.create(body.text))
        except ValueError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc

    @app.get("/api/jobs", response_model=list[JobView])
    def list_jobs() -> list[JobView]:
        return [JobView.model_validate(job) for job in store.list()]

    @app.get("/api/jobs/{job_id}", response_model=JobView)
    def get_job(job_id: str) -> JobView:
        job = store.get(job_id)
        if not job:
            raise HTTPException(status_code=404, detail="没有找到这条任务。")
        return JobView.model_validate(job)

    dist = _project_root() / "web" / "dist"
    if dist.is_dir():
        assets = dist / "assets"
        if assets.is_dir():
            app.mount("/assets", StaticFiles(directory=assets), name="assets")

        @app.get("/")
        def index() -> FileResponse:
            return FileResponse(dist / "index.html")

        @app.get("/{page_path:path}")
        def spa(page_path: str) -> FileResponse:
            if page_path.startswith("api/"):
                raise HTTPException(status_code=404, detail="没有找到，检查链接或返回首页")
            target = dist / page_path
            if target.is_file():
                return FileResponse(target)
            return FileResponse(dist / "index.html")

    return app


def frontend_dir() -> Path:
    return _project_root() / "web"
