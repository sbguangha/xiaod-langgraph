"""Shared LangGraph job state."""

from __future__ import annotations

from typing import Annotated, NotRequired, TypedDict
import operator
import uuid


MEDIA_SOURCES = frozenset({"xiaoyuzhou", "bilibili", "youtube", "local"})
SOCIAL_SOURCES = frozenset({"xhs", "douyin", "wechat_mp", "channels"})


class JobState(TypedDict):
    input_text: str
    open_id: str
    chat_id: str
    thread_id: str
    source_type: str
    route: str
    urls: list[str]
    title: str
    source_platform: str
    media_path: str
    subtitle: str
    transcript: str
    article: str
    feishu_url: str
    feishu_doc_token: str
    permission_granted: bool
    used_subtitle: bool
    duration_sec: int
    eta_minutes: int
    user_intent: str
    errors: Annotated[list[str], operator.add]
    pending_human: str
    reply_message: str
    qa_ok: bool
    qa_retries: int
    status: str
    skip_slow: NotRequired[bool]


def new_thread_id(open_id: str = "") -> str:
    suffix = uuid.uuid4().hex[:10]
    prefix = open_id or "cli"
    return f"{prefix}:{suffix}"


def empty_state(
    input_text: str,
    *,
    open_id: str = "",
    chat_id: str = "",
    thread_id: str = "",
) -> JobState:
    return {
        "input_text": input_text,
        "open_id": open_id,
        "chat_id": chat_id,
        "thread_id": thread_id or new_thread_id(open_id),
        "source_type": "",
        "route": "",
        "urls": [],
        "title": "",
        "source_platform": "",
        "media_path": "",
        "subtitle": "",
        "transcript": "",
        "article": "",
        "feishu_url": "",
        "feishu_doc_token": "",
        "permission_granted": False,
        "used_subtitle": False,
        "duration_sec": 0,
        "eta_minutes": 0,
        "user_intent": "",
        "errors": [],
        "pending_human": "",
        "reply_message": "",
        "qa_ok": False,
        "qa_retries": 0,
        "status": "received",
        "skip_slow": False,
    }
