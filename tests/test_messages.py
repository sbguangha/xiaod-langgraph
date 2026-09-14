from xiaod.bot.pending import get_pending, pop_pending, save_pending
from xiaod.messages import format_doc_reply, user_error
from xiaod.settings import get_settings


def test_user_error_has_no_http_or_traceback() -> None:
    text = user_error("download_failed")
    assert "404" not in text
    assert "Traceback" not in text
    assert "Exception" not in text


def test_doc_reply_mentions_manual_acl() -> None:
    text = format_doc_reply(url="https://feishu.cn/docx/abc", title="稿", used_subtitle=True, permission_granted=False)
    assert "权限" in text
    assert "https://feishu.cn/docx/abc" in text


def test_pending_roundtrip(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    from xiaod import settings

    monkeypatch.setattr(settings, "get_settings", get_settings)
    save_pending("ou_1", {"kind": "transcript_or_archive", "text": "https://v.douyin.com/a"})
    assert get_pending("ou_1")["kind"] == "transcript_or_archive"
    assert pop_pending("ou_1")["text"].startswith("https://")
    assert get_pending("ou_1") is None
