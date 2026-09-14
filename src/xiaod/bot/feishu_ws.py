"""Feishu WebSocket event bot. No public webhook required."""

from __future__ import annotations

from typing import Any, Callable
import json
import logging
import threading
import time

from xiaod.bot.jobs import TERMINAL, bot_thread_id, latest_job, remember_job, update_job
from xiaod.graph import run_text
from xiaod.messages import ACK_GENERIC, STATUS_IDLE, STATUS_RUNNING
from xiaod.nodes.classify import classify_text
from xiaod.progress import reset_progress_handler, set_progress_handler
from xiaod.settings import get_settings

logger = logging.getLogger("xiaod.bot")

SKIP_PROGRESS_STAGES = frozenset({"开始处理"})
PROGRESS_MIN_INTERVAL = 45


class ProgressReporter:
    """Send Feishu updates on stage changes; throttle whisper minute ticks."""

    def __init__(
        self,
        send: Callable[[str], None],
        *,
        open_id: str,
        thread_id: str,
        min_interval: float = PROGRESS_MIN_INTERVAL,
    ) -> None:
        self._send = send
        self._open_id = open_id
        self._thread_id = thread_id
        self._min_interval = min_interval
        self._last_stage = ""
        self._last_reply = ""
        self._last_sent_at = 0.0

    def __call__(self, fields: dict[str, str | int]) -> None:
        stage = str(fields.get("stage") or "")
        reply = str(fields.get("reply") or "")
        progress = fields.get("progress")
        patch: dict[str, str | int] = {}
        if stage:
            patch["stage"] = stage
        if reply:
            patch["reply"] = reply
        if progress is not None:
            patch["progress"] = int(progress)
        if patch:
            update_job(self._open_id, self._thread_id, status="running", **patch)
        if not reply or reply == self._last_reply:
            return
        if stage in SKIP_PROGRESS_STAGES:
            return
        now = time.monotonic()
        stage_changed = bool(stage) and stage != self._last_stage
        if not stage_changed and now - self._last_sent_at < self._min_interval:
            return
        self._last_stage = stage or self._last_stage
        self._last_reply = reply
        self._last_sent_at = now
        try:
            self._send(reply)
        except Exception:
            logger.exception("progress reply failed")


def _text_from_event(event: Any) -> tuple[str, str, str, str]:
    message = event.event.message
    sender = event.event.sender
    chat_id = message.chat_id
    message_id = message.message_id
    open_id = ""
    if sender and sender.sender_id:
        open_id = sender.sender_id.open_id or sender.sender_id.user_id or ""
    content = json.loads(message.content or "{}")
    text = content.get("text") or ""
    if not text and content.get("content"):
        text = str(content.get("content"))
    if message.message_type == "post":
        text = _flatten_post(content) or text
    return text.strip(), open_id, chat_id, message_id


def _flatten_post(content: dict[str, Any]) -> str:
    parts: list[str] = []
    title = content.get("title")
    if title:
        parts.append(str(title))
    for paragraph in content.get("content") or []:
        if not isinstance(paragraph, list):
            continue
        for item in paragraph:
            if not isinstance(item, dict):
                continue
            if item.get("tag") == "text":
                parts.append(str(item.get("text") or ""))
            if item.get("tag") == "a":
                parts.append(str(item.get("href") or item.get("text") or ""))
    return " ".join(part for part in parts if part)


def status_for_user(open_id: str) -> str:
    job = latest_job(open_id)
    if not job:
        return STATUS_IDLE
    reply = str(job.get("reply") or "").strip()
    status = str(job.get("status") or "")
    if status in TERMINAL:
        return reply or STATUS_IDLE
    return reply or STATUS_RUNNING


def handle_text(
    text: str,
    *,
    open_id: str = "",
    chat_id: str = "",
    message_id: str = "",
    runner: Callable[..., Any] | None = None,
    on_progress: Callable[[dict[str, str | int]], None] | None = None,
) -> str:
    invoke = runner or run_text
    if classify_text(text).route == "status":
        return status_for_user(open_id)

    thread_id = bot_thread_id(open_id, message_id)
    remember_job(open_id, thread_id, status="running", reply=ACK_GENERIC)
    token = set_progress_handler(on_progress) if on_progress else None
    try:
        result = invoke(text, open_id=open_id, chat_id=chat_id, thread_id=thread_id)
    except Exception:
        if token is not None:
            reset_progress_handler(token)
        update_job(open_id, thread_id, status="failed", reply="这次没有处理成功。请换一条公开链接再试。")
        raise
    if token is not None:
        reset_progress_handler(token)
    payload = dict(result or {})
    reply = str(payload.get("reply_message") or "").strip() or ACK_GENERIC
    update_job(
        open_id,
        thread_id,
        status=str(payload.get("status") or "done"),
        reply=reply,
        stage=str(payload.get("status") or ""),
    )
    return reply


def _reply(client: Any, message_id: str, text: str) -> None:
    from lark_oapi.api.im.v1 import ReplyMessageRequest, ReplyMessageRequestBody

    req = (
        ReplyMessageRequest.builder()
        .message_id(message_id)
        .request_body(
            ReplyMessageRequestBody.builder()
            .content(json.dumps({"text": text}, ensure_ascii=False))
            .msg_type("text")
            .build()
        )
        .build()
    )
    resp = client.im.v1.message.reply(req)
    if not resp.success():
        logger.warning("reply failed: %s", getattr(resp, "msg", ""))


def start_bot() -> None:
    settings = get_settings()
    if not settings.has_feishu:
        raise SystemExit("请先在 .env 里填写 FEISHU_APP_ID 和 FEISHU_APP_SECRET")

    import lark_oapi as lark
    from lark_oapi.api.im.v1 import P2ImMessageReceiveV1

    rest = (
        lark.Client.builder()
        .app_id(settings.feishu_app_id)
        .app_secret(settings.feishu_app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )

    def on_message(data: P2ImMessageReceiveV1) -> None:
        try:
            text, open_id, chat_id, message_id = _text_from_event(data)
        except Exception:
            logger.exception("parse event failed")
            return
        if not text:
            return
        if classify_text(text).route == "status":
            _reply(rest, message_id, status_for_user(open_id))
            return
        _reply(rest, message_id, ACK_GENERIC)

        def worker() -> None:
            def send(body: str) -> None:
                _reply(rest, message_id, body)

            reporter = ProgressReporter(send, open_id=open_id, thread_id=bot_thread_id(open_id, message_id))
            try:
                reply = handle_text(
                    text,
                    open_id=open_id,
                    chat_id=chat_id,
                    message_id=message_id,
                    on_progress=reporter,
                )
            except Exception:
                logger.exception("job failed")
                reply = "这次没有处理成功。请换一条公开链接再试。"
            send(reply)

        threading.Thread(target=worker, name=f"xiaod-{open_id}-{message_id}", daemon=True).start()

    handler = (
        lark.EventDispatcherHandler.builder("", "")
        .register_p2_im_message_receive_v1(on_message)
        .build()
    )
    ws = lark.ws.Client(
        settings.feishu_app_id,
        settings.feishu_app_secret,
        event_handler=handler,
        log_level=lark.LogLevel.INFO,
    )
    logger.info("xiaod feishu websocket bot starting")
    ws.start()
