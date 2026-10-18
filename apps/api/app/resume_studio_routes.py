"""HTTP contract shared by the Resume Studio browser and external agents."""
from urllib.parse import quote
from uuid import UUID

import fitz
from fastapi import APIRouter, Depends, Header, HTTPException, Response
from pydantic import BaseModel
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .delivery_version_service import list_delivery_versions, record_snapshot, resolve_interview_resume
from .resume_studio_export import render_export
from .resume_studio_render import ResumeRenderError, render_document
from .resume_studio_schemas import StudioOperation
from .resume_studio_sample import sample_document
from .resume_studio_service import apply_operation, build_resume_filename, export_checks, get_or_create_document, read_document, reimport_source, source_diff
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
        # 草稿口径（未核对内容只提示）
        "checks": export_checks(row.document_json),
        # 正式投递口径（姓名 / 联系方式 / 高风险未核对事实会阻塞）
        "final_checks": export_checks(row.document_json, final=True),
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
    # 确认的是「正式投递版」，因此用 final=True：姓名、联系方式与高风险事实都会阻塞。
    checks = export_checks(row.document_json, final=True)
    if any(check["level"] == "block" for check in checks):
        raise HTTPException(409, {"message": "正式投递版还有必须处理的问题，请处理后再确认。", "checks": checks})
    rendered = _render(row)
    if not 1 <= rendered.page_count <= 2:
        raise HTTPException(409, {"message": "简历应控制在一至两页。", "page_count": rendered.page_count})
    with fitz.open(stream=rendered.pdf, filetype="pdf") as pdf:
        extracted = " ".join(page.get_text() for page in pdf)
    name = (row.document_json.get("basics") or {}).get("name", {}).get("text", "").strip()
    if not extracted.strip() or (name and name not in extracted):
        raise HTTPException(409, "PDF 文字无法正常提取，请检查字体和排版。")
    row.confirmed_revision = row.revision
    # 指令 4.2 / 5.3：确认正式投递版时保存不可变快照，供面试准备回溯「当初投的是哪份」。
    mission = db.get(models.JobMission, mission_id)
    snapshot = None
    if mission is not None:
        snapshot = record_snapshot(
            db,
            mission,
            row,
            source="STUDIO_CONFIRM",
            pdf_bytes=rendered.pdf,
            filename=build_resume_filename(
                name=name,
                company=mission.company if mission else None,
                role=mission.role if mission else None,
                revision=row.revision,
                draft=False,
            ),
        )
    db.commit()
    db.refresh(row)
    return {
        **read_document(row),
        "page_count": rendered.page_count,
        "checks": checks,
        "snapshot_id": str(snapshot.id) if snapshot else None,
    }


@router.get("/job-missions/{mission_id}/resume-studio/export")
def export_studio_text(
    mission_id: UUID,
    format: str = "markdown",
    draft: bool = False,
    db: Session = Depends(get_db),
) -> Response:
    """Markdown / 纯文本 / JSON 导出（不依赖 Typst）。

    与 PDF 同一口径：``draft=true`` 导出草稿（跳过投递前检查、文件名带 ``_DRAFT``）；
    默认按正式投递版自检，占位残留、空简历、缺姓名/联系方式、高风险未核对事实都会阻塞。
    """
    row = get_or_create_document(db, mission_id)
    checks = export_checks(row.document_json, final=not draft)
    if not draft and any(check["level"] == "block" for check in checks):
        raise HTTPException(409, {"message": "正文还有未完成内容（占位标记或空白简历），请补齐后再导出。", "checks": checks})
    try:
        body, media_type = render_export(row.document_json, format, getattr(row, "layout_config", None))
    except ValueError as exc:
        raise HTTPException(422, str(exc)) from exc
    ext = {"markdown": "md", "txt": "txt", "json": "json", "docx": "docx", "word": "docx"}.get(
        (format or "").strip().lower(), "txt"
    )
    document = row.document_json or {}
    name = (document.get("basics") or {}).get("name", {}).get("text", "")
    mission = db.get(models.JobMission, mission_id)
    filename = build_resume_filename(
        name=name,
        company=mission.company if mission else None,
        role=mission.role if mission else None,
        revision=row.revision,
        draft=draft,
        ext=ext,
    )
    return Response(
        body,
        media_type=media_type,
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Resume-Revision": str(row.revision),
            "X-Resume-Draft": "1" if draft else "0",
            "X-Resume-Filename": quote(filename),
        },
    )


