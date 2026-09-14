"""yt-dlp, ffmpeg, and local faster-whisper. Priority is hardcoded: subtitle first."""

from __future__ import annotations

from pathlib import Path
import json
import shutil
import subprocess
import sys

from xiaod.settings import Settings, get_settings
from xiaod.tracing import traceable


class MediaError(Exception):
    def __init__(self, code: str, detail: str = "") -> None:
        self.code = code
        self.detail = detail
        super().__init__(code)


def _run(args: list[str], *, cwd: Path | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(args, cwd=cwd, check=False, capture_output=True, text=True, encoding="utf-8", errors="replace")


def ffmpeg_available(settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    return shutil.which(settings.ffmpeg_bin) is not None


def ytdlp_cmd() -> list[str]:
    found = shutil.which("yt-dlp")
    if found:
        return [found]
    return [sys.executable, "-m", "yt_dlp"]


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
    if not ffmpeg_available(settings):
        raise MediaError("ffmpeg_missing")
    dest_dir.mkdir(parents=True, exist_ok=True)
    outtmpl = str(dest_dir / "%(id)s.%(ext)s")
    cmd = ytdlp_cmd() + [
        "-x",
        "--audio-format",
        "mp3",
        "--no-playlist",
        "-o",
        outtmpl,
        url,
    ]
    result = _run(cmd)
    if result.returncode != 0:
        raise MediaError("download_failed", result.stderr[-400:])
    mp3s = sorted(dest_dir.glob("*.mp3"))
    if not mp3s:
        raise MediaError("download_failed", "no audio file")
    info = probe_media(url)
    return mp3s[0], info


def estimate_eta_minutes(duration_sec: int) -> int:
    if duration_sec <= 0:
        return 5
    return max(3, int(duration_sec / 60 * 0.4) + 2)


def split_audio(path: Path, dest_dir: Path, *, segment_sec: int = 30 * 60, settings: Settings | None = None) -> list[Path]:
    settings = settings or get_settings()
    dest_dir.mkdir(parents=True, exist_ok=True)
    pattern = dest_dir / "seg_%03d.mp3"
    cmd = [
        settings.ffmpeg_bin,
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
    model = WhisperModel(settings.whisper_model, device="cpu", compute_type="int8")
    segments, _info = model.transcribe(str(path), vad_filter=True)
    lines = [segment.text.strip() for segment in segments if segment.text.strip()]
    if not lines:
        raise MediaError("asr_failed")
    return "\n".join(lines)
