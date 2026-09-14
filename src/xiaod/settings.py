"""Load environment configuration. Secrets never go into traces or chat."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os

from dotenv import load_dotenv


def _project_root() -> Path:
    return Path(__file__).resolve().parents[2]


def load_env() -> None:
    load_dotenv(_project_root() / ".env", override=False)
    if os.getenv("LANGSMITH_TRACING", "").lower() in {"1", "true", "yes"}:
        os.environ.setdefault("LANGSMITH_PROJECT", "xiaod")


@dataclass(frozen=True)
class Settings:
    langsmith_tracing: bool
    langsmith_api_key: str
    langsmith_project: str
    langsmith_endpoint: str
    deepseek_api_key: str
    llm_model: str
    llm_base_url: str
    feishu_app_id: str
    feishu_app_secret: str
    feishu_folder_token: str
    whisper_model: str
    ffmpeg_bin: str
    data_dir: Path
    web_host: str
    web_port: int

    @property
    def has_llm(self) -> bool:
        return bool(self.deepseek_api_key)

    @property
    def has_feishu(self) -> bool:
        return bool(self.feishu_app_id and self.feishu_app_secret)

    @property
    def has_langsmith(self) -> bool:
        return bool(self.langsmith_api_key and self.langsmith_tracing)


def get_settings() -> Settings:
    load_env()
    data_dir = Path(os.getenv("XIAOD_DATA_DIR", "data"))
    if not data_dir.is_absolute():
        data_dir = _project_root() / data_dir
    data_dir.mkdir(parents=True, exist_ok=True)
    return Settings(
        langsmith_tracing=os.getenv("LANGSMITH_TRACING", "true").lower() in {"1", "true", "yes"},
        langsmith_api_key=os.getenv("LANGSMITH_API_KEY", "").strip(),
        langsmith_project=os.getenv("LANGSMITH_PROJECT", "xiaod").strip() or "xiaod",
        langsmith_endpoint=os.getenv("LANGSMITH_ENDPOINT", "").strip(),
        deepseek_api_key=os.getenv("DEEPSEEK_API_KEY", "").strip() or os.getenv("OPENAI_API_KEY", "").strip(),
        llm_model=os.getenv("LLM_MODEL", "deepseek-chat").strip() or "deepseek-chat",
        llm_base_url=os.getenv("LLM_BASE_URL", "https://api.deepseek.com").strip(),
        feishu_app_id=os.getenv("FEISHU_APP_ID", "").strip(),
        feishu_app_secret=os.getenv("FEISHU_APP_SECRET", "").strip(),
        feishu_folder_token=os.getenv("FEISHU_FOLDER_TOKEN", "").strip(),
        whisper_model=os.getenv("WHISPER_MODEL", "small").strip() or "small",
        ffmpeg_bin=os.getenv("FFMPEG_BIN", "ffmpeg").strip() or "ffmpeg",
        data_dir=data_dir,
        web_host=os.getenv("XIAOD_WEB_HOST", "127.0.0.1").strip() or "127.0.0.1",
        web_port=int(os.getenv("XIAOD_WEB_PORT", "8765") or "8765"),
    )
