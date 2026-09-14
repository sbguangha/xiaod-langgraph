"""Persist last pending question per Feishu user."""

from __future__ import annotations

from typing import Any
import json

from xiaod.settings import get_settings


def _path():
    return get_settings().data_dir / "pending.json"


def load_all() -> dict[str, Any]:
    path = _path()
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_pending(open_id: str, payload: dict[str, Any]) -> None:
    data = load_all()
    data[open_id] = payload
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def pop_pending(open_id: str) -> dict[str, Any] | None:
    data = load_all()
    item = data.pop(open_id, None)
    path = _path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
    return item


def get_pending(open_id: str) -> dict[str, Any] | None:
    return load_all().get(open_id)
