"""Rule evaluators: no timestamps, not a summary, Feishu URL, ACL."""

from __future__ import annotations

from typing import Any

from xiaod.nodes.classify import classify_text
from xiaod.nodes.clean import qa_share_draft
from xiaod.tracing import looks_like_secret


def eval_no_timestamps(article: str) -> bool:
    ok, reasons = qa_share_draft(article)
    return "timestamp" not in reasons and bool(article)


def eval_not_summary(article: str) -> bool:
    ok, reasons = qa_share_draft(article)
    return "summary" not in reasons and "trash_title" not in reasons


def eval_has_feishu_url(state: dict[str, Any]) -> bool:
    url = str(state.get("feishu_url") or "")
    return url.startswith("https://") and "feishu" in url


def eval_permission_granted(state: dict[str, Any]) -> bool:
    return bool(state.get("permission_granted"))


def eval_no_secrets(text: str) -> bool:
    return not looks_like_secret(text or "")


def evaluate_job(case: dict[str, Any], state: dict[str, Any] | None = None) -> dict[str, Any]:
    guessed = classify_text(case["input"])
    failed: list[str] = []
    if guessed.source_type != case["expect_source"]:
        failed.append("source")
    if guessed.route != case["expect_route"]:
        failed.append("route")
    if state:
        article = str(state.get("article") or "")
        if article and not eval_no_timestamps(article):
            failed.append("timestamp")
        if article and not eval_not_summary(article):
            failed.append("summary")
        if state.get("status") == "done" and not eval_has_feishu_url(state):
            failed.append("feishu_url")
        if state.get("status") == "done" and not eval_permission_granted(state):
            failed.append("permission")
        if not eval_no_secrets(str(state.get("reply_message") or "")):
            failed.append("secret")
    return {"id": case["id"], "passed": not failed, "failed": failed, "route": guessed.route}
