"""Local FastAPI console for Xiao D. No secrets in responses."""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable
from uuid import uuid4
import json
import logging
import threading

logger = logging.getLogger("xiaod.web")

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

from xiaod.messages import WEB_BUSY, WEB_EMPTY, WEB_FAILED, WEB_INTERRUPTED, WEB_RESUMED, WEB_STOPPED
from xiaod.progress import reset_progress_handler, set_progress_handler
from xiaod.settings import _project_root, get_settings

TERMINAL = frozenset({"done", "failed", "needs_human", "needs_feishu", "idle", "stopped"})

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
    "stopped": "已停止",
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
    progress: int = 0
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
    has_ytdlp: bool
    has_ffmpeg: bool
    has_whisper: bool
    whisper_model: str
    agent: str
    version: str


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _stage_label(status: str) -> str:
    return _STAGE_LABEL.get(status, status or "处理中")


def _blank_job(job_id: str, text: str) -> dict[str, Any]:
    return {
        "id": job_id,
        "thread_id": f"web:{job_id}",
        "text": text,
        "status": "running",
        "stage": _stage_label("ack"),
        "reply": "已收到，开始处理。",
        "progress": 0,
        "title": "",
        "feishu_url": "",
        "article": "",
        "used_subtitle": False,
        "permission_granted": False,
        "errors": [],
        "created_at": _now(),
        "updated_at": _now(),
    }


def _normalize_job(raw: dict[str, Any]) -> dict[str, Any] | None:
    job_id = str(raw.get("id") or "").strip()
    text = str(raw.get("text") or "").strip()
    if not job_id or not text:
        return None
    job = _blank_job(job_id, text)
    job.update({key: raw[key] for key in job if key in raw})
    job["id"] = job_id
    job["text"] = text
    job["thread_id"] = str(raw.get("thread_id") or f"web:{job_id}")
    job["errors"] = [str(item) for item in (raw.get("errors") or [])]
    job["used_subtitle"] = bool(raw.get("used_subtitle"))
    job["permission_granted"] = bool(raw.get("permission_granted"))
    try:
        job["progress"] = max(0, min(100, int(raw.get("progress") or 0)))
    except (TypeError, ValueError):
        job["progress"] = 0
    return job


