"""Xiao D subgraph nodes: subtitle first, then ASR, purify, deliver."""

from __future__ import annotations

from pathlib import Path
import logging

from xiaod.messages import NEED_ASR, NEED_FFMPEG, NEED_FEISHU, eta_notice, format_doc_reply, user_error
from xiaod.nodes.clean import clean_transcript, qa_share_draft, rule_based_purify
from xiaod.settings import get_settings
from xiaod.state import JobState
from xiaod.tools import lark, media
from xiaod.tools.llm import purify_share_draft
from xiaod.tracing import trace_metadata, traceable

logger = logging.getLogger("xiaod.nodes")


def job_dir_name(thread_id: str) -> str:
    raw = thread_id or "cli"
    return "".join(ch if ch.isalnum() or ch in "-_." else "-" for ch in raw)


def _work_dir(state: JobState) -> Path:
    settings = get_settings()
    path = settings.data_dir / "jobs" / job_dir_name(state.get("thread_id") or "cli")
    path.mkdir(parents=True, exist_ok=True)
    return path


@traceable(name="xiaod_fetch_source")
def fetch_source(state: JobState) -> dict:
    urls = state.get("urls") or []
    source_type = state.get("source_type") or ""
    if source_type == "local":
        media_path = urls[0] if urls else (state.get("input_text") or "").strip()
        return {
            "media_path": media_path,
            "title": Path(media_path).stem,
            "used_subtitle": False,
            "status": "local_ready",
        }
    if not urls:
        return {"errors": ["download_failed"], "status": "failed", "reply_message": user_error("download_failed")}
    url = urls[0]
    dest = _work_dir(state)
    subtitle, title = media.fetch_subtitles(url, dest / "subs")
    if subtitle.strip():
        duration = 0
        try:
            info = media.probe_media(url)
            duration = int(info.get("duration") or 0)
            title = title or str(info.get("title") or "")
        except media.MediaError:
            pass
        return {
            "subtitle": subtitle,
            "transcript": clean_transcript(subtitle),
            "title": title,
            "used_subtitle": True,
            "duration_sec": duration,
            "status": "subtitle_ready",
        }
    try:
        path, info = media.download_audio(url, dest / "audio")
    except media.MediaError as exc:
        logger.warning("fetch_source %s: %s", exc.code, exc.detail)
        if exc.code == "ffmpeg_missing":
            return {"errors": ["ffmpeg_missing"], "status": "failed", "reply_message": NEED_FFMPEG}
        return {"errors": ["download_failed"], "status": "failed", "reply_message": user_error("download_failed")}
    duration = int(info.get("duration") or 0)
    eta = media.estimate_eta_minutes(duration)
    return {
        "media_path": str(path),
        "title": str(info.get("title") or title or ""),
        "used_subtitle": False,
        "duration_sec": duration,
        "eta_minutes": eta,
        "reply_message": eta_notice(duration, eta) if duration >= 20 * 60 else "",
        "status": "audio_ready",
    }


@traceable(name="xiaod_transcribe")
def transcribe(state: JobState) -> dict:
    if state.get("used_subtitle") and state.get("transcript"):
        return {"status": "transcribed"}
    path = state.get("media_path") or ""
    if not path:
        return {"errors": ["asr_failed"], "status": "failed", "reply_message": user_error("asr_failed")}
    audio = Path(path)
    parts = [audio]
    if int(state.get("duration_sec") or 0) >= 2 * 60 * 60:
        parts = media.split_audio(audio, _work_dir(state) / "segments")
    texts: list[str] = []
    try:
        for part in parts:
            texts.append(media.transcribe_audio(part))
    except media.MediaError as exc:
        if exc.code == "asr_missing":
            return {"errors": ["asr_missing"], "status": "failed", "reply_message": NEED_ASR}
        return {"errors": ["asr_failed"], "status": "failed", "reply_message": user_error("asr_failed")}
    raw = "\n".join(texts)
    return {"transcript": clean_transcript(raw), "status": "transcribed"}


@traceable(name="xiaod_purify")
def purify(state: JobState) -> dict:
    transcript = state.get("transcript") or ""
    article = purify_share_draft(
        transcript,
        platform=state.get("source_platform") or "",
        title=state.get("title") or "",
    )
    ok, reasons = qa_share_draft(article)
    retries = int(state.get("qa_retries") or 0)
    if not ok and retries < 1:
        article = rule_based_purify(
            transcript,
            platform=state.get("source_platform") or "",
            title=state.get("title") or "",
        )
        ok, reasons = qa_share_draft(article)
        retries += 1
    return {
        "article": article,
        "qa_ok": ok,
        "qa_retries": retries,
        "status": "purified" if ok else "qa_failed",
        "errors": [] if ok else reasons,
    }


@traceable(name="xiaod_deliver")
def deliver_doc(state: JobState) -> dict:
    settings = get_settings()
    if not state.get("qa_ok"):
        return {"reply_message": user_error("qa_failed"), "status": "failed"}
    title = lark.document_title(state.get("source_platform") or "", state.get("title") or "")
    if not settings.has_feishu:
        return {
            "title": title,
            "reply_message": NEED_FEISHU,
            "status": "needs_feishu",
        }
    try:
        created = lark.create_markdown_doc(title, state.get("article") or "")
        granted = lark.grant_doc_permission(created["document_id"], state.get("open_id") or "")
    except lark.LarkError:
        return {"errors": ["feishu_failed"], "status": "failed", "reply_message": user_error("feishu_failed")}
    return {
        "title": title,
        "feishu_url": created["url"],
        "feishu_doc_token": created["document_id"],
        "permission_granted": granted,
        "reply_message": format_doc_reply(
            url=created["url"],
            title=title,
            used_subtitle=bool(state.get("used_subtitle")),
            permission_granted=granted,
        ),
        "status": "done",
        **{"_trace": trace_metadata(state)},
    }
