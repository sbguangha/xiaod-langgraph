"""yt-dlp, ffmpeg, and local faster-whisper. Priority is hardcoded: subtitle first."""

from __future__ import annotations

from pathlib import Path
import json
import logging
import os
import shutil
import subprocess
import sys

from xiaod.progress import report_progress
from xiaod.settings import Settings, get_settings
from xiaod.tracing import traceable

logger = logging.getLogger("xiaod.media")

AUDIO_SUFFIXES = (".mp3", ".m4a", ".webm", ".opus", ".aac", ".wav", ".ogg", ".flac")


class MediaError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ffmpeg_path(settings: Settings | None = None) -> Path | None:
    settings = settings or get_settings()
    raw = (settings.ffmpeg_bin or "ffmpeg").strip()
    candidate = Path(raw)
    if candidate.is_file():
        return candidate
    found = shutil.which(raw)
    return Path(found) if found else None


def ensure_ffmpeg_on_path(settings: Settings | None = None) -> Path | None:
    path = ffmpeg_path(settings)
    if path is None:
        return None
    directory = str(path.parent)
    current = os.environ.get("PATH", "")
    parts = current.split(os.pathsep)
    if directory not in parts:
        os.environ["PATH"] = directory + os.pathsep + current
    return path


def ffmpeg_available(settings: Settings | None = None) -> bool:
    return ffmpeg_path(settings) is not None


def ytdlp_available() -> bool:
    try:
        import yt_dlp  # noqa: F401
    except ImportError:
        return shutil.which("yt-dlp") is not None
    return True


def whisper_available() -> bool:
    try:
        import faster_whisper  # noqa: F401
    except ImportError:
        return False
    return True


def check_tool_stack(settings: Settings | None = None) -> dict[str, bool | str]:
    ffmpeg = ffmpeg_path(settings)
    stack = {
        "yt_dlp": ytdlp_available(),
        "ffmpeg": ffmpeg is not None,
        "faster_whisper": whisper_available(),
        "ffmpeg_bin": str(ffmpeg) if ffmpeg else "",
    }
    stack["ok"] = bool(stack["yt_dlp"] and stack["ffmpeg"] and stack["faster_whisper"])
    return stack


def ytdlp_cmd(settings: Settings | None = None) -> list[str]:
    found = shutil.which("yt-dlp")
    cmd = [found] if found else [sys.executable, "-m", "yt_dlp"]
    ffmpeg = ensure_ffmpeg_on_path(settings)
    if ffmpeg:
        cmd.extend(["--ffmpeg-location", str(ffmpeg)])
    return cmd


def find_audio_files(dest_dir: Path) -> list[Path]:
    if not dest_dir.is_dir():
        return []
    files = [path for path in dest_dir.iterdir() if path.is_file() and path.suffix.lower() in AUDIO_SUFFIXES]
    return sorted(files, key=lambda path: (path.suffix.lower() != ".mp3", path.name))


@traceable(run_type="tool", name="yt_dlp_probe")
def probe_media(url: str) -> dict:
    cmd = ytdlp_cmd() + ["--dump-json", "--no-playlist", "--skip-download", url]
    result = _run(cmd)
    if result.returncode != 0:
        raise MediaError("download_failed", result.stderr[-400:])
    info = json.loads(result.stdout.splitlines()[-1])
    return {
        "title": info.get("title") or info.get("fulltitle") or "",
        "duration": int(info.get("duration") or 0),
        "extractor": info.get("extractor") or "",
    }


@traceable(run_type="tool", name="yt_dlp_subtitles")
def fetch_subtitles(url: str, dest_dir: Path) -> tuple[str, str]:
    report_progress(stage="正在找字幕", reply="先找平台字幕，没有字幕再下载音频转写。", progress=8)
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(id)s")
    cmd = ytdlp_cmd() + [
        "--skip-download",
        "--write-subs",
        "--write-auto-subs",
        "--sub-langs",
        "zh.*,zh,en.*",
        "--convert-subs",
        "vtt",
        "-o",
        outtmpl,
        url,
    ]
    result = _run(cmd)
    if result.returncode != 0:
        return "", ""
    vtts = sorted(dest_dir.glob("*.vtt"))
    if not vtts:
        return "", ""
    text = vtts[0].read_text(encoding="utf-8", errors="replace")
    title = ""
    try:
        info = probe_media(url)
        title = str(info.get("title") or "")
    except MediaError:
        title = vtts[0].stem
    return text, title


