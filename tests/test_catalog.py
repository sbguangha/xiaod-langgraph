from xiaod.tools.catalog import ALL_TOOLS


def test_catalog_exposes_media_and_feishu_tools() -> None:
    names = {tool.name for tool in ALL_TOOLS}
    assert names == {
        "fetch_subtitles",
        "probe_media",
        "download_audio",
        "transcribe_audio",
        "split_audio",
        "create_feishu_doc",
        "grant_feishu_acl",
    }
    for tool in ALL_TOOLS:
        assert tool.description
