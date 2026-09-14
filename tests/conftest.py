from pathlib import Path
import os

import pytest


@pytest.fixture(autouse=True)
def _isolate_data_dir(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("XIAOD_DATA_DIR", str(tmp_path))
    monkeypatch.setenv("LANGSMITH_TRACING", "false")
    os.environ.pop("LANGSMITH_API_KEY", None)