@traceable(run_type="tool", name="yt_dlp_audio")
def download_audio(url: str, dest_dir: Path, settings: Settings | None = None) -> tuple[Path, dict]:
    settings = settings or get_settings()
    report_progress(stage="正在下载音频", reply="没有现成字幕，正在下载音频并转成可转写的格式。", progress=15)
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    cmd = ytdlp_cmd(settings) + [
        "-x",
        "--audio-format",
        "mp3",
        "--no-playlist",
        "-o",
        outtmpl,
        url,
    ]
    result = _run(cmd)
    audio = find_audio_files(dest_dir)
    if result.returncode != 0:
        logger.warning("yt-dlp audio extract failed: %s", (result.stderr or "")[-800:])
    if not audio:
        if not ffmpeg_available(settings):
            raise MediaError("ffmpeg_missing")
        raise MediaError("download_failed", (result.stderr or "no audio file")[-400:])
    try:
        info = probe_media(url)
    except MediaError:
        info = {"title": audio[0].stem, "duration": 0, "extractor": ""}
    return audio[0], info


def estimate_eta_minutes(duration_sec: int) -> int:
    if duration_sec <= 0:
        return 5
    return max(3, int(duration_sec / 60 * 0.4) + 2)


def split_audio(path: Path, dest_dir: Path, *, segment_sec: int = 30 * 60, settings: Settings | None = None) -> list[Path]:
    settings = settings or get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / "seg_%03d.mp3"
    ffmpeg = ffmpeg_path(settings)
    cmd = [
        str(ffmpeg) if ffmpeg else settings.ffmpeg_bin,
        "-y",
        "-i",
        str(path),
        "-f",
        "segment",
        "-segment_time",
        str(segment_sec),
        "-c",
        "copy",
        str(pattern),
    ]
    result = _run(cmd)
    if result.returncode != 0:
        return [path]
    parts = sorted(dest_dir.glob("seg_*.mp3"))
    return parts or [path]


@traceable(run_type="tool", name="faster_whisper")
def transcribe_audio(path: Path, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    try:
        from faster_whisper import WhisperModel
    except ImportError as exc:
        raise MediaError("asr_missing") from exc
    report_progress(stage="正在转写", reply="正在加载语音识别模型。第一次会下载模型，请稍等。", progress=28)
    model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    segments, info = model.transcribe(str(path), vad_filter=True)
    duration = float(getattr(info, "duration", 0) or 0)
    total_min = max(1, int(duration // 60)) if duration else 0
    report_progress(
        stage="正在转写",
        reply="正在本机转写，CPU 上会比较慢，页面会显示已完成的分钟数。"
        if not total_min
        else f"正在本机转写，音频大约 {total_min} 分钟。CPU 上通常要再等一段时间。",
        progress=30,
    )
    lines: list[str] = []
    last_pct = 29
    for segment in segments:
        text = (getattr(segment, "text", "") or "").strip()
        if text:
            lines.append(text)
        end = float(getattr(segment, "end", 0) or 0)
        if duration > 0:
            pct = 30 + int(min(end, duration) / duration * 55)
        else:
            pct = min(80, last_pct + 1)
        if pct < last_pct + 2:
            continue
        last_pct = min(84, pct)
        done_min = int(end // 60)
        reply = (
            f"正在转写，大约已完成 {done_min}/{total_min} 分钟。"
            if total_min
            else "正在转写。"
        )
        report_progress(stage="正在转写", reply=reply, progress=last_pct)
        logger.info("transcribe %s", reply)
    if not lines:
        raise MediaError("asr_failed")
    report_progress(stage="已转写", reply="语音识别完成，接下来整理成提纯稿。", progress=86)
    return "\n".join(lines)
