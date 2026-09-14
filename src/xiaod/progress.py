"""In-process progress for a running job. Web console polls this via JobStore."""

from __future__ import annotations

from contextvars import ContextVar, Token
from typing import Callable

ProgressHandler = Callable[[dict[str, str | int]], None]

_handler: ContextVar[ProgressHandler | None] = ContextVar("xiaod_progress", default=None)


def set_progress_handler(handler: ProgressHandler | None) -> Token[ProgressHandler | None]:
    return _handler.set(handler)


def reset_progress_handler(token: Token[ProgressHandler | None]) -> None:
    _handler.reset(token)


def report_progress(*, stage: str = "", reply: str = "", progress: int | None = None) -> None:
    handler = _handler.get()
    if handler is None:
        return
    payload: dict[str, str | int] = {}
    if stage:
        payload["stage"] = stage
    if reply:
        payload["reply"] = reply
    if progress is not None:
        payload["progress"] = max(0, min(100, int(progress)))
    if payload:
        handler(payload)
