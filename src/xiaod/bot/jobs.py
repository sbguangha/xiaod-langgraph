"""Per-user Feishu job index. One LangGraph thread per message, not per person."""

from __future__ import annotations

from typing import Any
import json
import threading

from xiaod.settings import get_settings
from xiaod.state import new_thread_id

_LOCK = threading.Lock()
_MAX_JOBS = 20
TERMINAL = frozenset({"done", "failed", "needs_human", "needs_feishu", "idle", "stopped"})


def bot_thread_id(open_id: str = "", message_id: str = "") -> str:
    owner = (open_id or "anon").strip() or "anon"
    if message_id:
        safe = "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in message_id)
        return f"feishu:{owner}:{safe}"
    return new_thread_id(f"feishu:{owner}")


def _path():
    return get_settings().data_dir / "feishu_jobs.json"


def _load() -> dict[str, Any]:
    path = _path()
    if not path.is_file():
        return {}
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _dump(data: dict[str, Any]) -> None:
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_name(path.name + ".tmp")
    tmp.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    tmp.replace(path)


def remember_job(open_id: str, thread_id: str, **fields: Any) -> None:
    owner = (open_id or "anon").strip() or "anon"
    if not thread_id:
        return
    with _LOCK:
        data = _load()
        bucket = data.setdefault(owner, {"latest": "", "jobs": {}})
        jobs = bucket.setdefault("jobs", {})
        current = dict(jobs.get(thread_id) or {})
        current.update({key: value for key, value in fields.items() if value is not None})
        current["thread_id"] = thread_id
        jobs[thread_id] = current
        bucket["latest"] = thread_id
        keys = list(jobs)
        if len(keys) > _MAX_JOBS:
            for key in keys[:-_MAX_JOBS]:
                jobs.pop(key, None)
        data[owner] = bucket
        _dump(data)


def update_job(open_id: str, thread_id: str, **fields: Any) -> None:
    owner = (open_id or "anon").strip() or "anon"
    if not thread_id:
        return
    with _LOCK:
        data = _load()
        bucket = data.get(owner)
        if not isinstance(bucket, dict):
            return
        jobs = bucket.get("jobs")
        if not isinstance(jobs, dict) or thread_id not in jobs:
            return
        jobs[thread_id].update({key: value for key, value in fields.items() if value is not None})
        _dump(data)


def latest_job(open_id: str) -> dict[str, Any] | None:
    owner = (open_id or "anon").strip() or "anon"
    with _LOCK:
        bucket = _load().get(owner)
    if not isinstance(bucket, dict):
        return None
    jobs = bucket.get("jobs")
    if not isinstance(jobs, dict):
        return None
    thread_id = str(bucket.get("latest") or "")
    job = jobs.get(thread_id) if thread_id else None
    if isinstance(job, dict):
        return dict(job)
    if not jobs:
        return None
    last_key = next(reversed(list(jobs)))
    found = jobs.get(last_key)
    return dict(found) if isinstance(found, dict) else None
