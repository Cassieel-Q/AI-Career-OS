"""HTTP contract shared by the Resume Studio browser and external agents."""
from urllib.parse import quote
from uuid import UUID

import fitz
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .resume_studio_export import render_export
from .resume_studio_render import ResumeRenderError, render_document
from .resume_studio_schemas import StudioOperation
from .resume_studio_sample import sample_document
from .resume_studio_service import apply_operation, export_checks, get_or_create_document, read_document, reimport_source, source_diff
from .resume_studio_templates import get_template, list_templates

router = APIRouter(prefix="/api/v1")


class PreviewRequest(BaseModel):
    revision: int


def _revision(value: str | None) -> int:
    if value is None:
        raise HTTPException(428, "请先读取最新简历修订号。")
    try:
        return int(value.strip('"'))
    except ValueError as exc:
        raise HTTPException(400, "If-Match 必须是整数修订号。") from exc


def _render(row):
    try:
        return render_document(row.document_json, row.template_id, getattr(row, "layout_config", None))
    except ResumeRenderError as exc:
        raise HTTPException(422, str(exc)) from exc


@router.get("/resume-studio/templates")
def templates() -> list[dict]:
    return [{**item, "sample_preview_url": f"/api/v1/resume-studio/templates/{item['id']}/sample-preview"} for item in list_templates()]


@router.get("/resume-studio/templates/{template_id}/sample-preview")
def template_sample_preview(template_id: str) -> dict:
    template = get_template(template_id)
    try:
        rendered = render_document(sample_document(template["language"]), template_id)
    except ResumeRenderError as exc:
        raise HTTPException(422, str(exc)) from exc
    return {"template_id": template_id, "page_count": rendered.page_count, "pages": rendered.pages}


@router.get("/job-missions/{mission_id}/resume-studio")
def read_studio(mission_id: UUID, db: Session = Depends(get_db)) -> dict:
    return read_document(get_or_create_document(db, mission_id))


@router.get("/job-missions/{mission_id}/resume-studio/source-diff")
def read_source_diff(mission_id: UUID, db: Session = Depends(get_db)) -> dict:
    return source_diff(db, mission_id)


@router.post("/job-missions/{mission_id}/resume-studio/reimport")
def reimport_studio(
    mission_id: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
) -> dict:
    return reimport_source(db, mission_id, _revision(if_match))


@router.patch("/job-missions/{mission_id}/resume-studio")
def edit_studio(
    mission_id: UUID,
    operation: StudioOperation,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
) -> dict:
    return apply_operation(db, mission_id, _revision(if_match), operation)


@router.post("/job-missions/{mission_id}/resume-studio/preview")
def preview_studio(mission_id: UUID, request: PreviewRequest, db: Session = Depends(get_db)) -> dict:
    row = get_or_create_document(db, mission_id)
    if request.revision != row.revision:
        raise HTTPException(409, {"message": "预览修订号已过期。", "latest": read_document(row)})
    result = _render(row)
    return {
        "revision": row.revision,
        "template_id": row.template_id,
        "page_count": result.page_count,
        "pages": result.pages,
        "layout_map": result.layout_map,
        "checks": export_checks(row.document_json),
    }


@router.post("/job-missions/{mission_id}/resume-studio/confirm")
def confirm_studio(
    mission_id: UUID,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
) -> dict:
    row = get_or_create_document(db, mission_id)
    if _revision(if_match) != row.revision:
        raise HTTPException(409, {"message": "简历已更新，请重新检查。", "latest": read_document(row)})
    checks = export_checks(row.document_json)
    if any(check["level"] == "block" for check in checks):
        raise HTTPException(409, {"message": "请先核对标记的事实。", "checks": checks})
    rendered = _render(row)
    if not 1 <= rendered.page_count <= 2:
        raise HTTPException(409, {"message": "简历应控制在一至两页。", "page_count": rendered.page_count})
    with fitz.open(stream=rendered.pdf, filetype="pdf") as pdf:
        extracted = " ".join(page.get_text() for page in pdf)
    name = (row.document_json.get("basics") or {}).get("name", {}).get("text", "").strip()
    if not extracted.strip() or (name and name not in extracted):
        raise HTTPException(409, "PDF 文字无法正常提取，请检查字体和排版。")
    row.confirmed_revision = row.revision
    db.commit()
    db.refresh(row)
    return {**read_document(row), "page_count": rendered.page_count, "checks": checks}


@router.get("/job-missions/{mission_id}/resume-studio/export")
def export_studio_text(
    mission_id: UUID,
    format: str = "markdown",
    draft: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    """Markdown / 纯文本 / JSON 导出（不依赖 Typst）。

    默认沿用与 PDF 相同的事实门禁；``draft=true`` 允许导出草稿自检，
    与 ResumeForge 的「仍要导出草稿」对齐。
    """
    row = get_or_create_document(db, mission_id)
    checks = export_checks(row.document_json)
    if not draft and any(check["level"] == "block" for check in checks):
        raise HTTPException(409, {"message": "请先核对标记的事实或补全占位内容。", "checks": checks})
    try:
        body, media_type = render_export(row.document_json, format, getattr(row, "layout_config", None))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ext = {"markdown": "md", "txt": "txt", "json": "json", "docx": "docx", "word": "docx"}.get(
        (format or "").strip().lower(), "txt"
    )
    name = (row.document_json.get("basics") or {}).get("name", {}).get("text", "")
    mission = db.get(models.JobMission, mission_id)
    pieces = [name, mission.company if mission else "", mission.role if mission else ""]
    safe_parts = ["".join(char for char in piece if char.isalnum() or char in "-_ ").strip()[:40] for piece in pieces]
    base = "-".join(piece for piece in safe_parts if piece) or "简历"
    filename = f"{base}.{ext}"
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename=resume.{ext}; filename*=UTF-8''{quote(filename)}",
            "X-Resume-Revision": str(row.revision),
        },
    )


@router.get("/job-missions/{mission_id}/resume-studio/pdf")
def download_studio_pdf(mission_id: UUID, db: Session = Depends(get_db)) -> Response:
    row = get_or_create_document(db, mission_id)
    if row.confirmed_revision != row.revision:
        raise HTTPException(409, "请先确认当前修订版，再下载 PDF。")
    rendered = _render(row)
    name = (row.document_json.get("basics") or {}).get("name", {}).get("text", "")
    mission = db.get(models.JobMission, mission_id)
    pieces = [name, mission.company if mission else "", mission.role if mission else "", row.language]
    safe_parts = ["".join(char for char in piece if char.isalnum() or char in "-_ ").strip()[:40] for piece in pieces]
    filename = f"{'-'.join(piece for piece in safe_parts if piece)}.pdf"
    return Response(
        rendered.pdf,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=resume.pdf; filename*=UTF-8''{quote(filename)}",
            "X-Resume-Revision": str(row.revision),
        },
    )
