"""Feishu document and ACL helpers."""

from __future__ import annotations

from datetime import date
from typing import Any
import re
import subprocess

from xiaod.settings import Settings, get_settings
from xiaod.tracing import traceable


class LarkError(Exception):
    def __init__(self, code: str, message: str = "") -> None:
        self.code = code
        self.message = message
        super().__init__(message or code)


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
