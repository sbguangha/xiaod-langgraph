"""Feishu WebSocket event bot. No public webhook required."""

from __future__ import annotations

from typing import Any
import json
import logging
import threading

from xiaod.graph import run_text
from xiaod.messages import ACK_GENERIC
from xiaod.settings import get_settings

logger = logging.getLogger("xiaod.bot")


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


def handle_text(text: str, *, open_id: str = "", chat_id: str = "") -> str:
    result = run_text(text, open_id=open_id, chat_id=chat_id, thread_id=open_id or "")
    reply = (result.get("reply_message") or "").strip()
    return reply or ACK_GENERIC


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
        _reply(rest, message_id, ACK_GENERIC)

        def worker() -> None:
            try:
                reply = handle_text(text, open_id=open_id, chat_id=chat_id)
            except Exception:
                logger.exception("job failed")
                reply = "这次没有处理成功。请换一条公开链接再试。"
            _reply(rest, message_id, reply)

        threading.Thread(target=worker, name=f"xiaod-{open_id}", daemon=True).start()

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