class JobStore:
    def __init__(
        self,
        runner: Callable[..., dict[str, Any]],
        persist_path: Path | None = None,
    ) -> None:
        self._runner = runner
        self._persist_path = persist_path
        self._lock = threading.Lock()
        self._jobs: dict[str, dict[str, Any]] = {}
        self._cancelled: set[str] = set()
        self._load()
        self._resume_orphans()

    def create(self, text: str) -> dict[str, Any]:
        cleaned = (text or "").strip()
        if not cleaned:
            raise ValueError(WEB_EMPTY)
        with self._lock:
            busy = any(job["status"] not in TERMINAL for job in self._jobs.values())
            if busy:
                raise ValueError(WEB_BUSY)
            job_id = uuid4().hex[:12]
            job = _blank_job(job_id, cleaned)
            self._jobs[job_id] = job
            self._dump_locked()
        self._spawn(job_id, cleaned, resume=False)
        return dict(job)

    def get(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            return dict(job) if job else None

    def list(self) -> list[dict[str, Any]]:
        with self._lock:
            return [dict(job) for job in reversed(self._jobs.values())]

    def stop(self, job_id: str) -> dict[str, Any] | None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return None
            if job["status"] in TERMINAL:
                return dict(job)
            self._cancelled.add(job_id)
        self._apply(job_id, status="stopped", stage=_stage_label("stopped"), reply=WEB_STOPPED)
        found = self.get(job_id)
        return found

    def _spawn(self, job_id: str, text: str, *, resume: bool) -> None:
        threading.Thread(
            target=self._run,
            args=(job_id, text, resume),
            name=f"xiaod-web-{job_id}",
            daemon=True,
        ).start()

    def _resume_orphans(self) -> None:
        with self._lock:
            orphans = [
                (job["id"], job["text"], str(job.get("thread_id") or f"web:{job['id']}"))
                for job in self._jobs.values()
                if job["status"] not in TERMINAL
            ]
        for job_id, text, thread_id in orphans:
            if self._finish_if_graph_done(job_id, thread_id):
                continue
            self._apply(job_id, reply=WEB_RESUMED)
            self._spawn(job_id, text, resume=True)

    def _finish_if_graph_done(self, job_id: str, thread_id: str) -> bool:
        if not self._persist_path:
            return False
        try:
            from xiaod.graph import read_thread, thread_is_open

            state = read_thread(thread_id)
            if not state or thread_is_open(thread_id):
                return False
            status = str(state.get("status") or "")
            if status not in TERMINAL:
                return False
        except Exception:
            return False
        extra: dict[str, Any] = {"progress": 100} if status == "done" else {}
        self._apply(
            job_id,
            status=status,
            stage=_stage_label(status),
            reply=str(state.get("reply_message") or WEB_FAILED),
            title=str(state.get("title") or ""),
            feishu_url=str(state.get("feishu_url") or ""),
            article=str(state.get("article") or ""),
            used_subtitle=bool(state.get("used_subtitle")),
            permission_granted=bool(state.get("permission_granted")),
            errors=[str(item) for item in (state.get("errors") or [])],
            **extra,
        )
        return True

    def _load(self) -> None:
        path = self._persist_path
        if not path or not path.is_file():
            return
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            logger.exception("could not read job memory %s", path)
            return
        rows = payload.get("jobs") if isinstance(payload, dict) else payload
        if not isinstance(rows, list):
            return
        for raw in rows:
            if not isinstance(raw, dict):
                continue
            job = _normalize_job(raw)
            if job:
                self._jobs[job["id"]] = job

    def _dump_locked(self) -> None:
        path = self._persist_path
        if not path:
            return
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"jobs": list(self._jobs.values())}
        tmp = path.with_name(path.name + ".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
        tmp.replace(path)

    def _apply(self, job_id: str, **fields: Any) -> None:
        with self._lock:
            job = self._jobs.get(job_id)
            if not job:
                return
            if job_id in self._cancelled and job["status"] in TERMINAL:
                return
            job.update(fields)
            job["updated_at"] = _now()
            self._dump_locked()

    def _invoke_runner(self, text: str, thread_id: str, resume: bool) -> dict[str, Any]:
        try:
            return self._runner(text, thread_id=thread_id, resume=resume)
        except TypeError:
            try:
                return self._runner(text, thread_id=thread_id)
            except TypeError:
                return self._runner(text)

    def _run(self, job_id: str, text: str, resume: bool = False) -> None:
        thread_id = f"web:{job_id}"

        def on_progress(fields: dict[str, str | int]) -> None:
            if job_id in self._cancelled:
                return
            patch: dict[str, str | int] = {}
            if "stage" in fields:
                patch["stage"] = str(fields["stage"])
            if "reply" in fields:
                patch["reply"] = str(fields["reply"])
            if "progress" in fields:
                patch["progress"] = int(fields["progress"])
            if patch:
                self._apply(job_id, **patch)

        token = set_progress_handler(on_progress)
        try:
            result = self._invoke_runner(text, thread_id, resume)
        except Exception:
            logger.exception("job %s failed", job_id)
            if job_id not in self._cancelled:
                self._apply(job_id, status="failed", stage=_stage_label("failed"), reply=WEB_INTERRUPTED)
            return
        finally:
            reset_progress_handler(token)
        if job_id in self._cancelled:
            return
        status = str(result.get("status") or "failed")
        if status == "qa_failed":
            status = "failed"
        final = status if status in TERMINAL else "failed"
        extra: dict[str, Any] = {}
        if final == "done":
            extra["progress"] = 100
        self._apply(
            job_id,
            status=final,
            stage=_stage_label(final),
            reply=str(result.get("reply_message") or WEB_FAILED),
            title=str(result.get("title") or ""),
            feishu_url=str(result.get("feishu_url") or ""),
            article=str(result.get("article") or ""),
            used_subtitle=bool(result.get("used_subtitle")),
            permission_granted=bool(result.get("permission_granted")),
            errors=[str(item) for item in (result.get("errors") or [])],
            **extra,
        )


def _default_runner(text: str, *, thread_id: str = "", resume: bool = False) -> dict[str, Any]:
    from xiaod.graph import run_text

    return dict(run_text(text, thread_id=thread_id, resume=resume))


def create_app(
    runner: Callable[..., dict[str, Any]] | None = None,
    *,
    persist: bool | Path = False,
) -> FastAPI:
    from xiaod.tools.media import check_tool_stack, ensure_ffmpeg_on_path

    settings = get_settings()
    ensure_ffmpeg_on_path(settings)
    if persist is True:
        persist_path: Path | None = settings.data_dir / "console_jobs.json"
    elif isinstance(persist, Path):
        persist_path = persist
    else:
        persist_path = None
    store = JobStore(runner or _default_runner, persist_path=persist_path)
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
        stack = check_tool_stack(live)
        return ConfigView(
            has_llm=live.has_llm,
            has_feishu=live.has_feishu,
            has_langsmith=live.has_langsmith,
            has_ytdlp=bool(stack["yt_dlp"]),
            has_ffmpeg=bool(stack["ffmpeg"]),
            has_whisper=bool(stack["faster_whisper"]),
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

    @app.post("/api/jobs/{job_id}/stop", response_model=JobView)
    def stop_job(job_id: str) -> JobView:
        job = store.stop(job_id)
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
            return FileResponse(dist / "index.html", media_type="text/html; charset=utf-8")

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
