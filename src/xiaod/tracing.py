"""LangSmith tracing and secret redaction."""

from __future__ import annotations

from typing import Any
import os
import re

from langsmith import traceable
from langsmith.anonymizer import create_anonymizer

from xiaod.settings import Settings, get_settings

_SECRET_KEYS = (
    "FEISHU_APP_SECRET",
    "DEEPSEEK_API_KEY",
    "OPENAI_API_KEY",
    "LANGSMITH_API_KEY",
        "APP_SECRET",
    "Authorization",
    "cookie",
    "Cookie",
)

_anonymizer = create_anonymizer(
    [
        {"pattern": r"(?i)(app[_-]?secret|api[_-]?key|token|bearer|cookie)\s*[:=]\s*\S+", "replace": r"\1=<redacted>"},
        {"pattern": r"\bcli_[a-zA-Z0-9]{8,}\b", "replace": "cli_<redacted>"},
        {"pattern": r"\bsk-[A-Za-z0-9\-_]{10,}\b", "replace": "sk-<redacted>"},
        {"pattern": r"\bBearer\s+\S+", "replace": "Bearer <redacted>"},
    ]
)


def configure_langsmith(settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    if settings.has_langsmith:
        os.environ["LANGSMITH_TRACING"] = "true"
    else:
        os.environ["LANGSMITH_TRACING"] = "false"
    if settings.langsmith_api_key:
        os.environ["LANGSMITH_API_KEY"] = settings.langsmith_api_key
    os.environ["LANGSMITH_PROJECT"] = settings.langsmith_project
    if settings.langsmith_endpoint:
        os.environ["LANGSMITH_ENDPOINT"] = settings.langsmith_endpoint.rstrip("/")


def redact_text(text: str) -> str:
    redacted = _anonymizer(text)
    for key in _SECRET_KEYS:
        value = os.getenv(key, "")
        if value and len(value) >= 6:
            redacted = redacted.replace(value, "<redacted>")
    return redacted


def trace_metadata(state: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_type": state.get("source_type") or "",
        "duration_sec": state.get("duration_sec") or 0,
        "used_subtitle": bool(state.get("used_subtitle")),
        "thread_id": state.get("thread_id") or "",
        "route": state.get("route") or "",
    }


def looks_like_secret(text: str) -> bool:
    return bool(re.search(r"(app_secret|sk-|Bearer\s+\S+|cli_[a-zA-Z0-9]{12,})", text, re.I))


__all__ = ["traceable", "configure_langsmith", "redact_text", "trace_metadata", "looks_like_secret"]
