"""模板工作台路由（目标五）：HTML 导入、参考模板识别草稿、版式配置编辑。

Preview / PDF / Word / Markdown 共用同一份 layout_config；本路由负责生成与编辑该配置。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from . import resume_template_service as svc
from .database import get_db
from .resume_layout import DEFAULT_LAYOUT_CONFIG, normalize_layout_config

router = APIRouter(prefix="/api/v1")

MAX_TEMPLATE_BYTES = 2 * 1024 * 1024


class HtmlImportPayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    html: str
    source_ref: str | None = None


class DraftPatch(BaseModel):
    model_config = ConfigDict(extra="ignore")

    layout_config: dict | None = None
    status: str | None = None


@router.get("/resume-studio/layout/default")
def read_default_layout() -> dict:
    """版式配置默认值（前端控件用它渲染初值）。"""
    return normalize_layout_config(DEFAULT_LAYOUT_CONFIG)


@router.post("/profiles/{profile_id}/resume-template-drafts/html", status_code=201)
def import_html_draft(profile_id: UUID, payload: HtmlImportPayload, db: Session = Depends(get_db)) -> dict:
    fields = svc.build_draft("HTML", html=payload.html, source_ref=payload.source_ref)
    row = svc.create_draft(db, profile_id, fields)
    return svc.draft_read(row)


@router.post("/profiles/{profile_id}/resume-template-drafts/upload", status_code=201)
async def upload_reference_template(
    profile_id: UUID,
    file: UploadFile = File(...),
    source_kind: str | None = Form(default=None),
    db: Session = Depends(get_db),
) -> dict:
    """上传 图片 / PDF / DOCX（或 HTML 文件）作为参考模板 → 识别为草稿。"""
    filename = (file.filename or "").strip()
    name_lower = filename.lower()
    data = await file.read(MAX_TEMPLATE_BYTES + 1)
    if len(data) > MAX_TEMPLATE_BYTES:
        raise HTTPException(413, "模板文件超过 2MB，请压缩后重试。")
    if not data:
        raise HTTPException(422, "模板文件为空。")

    kind = (source_kind or "").strip().upper()
    if not kind:
        if name_lower.endswith((".html", ".htm")):
            kind = "HTML"
        elif name_lower.endswith(".pdf"):
            kind = "PDF"
        elif name_lower.endswith(".docx"):
            kind = "DOCX"
        elif name_lower.endswith((".png", ".jpg", ".jpeg", ".webp")):
            kind = "IMAGE"
        else:
            raise HTTPException(415, "无法识别的模板文件类型（支持 html/htm/pdf/docx/png/jpg/jpeg/webp）。")

    if kind == "HTML":
        head = data[:4096].decode("utf-8", errors="ignore")
        if "<" not in head and "<!doctype" not in head.casefold():
            raise HTTPException(415, "该文件不像 HTML 模板。")
        fields = svc.build_draft("HTML", html=data.decode("utf-8", errors="ignore"), source_ref=filename or None)
    else:
        fields = svc.build_draft(kind, data=data, source_ref=filename or None)
    row = svc.create_draft(db, profile_id, fields)
    return svc.draft_read(row)


@router.get("/profiles/{profile_id}/resume-template-drafts")
def list_reference_drafts(profile_id: UUID, db: Session = Depends(get_db)) -> list[dict]:
    return [svc.draft_read(row) for row in svc.list_drafts(db, profile_id)]


@router.get("/resume-template-drafts/{draft_id}")
def read_reference_draft(draft_id: UUID, db: Session = Depends(get_db)) -> dict:
    return svc.draft_read(svc.get_draft(db, draft_id))


@router.patch("/resume-template-drafts/{draft_id}")
def patch_reference_draft(draft_id: UUID, payload: DraftPatch, db: Session = Depends(get_db)) -> dict:
    row = svc.update_draft(db, draft_id, layout_config=payload.layout_config, status=payload.status)
    return svc.draft_read(row)


@router.post("/resume-template-drafts/{draft_id}/confirm")
def confirm_reference_draft(draft_id: UUID, db: Session = Depends(get_db)) -> dict:
    return svc.draft_read(svc.confirm_draft(db, draft_id))
