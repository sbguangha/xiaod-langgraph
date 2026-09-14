from xiaod.evals.dataset import SAMPLE_CASES, langsmith_examples
from xiaod.evals.evaluators import evaluate_job, eval_has_feishu_url, eval_no_secrets, eval_not_summary
from xiaod.tools.lark import _markdown_blocks, document_title


def test_dataset_covers_voyage_shapes() -> None:
    ids = {case["id"] for case in SAMPLE_CASES}
    assert "xiaoyuzhou-20m" in ids
    assert "bilibili-short" in ids
    assert "youtube-long" in ids
    long_case = next(case for case in SAMPLE_CASES if case["id"] == "youtube-long")
    assert long_case["skip_slow"] is True
    assert langsmith_examples()


def test_local_eval_classifies_samples() -> None:
    for case in SAMPLE_CASES:
        result = evaluate_job(case)
        assert result["passed"], (case["id"], result["failed"])


def test_article_evaluators() -> None:
    good = "## 访谈里的判断\n亦仁说生财有术要做分享式提纯稿，并举了小宇宙的例子。" * 2
    assert eval_not_summary(good)
    assert not eval_has_feishu_url({"feishu_url": ""})
    assert eval_has_feishu_url({"feishu_url": "https://feishu.cn/docx/abc"})
    assert eval_no_secrets("文档已创建")
    assert not eval_no_secrets("Bearer sk-secret-token-value")


def test_doc_title_format() -> None:
    title = document_title("小宇宙", "跨国串门", when=__import__("datetime").date(2026, 9, 14))
    assert title == "[小宇宙]-跨国串门-整理稿-2026-09-14"


def test_markdown_blocks_use_sdk_types() -> None:
    blocks = _markdown_blocks("## 访谈\n亦仁说生财有术要做分享式提纯稿。")
    assert len(blocks) == 2
    assert blocks[0].block_type == 4
    assert blocks[0].heading2.elements[0].text_run.content == "访谈"
    assert blocks[1].block_type == 2
    assert "分享式提纯稿" in blocks[1].text.elements[0].text_run.content
