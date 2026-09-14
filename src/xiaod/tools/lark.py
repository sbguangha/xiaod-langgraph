"""Feishu document, ACL, and Bitable helpers."""

from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any
import json
import re
import subprocess

from xiaod.settings import Settings, get_settings
from xiaod.tracing import traceable

LOCAL_CONFIG_NAME = "local.json"


class LarkError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(message or code)


def _config_path(settings: Settings) -> Path:
    return settings.data_dir / LOCAL_CONFIG_NAME


def load_local_config(settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    path = _config_path(settings)
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def save_local_config(data: dict[str, Any], settings: Settings | None = None) -> None:
    settings = settings or get_settings()
    path = _config_path(settings)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def document_title(platform: str, title: str, when: date | None = None) -> str:
    day = (when or date.today()).isoformat()
    clean = re.sub(r"[\\/:*?\"<>|]", "", (title or "未命名").strip())[:40] or "未命名"
    return f"[{platform or '未知'}]-{clean}-整理稿-{day}"


def _client(settings: Settings):
    import lark_oapi as lark

    return (
        lark.Client.builder()
        .app_id(settings.feishu_app_id)
        .app_secret(settings.feishu_app_secret)
        .log_level(lark.LogLevel.WARNING)
        .build()
    )


def _text_block_content(content: str):
    from lark_oapi.api.docx.v1 import Text, TextElement, TextRun

    return (
        Text.builder()
        .elements([TextElement.builder().text_run(TextRun.builder().content(content[:8000]).build()).build()])
        .build()
    )


def _markdown_blocks(markdown: str) -> list[Any]:
    from lark_oapi.api.docx.v1 import Block

    heading_types = {1: (3, "heading1"), 2: (4, "heading2"), 3: (5, "heading3")}
    blocks: list[Any] = []
    for raw in (markdown or "").splitlines():
        line = raw.rstrip()
        if not line.strip():
            continue
        heading = re.match(r"^(#{1,3})\s+(.*)$", line)
        if heading:
            level = len(heading.group(1))
            block_type, field = heading_types[level]
            builder = Block.builder().block_type(block_type)
            getattr(builder, field)(_text_block_content(heading.group(2)))
            blocks.append(builder.build())
            continue
        blocks.append(Block.builder().block_type(2).text(_text_block_content(line)).build())
    if not blocks:
        blocks.append(Block.builder().block_type(2).text(_text_block_content(markdown or "（空）")).build())
    return blocks


@traceable(run_type="tool", name="lark_create_doc")
def create_markdown_doc(title: str, markdown: str, settings: Settings | None = None) -> dict[str, str]:
    settings = settings or get_settings()
    if not settings.has_feishu:
        raise LarkError("missing_app")
    from lark_oapi.api.docx.v1 import (
        CreateDocumentBlockChildrenRequest,
        CreateDocumentBlockChildrenRequestBody,
        CreateDocumentRequest,
        CreateDocumentRequestBody,
    )

    client = _client(settings)
    body = CreateDocumentRequestBody.builder().title(title)
    if settings.feishu_folder_token:
        body = body.folder_token(settings.feishu_folder_token)
    created = client.docx.v1.document.create(CreateDocumentRequest.builder().request_body(body.build()).build())
    if not created.success() or not created.data or not created.data.document:
        raise LarkError("feishu_failed", created.msg or "")
    document_id = created.data.document.document_id
    children = _markdown_blocks(markdown)
    for offset in range(0, len(children), 50):
        chunk = children[offset : offset + 50]
        written = client.docx.v1.document_block_children.create(
            CreateDocumentBlockChildrenRequest.builder()
            .document_id(document_id)
            .block_id(document_id)
            .document_revision_id(-1)
            .request_body(CreateDocumentBlockChildrenRequestBody.builder().children(chunk).index(-1).build())
            .build()
        )
        if not written.success():
            raise LarkError("feishu_failed", written.msg or "")
    url = f"https://feishu.cn/docx/{document_id}"
    return {"document_id": document_id, "url": url}


@traceable(run_type="tool", name="lark_grant_acl")
def grant_doc_permission(document_id: str, open_id: str, settings: Settings | None = None) -> bool:
    settings = settings or get_settings()
    if not open_id:
        return False
    if not settings.has_feishu:
        raise LarkError("missing_app")
    from lark_oapi.api.drive.v1 import BaseMember, CreatePermissionMemberRequest

    client = _client(settings)
    req = (
        CreatePermissionMemberRequest.builder()
        .token(document_id)
        .type("docx")
        .request_body(
            BaseMember.builder()
            .member_type("openid")
            .member_id(open_id)
            .perm("view")
            .build()
        )
        .build()
    )
    resp = client.drive.v1.permission_member.create(req)
    if resp.success():
        return True
    return _grant_via_cli(document_id, open_id)


def _grant_via_cli(document_id: str, open_id: str) -> bool:
    try:
        result = subprocess.run(
            [
                "lark-cli",
                "drive",
                "permissions",
                "members",
                "create",
                "--token",
                document_id,
                "--type",
                "docx",
                "--member-type",
                "openid",
                "--member-id",
                open_id,
                "--perm",
                "view",
                "--as",
                "user",
            ],
            check=False,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
        )
    except FileNotFoundError:
        return False
    return result.returncode == 0


@traceable(run_type="tool", name="lark_bitable_upsert")
def archive_social_row(item: dict[str, Any], settings: Settings | None = None) -> str:
    settings = settings or get_settings()
    if not settings.has_feishu:
        raise LarkError("missing_app")
    app_token, table_id = _ensure_bitable(settings)
    from lark_oapi.api.bitable.v1 import AppTableRecord, CreateAppTableRecordRequest

    client = _client(settings)
    url = str(item.get("url") or "")
    fields = {
        "平台": item.get("platform") or "",
        "标题": item.get("title") or "",
        "作者": item.get("author") or "",
        "链接": {"text": url, "link": url} if url else "",
        "摘要": (item.get("summary") or "")[:2000],
        "采集日": date.today().isoformat(),
        "cache_url": item.get("cache_url") or "",
    }
    req = (
        CreateAppTableRecordRequest.builder()
        .app_token(app_token)
        .table_id(table_id)
        .request_body(AppTableRecord.builder().fields(fields).build())
        .build()
    )
    resp = client.bitable.v1.app_table_record.create(req)
    if not resp.success() or not resp.data or not resp.data.record:
        raise LarkError("feishu_failed", getattr(resp, "msg", "") or "")
    return resp.data.record.record_id or ""


def _ensure_bitable(settings: Settings) -> tuple[str, str]:
    cfg = load_local_config(settings)
    if cfg.get("bitable_app_token") and cfg.get("bitable_table_id"):
        return str(cfg["bitable_app_token"]), str(cfg["bitable_table_id"])
    from lark_oapi.api.bitable.v1 import (
        AppTableCreateHeader,
        CreateAppRequest,
        CreateAppTableRequest,
        CreateAppTableRequestBody,
        ReqApp,
        ReqTable,
    )

    client = _client(settings)
    created = client.bitable.v1.app.create(
        CreateAppRequest.builder()
        .request_body(ReqApp.builder().name("小D收藏库").build())
        .build()
    )
    if not created.success() or not created.data or not created.data.app:
        raise LarkError("feishu_failed", getattr(created, "msg", "") or "")
    app_token = created.data.app.app_token
    fields = [
        AppTableCreateHeader.builder().field_name("平台").type(1).build(),
        AppTableCreateHeader.builder().field_name("标题").type(1).build(),
        AppTableCreateHeader.builder().field_name("作者").type(1).build(),
        AppTableCreateHeader.builder().field_name("链接").type(15).build(),
        AppTableCreateHeader.builder().field_name("摘要").type(1).build(),
        AppTableCreateHeader.builder().field_name("采集日").type(1).build(),
        AppTableCreateHeader.builder().field_name("cache_url").type(1).build(),
    ]
    table = client.bitable.v1.app_table.create(
        CreateAppTableRequest.builder()
        .app_token(app_token)
        .request_body(
            CreateAppTableRequestBody.builder()
            .table(ReqTable.builder().name("收藏").fields(fields).build())
            .build()
        )
        .build()
    )
    if not table.success() or not table.data or not table.data.table_id:
        raise LarkError("feishu_failed", getattr(table, "msg", "") or "")
    save_local_config({"bitable_app_token": app_token, "bitable_table_id": table.data.table_id}, settings)
    return app_token, table.data.table_id
