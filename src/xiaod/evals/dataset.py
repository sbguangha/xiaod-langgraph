"""Voyage-style sample cases. Long YouTube is marked skip-slow."""

from __future__ import annotations

SAMPLE_CASES = [
    {
        "id": "xiaoyuzhou-20m",
        "input": "请转录 https://www.xiaoyuzhoufm.com/episode/6a49649f3fb7233cbf43c439",
        "expect_source": "xiaoyuzhou",
        "expect_route": "xiaod",
        "skip_slow": False,
    },
    {
        "id": "bilibili-short",
        "input": "整理这个 B 站视频 https://www.bilibili.com/video/BV1xx411c7mD",
        "expect_source": "bilibili",
        "expect_route": "xiaod",
        "skip_slow": False,
    },
    {
        "id": "youtube-long",
        "input": "请转录 https://www.youtube.com/watch?v=dQw4w9WgXcQ",
        "expect_source": "youtube",
        "expect_route": "xiaod",
        "skip_slow": True,
    },
    {
        "id": "xhs-out-of-scope",
        "input": "归档 https://www.xiaohongshu.com/explore/64f000000000000000000001",
        "expect_source": "xhs",
        "expect_route": "human",
        "skip_slow": False,
    },
]


def langsmith_examples() -> list[dict]:
    return [
        {
            "inputs": {"input_text": case["input"]},
            "outputs": {"source_type": case["expect_source"], "route": case["expect_route"]},
            "metadata": {"id": case["id"], "skip_slow": case["skip_slow"]},
        }
        for case in SAMPLE_CASES
    ]
