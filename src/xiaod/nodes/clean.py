"""Transcript cleaning, typo fixes, and share-draft QA."""

from __future__ import annotations

from pathlib import Path
import re

from xiaod.nodes.classify import is_trash_title

_TIMESTAMP_RE = re.compile(
    r"(?:\[)?(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?(?:\])?(?:\s*-->\s*(?:\[)?(?:\d{1,2}:)?\d{1,2}:\d{2}(?:\.\d+)?(?:\])?)?"
)
_SPEAKER_RE = re.compile(r"^(?:说话人\s*\d+|speaker\s*\d+|主持人|嘉宾)[:：]\s*", re.I)
_FILLER_RE = re.compile(r"(那个|就是说|然后那个|嗯+|啊+|呃+)\s*")
_VTT_TAG_RE = re.compile(r"<[^>]+>")

TYPO_MAP = {
    "飞输": "飞书",
    "飞书书": "飞书",
}

TRASH_HEADINGS = ("其他有效观点", "补充说明", "其他", "总结一下")


def load_purify_prompt() -> str:
    path = Path(__file__).resolve().parents[1] / "prompts" / "purify.md"
    return path.read_text(encoding="utf-8")


def apply_typos(text: str) -> str:
    out = text
    for wrong, right in TYPO_MAP.items():
        out = out.replace(wrong, right)
    return out


def strip_timestamps(text: str) -> str:
    cleaned = _TIMESTAMP_RE.sub("", text)
    cleaned = _VTT_TAG_RE.sub("", cleaned)
    return cleaned


def clean_transcript(text: str) -> str:
    lines: list[str] = []
    for raw in (text or "").splitlines():
        line = strip_timestamps(raw).strip()
        if not line or line.upper() in {"WEBVTT", "NOTE"}:
            continue
        line = _SPEAKER_RE.sub("", line)
        line = _FILLER_RE.sub("", line)
        line = apply_typos(line)
        if line:
            lines.append(line)
    return "\n".join(lines).strip()


def looks_like_summary(text: str) -> bool:
    lines = [line.strip() for line in (text or "").splitlines() if line.strip()]
    if not lines:
        return True
    bullets = [line for line in lines if re.match(r"^[-*•]|\d+[\.、]", line)]
    if len(bullets) >= 8 and len(text) < 800:
        return True
    if "一句话总结" in text or "核心要点" in text or "三点启发" in text:
        return True
    return False


def has_trash_heading(text: str) -> bool:
    for line in (text or "").splitlines():
        heading = line.lstrip("#").strip()
        if is_trash_title(heading) or heading in TRASH_HEADINGS:
            return True
    return False


def qa_share_draft(text: str) -> tuple[bool, list[str]]:
    reasons: list[str] = []
    if not (text or "").strip():
        reasons.append("empty")
    if _TIMESTAMP_RE.search(text or ""):
        reasons.append("timestamp")
    if looks_like_summary(text):
        reasons.append("summary")
    if has_trash_heading(text):
        reasons.append("trash_title")
    if len((text or "").strip()) < 80:
        reasons.append("too_short")
    return (not reasons, reasons)


def rule_based_purify(transcript: str, *, platform: str, title: str) -> str:
    cleaned = clean_transcript(transcript)
    if not cleaned:
        return ""
    heading = title.strip() or "整理稿"
    if is_trash_title(heading):
        heading = "正文"
    paragraphs = [chunk.strip() for chunk in re.split(r"\n{2,}", cleaned) if chunk.strip()]
    if not paragraphs:
        paragraphs = [cleaned]
    body = ["## " + heading]
    for para in paragraphs:
        body.append(para)
        body.append("")
    body.append("")
    body.append(f"（来源：{platform or '未知'}。不确定的专有名词已尽量按错词表修正。）")
    return "\n".join(body).strip()