def _stamp_draft(pdf_bytes: bytes) -> bytes:
    """给草稿 PDF 盖一个明确的草稿标记（ASCII 文案，避免字体缺字变乱码）。"""
    try:
        with fitz.open(stream=pdf_bytes, filetype="pdf") as document:
            for page in document:
                page.insert_text(
                    (36, 26),
                    "DRAFT - FOR REVIEW ONLY, NOT FOR SUBMISSION",
                    fontsize=10,
                    color=(0.72, 0.11, 0.11),
                )
            return document.tobytes()
    except Exception:  # noqa: BLE001 - 水印失败不能让草稿也导不出来
        return pdf_bytes


@router.get("/job-missions/{mission_id}/resume-studio/pdf")
def download_studio_pdf(mission_id: UUID, draft: bool = False, db: Session = Depends(get_db)) -> Response:
    """导出 PDF。

    - ``draft=true``：草稿，文件名带 ``_DRAFT``、正文盖草稿标记、可跳过未完成的检查；
    - 默认：正式投递版，必须通过全部投递前检查，并绑定当前修订号。
    """
    row = get_or_create_document(db, mission_id)
    mission = db.get(models.JobMission, mission_id)
    document = row.document_json or {}
    checks = export_checks(document, final=not draft)
    blocking = [check for check in checks if check["level"] == "block"]
    if not draft:
        if row.confirmed_revision != row.revision:
            raise HTTPException(409, "请先确认当前修订版，再下载正式投递版 PDF。")
        if blocking:
            raise HTTPException(409, {"message": "正式投递版还有必须处理的问题。", "checks": checks})
    rendered = _render(row)
    payload = _stamp_draft(rendered.pdf) if draft else rendered.pdf
    name = (document.get("basics") or {}).get("name", {}).get("text", "")
    filename = build_resume_filename(
        name=name,
        company=mission.company if mission else None,
        role=mission.role if mission else None,
        revision=row.revision,
        draft=draft,
    )
    return Response(
        payload,
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename*=UTF-8''{quote(filename)}",
            "X-Resume-Revision": str(row.revision),
            "X-Resume-Draft": "1" if draft else "0",
            "X-Resume-Filename": quote(filename),
        },
    )


@router.get("/job-missions/{mission_id}/interview-resume")
def read_interview_resume(
    mission_id: UUID,
    application_id: UUID | None = None,
    db: Session = Depends(get_db),
) -> dict:
    """面试准备应该使用的简历版本（指令 5.3）。

    默认读取**实际投递出去**的那一份（投递快照），多次投递可用 ``application_id`` 指定；
    尚未投递时返回 ``studio_current``，并带「尚无正式投递版本，当前使用准备中的简历。」标注。
    """
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(404, "岗位任务不存在。")
    resolved = resolve_interview_resume(db, mission, application_id=application_id)
    if resolved is None:
        return {
            "source": "none",
            "label": "这个岗位还没有可用来准备面试的简历版本。",
            "warning": None,
            "bullets": [],
            "versions": [],
        }
    return resolved


@router.get("/job-missions/{mission_id}/delivery-versions")
def read_delivery_versions(mission_id: UUID, db: Session = Depends(get_db)) -> dict:
    """列出该岗位的历史投递版本，供用户明确选择使用哪一次。"""
    return {"mission_id": str(mission_id), "versions": list_delivery_versions(db, mission_id)}
