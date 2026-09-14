"""Parent-graph reply and human-gate nodes."""

from __future__ import annotations

from xiaod.messages import (
    ACK_MEDIA,
    ASK_PAYWALL,
    ASK_UNKNOWN,
    ASK_UNSUPPORTED_SOCIAL,
    STATUS_IDLE,
    STATUS_RUNNING,
)
from xiaod.progress import report_progress
from xiaod.state import JobState


def ask_human(state: JobState) -> dict:
    pending = state.get("pending_human") or ""
    if pending == "paywall":
        return {"reply_message": ASK_PAYWALL, "status": "needs_human"}
    if pending == "unsupported_social":
        return {"reply_message": ASK_UNSUPPORTED_SOCIAL, "status": "needs_human"}
    return {"reply_message": ASK_UNKNOWN, "status": "needs_human"}


_IN_PROGRESS = {
    "ack",
    "audio_ready",
    "subtitle_ready",
    "local_ready",
    "transcribed",
    "purified",
}


def status_node(state: JobState) -> dict:
    current = state.get("status") or ""
    if current in {"done", "failed", "needs_feishu", "needs_human"}:
        return {"reply_message": state.get("reply_message") or STATUS_IDLE}
    if current in _IN_PROGRESS:
        return {"reply_message": STATUS_RUNNING, "status": current}
    return {"reply_message": STATUS_IDLE, "status": "idle"}


def ack_route(state: JobState) -> dict:
    if state.get("route") == "xiaod":
        report_progress(stage="开始处理", reply=ACK_MEDIA, progress=5)
        return {"reply_message": ACK_MEDIA, "status": "ack"}
    return {}
