"""参考模板识别与模板草稿（目标五）。

设计原则（诚实标注）：
- HTML：可解析 → 清洗 script/外链/内联事件，并提取 accent 颜色与分栏线索；
- PDF / DOCX：可提取文字与文档内颜色线索，据此给出**草稿**版式；
- IMAGE：本地无 OCR / 视觉识别能力，**不假装识别**——生成默认版式草稿并标注
  ``image_requires_manual_review``，由用户在版式控件里手动调整。

所有来源都先落 ``resume_template_drafts``（status=DRAFT），用户确认后才变成可用模板；
模型/规则都不能直接写任意 HTML（只产出受限 layout_config + 白名单清洗后的片段）。
"""
from __future__ import annotations

import io
import re
import zipfile
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .resume_layout import DEFAULT_LAYOUT_CONFIG, layout_config_from_html, normalize_layout_config, sanitize_template_html

SOURCE_KINDS = {"IMAGE", "PDF", "DOCX", "HTML"}
STATUSES = {"DRAFT", "CONFIRMED"}


def _docx_text_and_colors(data: bytes) -> tuple[str, list[str]]:
    try:
        with zipfile.ZipFile(io.BytesIO(data)) as archive:
            xml = archive.read("word/document.xml").decode("utf-8", errors="ignore")
    except (KeyError, zipfile.BadZipFile) as exc:
        raise HTTPException(415, "不是有效的 DOCX 文件。") from exc
    colors = [f"#{m.lower()}" for m in re.findall(r'w:color\s+w:val="([0-9A-Fa-f]{6})"', xml)]
    text = re.sub(r"<[^>]+>", " ", xml)
    text = re.sub(r"\s+", " ", text).strip()
    return text, colors


def _pdf_text_and_colors(data: bytes) -> tuple[str, list[str]]:
    try:
        import fitz  # PyMuPDF
    except ImportError:  # pragma: no cover
        return "", []
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(415, "不是有效的 PDF 文件。") from exc
    colors: list[str] = []
    try:
        pages = [page.get_text() for page in document]
        for page in document:
            try:
                for block in page.get_text("dict").get("blocks", []):
                    for line in block.get("lines", []):
                        for span in line.get("spans", []):
                            color = span.get("color")
                            if isinstance(color, int):
                                colors.append(f"#{color & 0xFFFFFF:06x}")
            except Exception:  # noqa: BLE001
                continue
    finally:
        document.close()
    return "\n".join(pages).strip(), colors


def _draft_from_html(html: str) -> tuple[dict, str, list[str]]:
    sanitized, warnings = sanitize_template_html(html)
    layout = layout_config_from_html(sanitized)
    if not sanitized.strip():
        warnings.append("html_empty_after_sanitize")
    return layout, sanitized, warnings


def _draft_from_pdf(data: bytes) -> tuple[dict, str | None, list[str]]:
    text, colors = _pdf_text_and_colors(data)
    layout = dict(DEFAULT_LAYOUT_CONFIG)
    warnings: list[str] = ["pdf_layout_inferred"]
    if colors:
        # 取出现次数最多、且不太可能只是默认黑的颜色作为 accent。
        from collections import Counter

        counts = Counter(c for c in colors if c not in {"#000000", "#010101"})
        if counts:
            layout["accent_color"] = counts.most_common(1)[0][0]
    if not text.strip():
        warnings.append("pdf_no_text_layer")
    return normalize_layout_config(layout), None, warnings


def _draft_from_docx(data: bytes) -> tuple[dict, str | None, list[str]]:
    text, colors = _docx_text_and_colors(data)
    layout = dict(DEFAULT_LAYOUT_CONFIG)
    warnings: list[str] = ["docx_layout_inferred"]
    if colors:
        from collections import Counter

        counts = Counter(c for c in colors if c not in {"#000000", "#010101"})
        if counts:
            layout["accent_color"] = counts.most_common(1)[0][0]
    if not text.strip():
        warnings.append("docx_no_text")
    return normalize_layout_config(layout), None, warnings


