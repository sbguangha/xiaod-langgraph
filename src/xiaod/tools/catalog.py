"""LangChain tools wrapping yt-dlp, whisper, and Feishu implementations."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from langchain_core.tools import StructuredTool


def _fetch_subtitles(url: str, dest_dir: str) -> dict[str, str]:
    from xiaod.tools import media

    text, title = media.fetch_subtitles(url, Path(dest_dir))
    return {"text": text, "title": title}


def _probe_media(url: str) -> dict[str, Any]:
    from xiaod.tools import media

    return media.probe_media(url)


def _download_audio(url: str, dest_dir: str) -> dict[str, Any]:
    from xiaod.tools import media

    path, info = media.download_audio(url, Path(dest_dir))
    return {
        "path": str(path),
        "title": str(info.get("title") or ""),
        "duration": int(info.get("duration") or 0),
        "extractor": str(info.get("extractor") or ""),
    }


def _transcribe_audio(path: str) -> str:
    from xiaod.tools import media

    return media.transcribe_audio(Path(path))


def _split_audio(path: str, dest_dir: str) -> list[str]:
    from xiaod.tools import media

    return [str(part) for part in media.split_audio(Path(path), Path(dest_dir))]


def _create_feishu_doc(title: str, markdown: str) -> dict[str, str]:
    from xiaod.tools import lark

    return lark.create_markdown_doc(title, markdown)


def _grant_feishu_acl(document_id: str, open_id: str) -> bool:
    from xiaod.tools import lark

    return lark.grant_doc_permission(document_id, open_id)


fetch_subtitles_tool = StructuredTool.from_function(
    name="fetch_subtitles",
    description="从公开视频或播客链接读取平台字幕。没有字幕时返回空文本。",
    func=_fetch_subtitles,
)
probe_media_tool = StructuredTool.from_function(
    name="probe_media",
    description="读取公开链接的标题和时长，不下载文件。",
    func=_probe_media,
)
download_audio_tool = StructuredTool.from_function(
    name="download_audio",
    description="用 yt-dlp 从公开播客或视频链接下载音频。",
    func=_download_audio,
)
transcribe_audio_tool = StructuredTool.from_function(
    name="transcribe_audio",
    description="用本机 faster-whisper 把音频转成文字。",
    func=_transcribe_audio,
)
split_audio_tool = StructuredTool.from_function(
    name="split_audio",
    description="把超过两小时的音频切成较短片段，方便分段转写。",
    func=_split_audio,
)
create_feishu_doc_tool = StructuredTool.from_function(
    name="create_feishu_doc",
    description="把整理稿写成飞书文档，返回文档编号和链接。",
    func=_create_feishu_doc,
)
grant_feishu_acl_tool = StructuredTool.from_function(
    name="grant_feishu_acl",
    description="把飞书文档的阅读权限授给发信人。",
    func=_grant_feishu_acl,
)

ALL_TOOLS = [
    fetch_subtitles_tool,
    probe_media_tool,
    download_audio_tool,
    transcribe_audio_tool,
    split_audio_tool,
    create_feishu_doc_tool,
    grant_feishu_acl_tool,
]
