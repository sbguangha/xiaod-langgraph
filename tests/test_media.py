import subprocess
import sys
from pathlib import Path

import pytest

from xiaod.tools import media


def test_ytdlp_cmd_passes_ffmpeg_location(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("FFMPEG_BIN", str(fake))
    cmd = media.ytdlp_cmd()
    assert "--ffmpeg-location" in cmd
    assert str(fake) in cmd


def test_download_audio_keeps_m4a_when_mp3_conversion_fails(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "audio"
    dest.mkdir()
    leftover = dest / "BV1t5Yj6CEJe.m4a"
    leftover.write_bytes(b"audio")

    monkeypatch.setattr(
        media,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(
            args, 1, "", "ERROR: ffprobe and ffmpeg not found. Please install or provide the path using --ffmpeg-location"
        ),
    )
    monkeypatch.setattr(
        media,
        "probe_media",
        lambda url: {"title": "demo", "duration": 12, "extractor": "BiliBili"},
    )

    path, info = media.download_audio("https://www.bilibili.com/video/BV1t5Yj6CEJe", dest)
    assert path == leftover
    assert info["title"] == "demo"


def test_download_audio_without_file_is_download_failed(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "audio"
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"")
    monkeypatch.setenv("FFMPEG_BIN", str(fake))
    monkeypatch.setattr(
        media,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1, "", "HTTP Error 404"),
    )
    with pytest.raises(media.MediaError) as exc:
        media.download_audio("https://www.bilibili.com/video/BV404", dest)
    assert exc.value.code == "platform_blocked"
    assert "换一条公开链接" not in exc.value.detail


def test_download_audio_without_ffmpeg_or_file_is_ffmpeg_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    dest = tmp_path / "audio"
    monkeypatch.setenv("FFMPEG_BIN", str(tmp_path / "missing-ffmpeg"))
    monkeypatch.setattr(media, "ffmpeg_path", lambda settings=None: None)
    monkeypatch.setattr(
        media,
        "_run",
        lambda args, **kwargs: subprocess.CompletedProcess(args, 1, "", "ERROR: ffmpeg not found"),
    )
    with pytest.raises(media.MediaError) as exc:
        media.download_audio("https://www.bilibili.com/video/BV404", dest)
    assert exc.value.code == "ffmpeg_missing"


def test_check_tool_stack_reports_each_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(media, "ytdlp_available", lambda: True)
    monkeypatch.setattr(media, "whisper_available", lambda: False)
    monkeypatch.setattr(media, "ffmpeg_path", lambda settings=None: None)
    stack = media.check_tool_stack()
    assert stack["yt_dlp"] is True
    assert stack["ffmpeg"] is False
    assert stack["faster_whisper"] is False
    assert stack["ok"] is False


def test_check_tool_stack_ok_when_all_present(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = tmp_path / "ffmpeg.exe"
    fake.write_bytes(b"")
    monkeypatch.setattr(media, "ytdlp_available", lambda: True)
    monkeypatch.setattr(media, "whisper_available", lambda: True)
    monkeypatch.setattr(media, "ffmpeg_path", lambda settings=None: fake)
    stack = media.check_tool_stack()
    assert stack["ok"] is True
    assert stack["ffmpeg_bin"] == str(fake)


def test_classify_ytdlp_error_splits_reasons() -> None:
    assert media.classify_ytdlp_error("Sign in to confirm your age") == "login_required"
    assert media.classify_ytdlp_error("ERROR: 需要登录后观看") == "login_required"
    assert media.classify_ytdlp_error("The uploader has not made this video available in your country") == "region_blocked"
    assert media.classify_ytdlp_error("HTTP Error 404: Not Found") == "platform_blocked"
    assert media.classify_ytdlp_error("Requested format is video only; no audio") == "no_audio"
    assert media.classify_ytdlp_error("") == "no_audio"


def test_transcribe_audio_reads_whisper_segments(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    clip = tmp_path / "talk.mp3"
    clip.write_bytes(b"audio")

    class FakeModel:
        def __init__(self, *args, **kwargs) -> None:
            self.kwargs = kwargs

        def transcribe(self, path: str, vad_filter: bool = True):
            assert path == str(clip)
            assert vad_filter is True
            segment = type("Segment", (), {"text": "  亦仁说生财有术。  "})()
            return [segment], None

    fake_mod = type(sys)("faster_whisper")
    fake_mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)

    text = media.transcribe_audio(clip)
    assert "亦仁" in text


def test_transcribe_audio_reports_segment_progress(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    from xiaod.progress import reset_progress_handler, set_progress_handler

    clip = tmp_path / "talk.mp3"
    clip.write_bytes(b"audio")
    seen: list[dict] = []
    token = set_progress_handler(seen.append)

    class FakeModel:
        def __init__(self, *args, **kwargs) -> None:
            return None

        def transcribe(self, path: str, vad_filter: bool = True):
            segments = [
                type("Segment", (), {"text": "第一段。", "end": 180})(),
                type("Segment", (), {"text": "第二段。", "end": 420})(),
            ]
            info = type("Info", (), {"duration": 600})()
            return segments, info

    fake_mod = type(sys)("faster_whisper")
    fake_mod.WhisperModel = FakeModel
    monkeypatch.setitem(sys.modules, "faster_whisper", fake_mod)
    try:
        text = media.transcribe_audio(clip)
    finally:
        reset_progress_handler(token)

    assert "第一段" in text
    replies = [str(item.get("reply") or "") for item in seen]
    assert any("已完成 3/10 分钟" in reply for reply in replies)
    percents = [int(item["progress"]) for item in seen if "progress" in item]
    assert percents[0] >= 28
    assert percents[-1] == 86
    assert any(30 < value < 86 for value in percents)
