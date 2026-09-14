from xiaod.messages import ASK_UNSUPPORTED_MINUTES, format_doc_reply, user_error


def test_user_error_has_no_http_or_traceback() -> None:
    for code in ("download_failed", "login_required", "region_blocked", "platform_blocked", "no_audio"):
        text = user_error(code)
        assert "404" not in text
        assert "Traceback" not in text
        assert "Exception" not in text
    assert "登录或会员" in user_error("login_required")
    assert "地区" in user_error("region_blocked")
    assert "不允许直接下载" in user_error("platform_blocked")
    assert "音频轨" in user_error("no_audio")
    assert "妙记" in ASK_UNSUPPORTED_MINUTES


def test_doc_reply_mentions_manual_acl() -> None:
    text = format_doc_reply(url="https://feishu.cn/docx/abc", title="稿", used_subtitle=True, permission_granted=False)
    assert "权限" in text
    assert "https://feishu.cn/docx/abc" in text


