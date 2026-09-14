from xiaod.messages import user_error
from xiaod.nodes.xiaod_nodes import fetch_source, transcribe
from xiaod.state import empty_state
from xiaod.tools import media


def test_fetch_source_local_file(tmp_path) -> None:
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"audio")
    state = empty_state(str(audio))
    state["source_type"] = "local"
    state["urls"] = [str(audio)]
    out = fetch_source(state)
    assert out["status"] == "local_ready"
    assert out["media_path"] == str(audio)
    assert out["used_subtitle"] is False


def test_fetch_source_uses_login_error_copy(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(media, "fetch_subtitles", lambda url, dest: ("", ""))
    monkeypatch.setattr(
        media,
        "download_audio",
        lambda url, dest: (_ for _ in ()).throw(media.MediaError("login_required", "need login")),
    )
    state = empty_state("请转录 https://www.youtube.com/watch?v=abc")
    state["source_type"] = "youtube"
    state["urls"] = ["https://www.youtube.com/watch?v=abc"]
    state["thread_id"] = "cli-login"
    out = fetch_source(state)
    assert out["status"] == "failed"
    assert out["errors"] == ["login_required"]
    assert out["reply_message"] == user_error("login_required")


def test_transcribe_uses_local_whisper(monkeypatch, tmp_path) -> None:
    audio = tmp_path / "talk.mp3"
    audio.write_bytes(b"audio")
    monkeypatch.setattr(media, "transcribe_audio", lambda path: "亦仁说生财有术要做分享式提纯稿。")
    state = empty_state("本地")
    state["media_path"] = str(audio)
    state["used_subtitle"] = False
    state["duration_sec"] = 12
    out = transcribe(state)
    assert out["status"] == "transcribed"
    assert "亦仁" in out["transcript"]