def build_draft(source_kind: str, *, html: str | None = None, data: bytes | None = None, source_ref: str | None = None) -> dict:
    """按来源类型生成模板草稿字段（不落库）。"""
    kind = (source_kind or "").strip().upper()
    if kind not in SOURCE_KINDS:
        raise HTTPException(422, f"source_kind 必须是 {sorted(SOURCE_KINDS)} 之一。")
    if kind == "HTML":
        if html is None and data is not None:
            html = data.decode("utf-8", errors="ignore")
        if html is None:
            raise HTTPException(422, "HTML 模板需要 html 或文件内容。")
        layout, sanitized, warnings = _draft_from_html(html)
        return {"source_kind": kind, "layout_config": layout, "sanitized_html": sanitized, "warnings": warnings, "source_ref": source_ref}
    if data is None:
        raise HTTPException(422, f"{kind} 模板需要上传文件内容。")
    if kind == "DOCX":
        layout, sanitized, warnings = _draft_from_docx(data)
    elif kind == "PDF":
        layout, sanitized, warnings = _draft_from_pdf(data)
    else:  # IMAGE
        layout, sanitized, warnings = normalize_layout_config(DEFAULT_LAYOUT_CONFIG), None, ["image_requires_manual_review"]
    return {"source_kind": kind, "layout_config": layout, "sanitized_html": sanitized, "warnings": warnings, "source_ref": source_ref}


def create_draft(db: Session, profile_id: UUID, fields: dict) -> models.ResumeTemplateDraft:
    row = models.ResumeTemplateDraft(
        profile_id=profile_id,
        source_kind=fields["source_kind"],
        source_ref=fields.get("source_ref"),
        layout_config=fields["layout_config"],
        sanitized_html=fields.get("sanitized_html"),
        status="DRAFT",
        warnings=list(fields.get("warnings") or []),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_drafts(db: Session, profile_id: UUID) -> list[models.ResumeTemplateDraft]:
    return list(
        db.scalars(
            select(models.ResumeTemplateDraft)
            .where(models.ResumeTemplateDraft.profile_id == profile_id)
            .order_by(models.ResumeTemplateDraft.created_at.desc())
        ).all()
    )


def get_draft(db: Session, draft_id: UUID) -> models.ResumeTemplateDraft:
    row = db.get(models.ResumeTemplateDraft, draft_id)
    if row is None:
        raise HTTPException(404, "模板草稿不存在。")
    return row


def update_draft(db: Session, draft_id: UUID, *, layout_config: dict | None, status: str | None) -> models.ResumeTemplateDraft:
    row = get_draft(db, draft_id)
    if layout_config is not None:
        # 用户可改颜色、字号、间距、分栏、照片、栏目顺序——统一走归一化白名单。
        row.layout_config = normalize_layout_config({**(row.layout_config or {}), **layout_config})
        if row.status == "CONFIRMED":
            row.status = "DRAFT"  # 已确认草稿被再次编辑 → 退回待确认
    if status is not None:
        if status not in STATUSES:
            raise HTTPException(422, f"status 必须是 {sorted(STATUSES)} 之一。")
        row.status = status
    db.commit()
    db.refresh(row)
    return row


def confirm_draft(db: Session, draft_id: UUID) -> models.ResumeTemplateDraft:
    row = get_draft(db, draft_id)
    if not row.layout_config:
        raise HTTPException(409, "草稿缺少版式配置，无法确认。")
    row.status = "CONFIRMED"
    db.commit()
    db.refresh(row)
    return row


def draft_read(row: models.ResumeTemplateDraft) -> dict:
    return {
        "id": str(row.id),
        "profile_id": str(row.profile_id),
        "source_kind": row.source_kind,
        "source_ref": row.source_ref,
        "layout_config": normalize_layout_config(row.layout_config),
        "sanitized_html": row.sanitized_html,
        "status": row.status,
        "warnings": list(row.warnings or []),
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "updated_at": row.updated_at.isoformat() if row.updated_at else None,
    }


__all__ = [
    "SOURCE_KINDS",
    "build_draft",
    "create_draft",
    "list_drafts",
    "get_draft",
    "update_draft",
    "confirm_draft",
    "draft_read",
]
