"""DeepSeek-compatible chat model used only for share-draft purify."""

from __future__ import annotations

from xiaod.nodes.clean import load_purify_prompt, rule_based_purify
from xiaod.settings import Settings, get_settings
from xiaod.tracing import traceable


@traceable(run_type="llm", name="purify_share_draft")
def purify_share_draft(transcript: str, *, platform: str, title: str, settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    fallback = rule_based_purify(transcript, platform=platform, title=title)
    if not settings.has_llm:
        return fallback
    try:
        from langchain_openai import ChatOpenAI
        from langchain_core.messages import HumanMessage, SystemMessage
    except Exception:
        return fallback
    model = ChatOpenAI(
        model=settings.llm_model,
        api_key=settings.deepseek_api_key,
        base_url=settings.llm_base_url,
        temperature=0.2,
    )
    prompt = (
        f"来源平台：{platform}\n原标题：{title}\n\n清洗后的逐字稿：\n{transcript}"
    )
    response = model.invoke(
        [SystemMessage(content=load_purify_prompt()), HumanMessage(content=prompt)]
    )
    text = str(getattr(response, "content", "") or "").strip()
    return text or fallback
