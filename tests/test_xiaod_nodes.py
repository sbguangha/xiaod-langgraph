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
