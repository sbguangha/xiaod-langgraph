"""Deterministic source and intent classification."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

from xiaod.state import MEDIA_SOURCES, SOCIAL_SOURCES, JobState

_URL_RE = re.compile(r"https?://[^\s<>\"']+", re.I)
_LOCAL_RE = re.compile(
    r'(?:[a-zA-Z]:\\|/)[^\s"\']+\.(?:mp3|m4a|wav|mp4|aac|flac)',
    re.I,
)

_STATUS_WORDS = ("进度", "状态", "怎么样了", "好了吗", "还在吗")
_TRANSCRIPT_WORDS = ("转录", "转写", "整理稿", "提纯", "文稿")
_ARCHIVE_WORDS = ("归档", "收藏", "只要链接", "先存")
_RESEARCH_WORDS = ("调研", "选题", "对标", "评论", "挖需求", "搜索")
_PAYWALL_WORDS = ("付费", "会员", "登录后", "需要登录", "vip")

_TRASH_TITLES = ("其他有效观点", "补充说明", "其他", "总结一下")


@dataclass(frozen=True)
class Classification:
    source_type: str
    route: str
    urls: list[str]
    user_intent: str
    research_kind: str
    pending_human: str
    source_platform: str


def extract_urls(text: str) -> list[str]:
    found = [m.group(0).rstrip(").,，。]") for m in _URL_RE.finditer(text or "")]
    locals_ = [m.group(0) for m in _LOCAL_RE.finditer(text or "")]
    return list(dict.fromkeys(found + locals_))


def detect_source(url: str) -> str:
    raw = (url or "").strip()
    lower = raw.lower()
    if _LOCAL_RE.search(raw) or Path(raw).suffix.lower() in {".mp3", ".m4a", ".wav", ".mp4", ".aac", ".flac"}:
        return "local"
    if "xiaoyuzhoufm.com" in lower:
        return "xiaoyuzhou"
    if "youtube.com" in lower or "youtu.be" in lower:
        return "youtube"
    if "bilibili.com" in lower or "b23.tv" in lower:
        return "bilibili"
    if "xiaohongshu.com" in lower or "xhslink.com" in lower:
        return "xhs"
    if "douyin.com" in lower or "iesdouyin.com" in lower:
        return "douyin"
    if "mp.weixin.qq.com" in lower:
        return "wechat_mp"
    if "weixin.qq.com/sph" in lower or "channels.weixin.qq.com" in lower:
        return "channels"
    if "minutes" in lower and ("feishu.cn" in lower or "larksuite.com" in lower):
        return "minutes"
    if "feishu.cn" in lower and ("/docx/" in lower or "/wiki/" in lower):
        return "minutes"
    return "unknown"


def detect_intent(text: str) -> str:
    blob = text or ""
    if any(word in blob for word in _STATUS_WORDS) and not extract_urls(blob):
        return "status"
    if any(word in blob for word in _RESEARCH_WORDS):
        return "research"
    if any(word in blob for word in _ARCHIVE_WORDS):
        return "archive"
    if any(word in blob for word in _TRANSCRIPT_WORDS):
        return "transcript"
    return "auto"


def detect_research_kind(text: str) -> str:
    blob = text or ""
    if any(word in blob for word in ("对标", "账号", "主页")):
        return "competitor"
    if any(word in blob for word in ("评论", "挖需求")):
        return "comments"
    if any(word in blob for word in ("选题", "搜索", "调研")):
        return "topic"
    return "collect"


def _platform_name(source_type: str) -> str:
    return {
        "xiaoyuzhou": "小宇宙",
        "bilibili": "B站",
        "youtube": "YouTube",
        "local": "本地",
        "minutes": "飞书妙记",
        "xhs": "小红书",
        "douyin": "抖音",
        "wechat_mp": "微信公众号",
        "channels": "微信视频号",
    }.get(source_type, "未知")


def classify_text(text: str) -> Classification:
    urls = extract_urls(text)
    intent = detect_intent(text)
    research_kind = detect_research_kind(text)
    if any(word in (text or "") for word in _PAYWALL_WORDS):
        source = detect_source(urls[0]) if urls else "paywalled"
        return Classification(source, "human", urls, intent, research_kind, "paywall", _platform_name(source))
    if intent == "status":
        return Classification("", "status", urls, "status", "", "", "")
    if not urls:
        return Classification("unknown", "human", [], intent, research_kind, "unknown", "未知")
    source = detect_source(urls[0])
    platform = _platform_name(source)
    if source in MEDIA_SOURCES:
        return Classification(source, "xiaod", urls, "transcript" if intent == "auto" else intent, "", "", platform)
    if source in SOCIAL_SOURCES:
        return Classification(source, "human", urls, intent, "", "unsupported_social", platform)
    return Classification("unknown", "human", urls, intent, research_kind, "unknown", "未知")


def classify_node(state: JobState) -> dict:
    result = classify_text(state.get("input_text") or "")
    update = {
        "source_type": result.source_type,
        "route": result.route,
        "urls": result.urls,
        "user_intent": result.user_intent,
        "research_kind": result.research_kind,
        "pending_human": result.pending_human,
        "source_platform": result.source_platform,
    }
    if result.route != "status":
        update["status"] = "classified"
    return update


def is_trash_title(title: str) -> bool:
    return any(item == (title or "").strip() for item in _TRASH_TITLES)
