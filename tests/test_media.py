import subprocess
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
    assert exc.value.code == "download_failed"
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
