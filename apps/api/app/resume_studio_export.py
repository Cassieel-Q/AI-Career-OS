"""Render a Resume Studio document to portable text formats without Typst.

These exports are pure functions over ``document_json``: they never require the
Typst binary or a system font, so a user can always keep a Markdown / plain-text
archive or a structured JSON backup even on machines without the PDF toolchain.

目标五硬约束：Preview / PDF / Word / Markdown 必须使用同一份版式配置。因此本模块的
所有导出入口都接收 ``layout_config``，并用 ``resume_layout.apply_section_order`` 排出
与预览一致的栏目顺序（accent 颜色等同时写入 Word 标题）。
"""
from __future__ import annotations

import io
import json
import zipfile
from xml.sax.saxutils import escape as _xml_escape

from .resume_layout import apply_section_order, normalize_layout_config


def _node_text(node: dict | None) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("text") or "").strip()


def _ordered_sections(document: dict, layout_config: dict | None) -> list[dict]:
    """应用版式配置的 section_order，返回与预览一致的 section 列表。"""
    ordered = apply_section_order(document or {}, layout_config)
    return list(ordered.get("sections") or [])


def _included_entries(document: dict, layout_config: dict | None = None) -> list[tuple[str, list[dict]]]:
    """Return [(section_title, [included entries])] with omitted nodes dropped."""
    result: list[tuple[str, list[dict]]] = []
    for section in _ordered_sections(document, layout_config):
        title = _node_text(section.get("title")) or str(section.get("kind") or "板块")
        entries: list[dict] = []
        for entry in section.get("entries") or []:
            if entry.get("status") == "OMITTED":
                continue
            bullets = [
                _node_text(bullet)
                for bullet in entry.get("bullets") or []
                if bullet.get("claim_status") != "OMITTED" and _node_text(bullet)
            ]
            entries.append(
                {
                    "title": _node_text(entry.get("title")),
                    "subtitle": _node_text(entry.get("subtitle")),
                    "date": _node_text(entry.get("date")),
                    "bullets": bullets,
                }
            )
        result.append((title, entries))
    return result


def _entry_heading(entry: dict) -> str:
    title = entry.get("title") or ""
    subtitle = entry.get("subtitle") or ""
    date = entry.get("date") or ""
    middle = " · ".join(part for part in (title, subtitle) if part)
    if date:
        middle = f"{middle}（{date}）" if middle else date
    return middle


def _basics(document: dict) -> dict[str, str]:
    basics = document.get("basics") or {}
    labels = {"name": "姓名", "phone": "电话", "email": "邮箱", "location": "地点"}
    return {labels.get(key, key): _node_text(node) for key, node in basics.items() if isinstance(node, dict)}


def render_markdown(document: dict, layout_config: dict | None = None) -> str:
    """Markdown export: full fields except photos, suitable for text archival."""
    basics = _basics(document)
    lines: list[str] = []
    name = basics.pop("姓名", "")
    lines.append(f"# {name}".strip())
    contact = " · ".join(value for value in basics.values() if value)
    if contact:
        lines.append("")
        lines.append(contact)
    for section_title, entries in _included_entries(document, layout_config):
        lines.append("")
        lines.append(f"## {section_title}")
        for entry in entries:
            heading = _entry_heading(entry)
            if heading:
                lines.append("")
                lines.append(f"### {heading}")
            for bullet in entry["bullets"]:
                lines.append(f"- {bullet}")
    return "\n".join(lines).strip() + "\n"


def render_plain_text(document: dict, layout_config: dict | None = None) -> str:
    """Plain-text export: the simplest archive with no Markdown markup."""
    basics = _basics(document)
    lines: list[str] = []
    name = basics.pop("姓名", "")
    if name:
        lines.append(name)
    contact = " · ".join(value for value in basics.values() if value)
    if contact:
        lines.append(contact)
    for section_title, entries in _included_entries(document, layout_config):
        if not entries:
            continue
        lines.append("")
        lines.append(f"【{section_title}】")
        for entry in entries:
            heading = _entry_heading(entry)
            if heading:
                lines.append("")
                lines.append(heading)
            for bullet in entry["bullets"]:
                lines.append(f"- {bullet}")
    return "\n".join(lines).strip() + "\n"


def render_json(document: dict, layout_config: dict | None = None) -> str:
    """JSON export: structured backup for later processing (photos excluded)."""
    basics = document.get("basics") or {}
    labels = {"name": "name", "phone": "phone", "email": "email", "location": "location"}
    sections: list[dict[str, object]] = []
    for section in _ordered_sections(document, layout_config):
        kind = section.get("kind")
        title = _node_text(section.get("title")) or kind
        entries = [
            {
                "title": _node_text(entry.get("title")),
                "subtitle": _node_text(entry.get("subtitle")),
                "date": _node_text(entry.get("date")),
                "bullets": [
                    _node_text(bullet)
                    for bullet in entry.get("bullets") or []
                    if bullet.get("claim_status") != "OMITTED" and _node_text(bullet)
                ],
            }
            for entry in section.get("entries") or []
            if entry.get("status") != "OMITTED"
        ]
        sections.append({"kind": kind, "title": title, "entries": entries})
    payload: dict[str, object] = {
        "schema_version": document.get("schema_version", 1),
        "basics": {labels.get(key, key): _node_text(node) for key, node in basics.items() if isinstance(node, dict)},
        "sections": sections,
    }
    return json.dumps(payload, ensure_ascii=False, indent=2) + "\n"


# ---------------------------------------------------------------------------
# Word (.docx) 导出：不依赖第三方库，直接产出最小 OOXML 包。
# 与 Preview / PDF / Markdown 共用同一份 layout_config（accent / font_scale /
# line_height / section_order），保证「同一份版式配置」。
# ---------------------------------------------------------------------------

_CONTENT_TYPES = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">'
    '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>'
    '<Default Extension="xml" ContentType="application/xml"/>'
    '<Override PartName="/word/document.xml" '
    'ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>'
    "</Types>"
)

_ROOT_RELS = (
    '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
    '<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">'
    '<Relationship Id="rId1" '
    'Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" '
    'Target="word/document.xml"/>'
    "</Relationships>"
)


def _docx_paragraph(text: str, *, size_half_pt: int, color: str, bold: bool = False, space_before: int = 0) -> str:
    """构造一个单 run 段落；size 为半磅（Word 单位），color 为 6 位十六进制。"""
    run_props = "<w:rPr>"
    if bold:
        run_props += "<w:b/>"
    run_props += f'<w:color w:val="{color}"/><w:sz w:val="{size_half_pt}"/><w:szCs w:val="{size_half_pt}"/></w:rPr>'
    ppr = f'<w:pPr><w:spacing w:before="{space_before}" w:after="0"/></w:pPr>' if space_before else ""
    return (
        f"<w:p>{ppr}<w:r>{run_props}"
        f'<w:t xml:space="preserve">{_xml_escape(text)}</w:t></w:r></w:p>'
    )


def render_docx(document: dict, layout_config: dict | None = None) -> bytes:
    """Word 导出：读同一份版式配置（accent_color / font_scale / section_order）。"""
    layout = normalize_layout_config(layout_config)
    scale = float(layout["font_scale"])
    accent = str(layout["accent_color"]).lstrip("#").upper() or "111111"
    base_sz = max(16, min(40, int(round(21 * scale))))  # 21 半磅 ≈ 10.5pt 正文
    h1_sz = max(24, min(56, int(round(base_sz * 1.6))))
    h2_sz = max(20, min(44, int(round(base_sz * 1.2))))
    gap = int(layout["section_gap"]) * 12  # twips 近似

    paragraphs: list[str] = []
    basics = _basics(document)
    name = basics.pop("姓名", "")
    if name:
        paragraphs.append(_docx_paragraph(name, size_half_pt=h1_sz, color="111111", bold=True))
    contact = " · ".join(value for value in basics.values() if value)
    if contact:
        paragraphs.append(_docx_paragraph(contact, size_half_pt=base_sz, color="444444"))

    for section_title, entries in _included_entries(document, layout):
        paragraphs.append(_docx_paragraph(section_title, size_half_pt=h2_sz, color=accent, bold=True, space_before=gap))
        for entry in entries:
            heading = _entry_heading(entry)
            if heading:
                paragraphs.append(_docx_paragraph(heading, size_half_pt=base_sz, color="111111", bold=True))
            for bullet in entry["bullets"]:
                paragraphs.append(_docx_paragraph(f"· {bullet}", size_half_pt=base_sz, color="222222"))

    document_xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{''.join(paragraphs)}"
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/></w:sectPr>'
        "</w:body></w:document>"
    )

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", _CONTENT_TYPES)
        archive.writestr("_rels/.rels", _ROOT_RELS)
        archive.writestr("word/document.xml", document_xml)
    return buffer.getvalue()


def render_export(document: dict, format: str, layout_config: dict | None = None) -> tuple[str | bytes, str]:
    """Return (body, media_type) for the requested export format.

    Markdown / txt / json 返回 str；Word(docx) 返回 bytes。
    """
    normalized = (format or "").strip().lower()
    if normalized == "markdown":
        return render_markdown(document, layout_config), "text/markdown; charset=utf-8"
    if normalized == "txt":
        return render_plain_text(document, layout_config), "text/plain; charset=utf-8"
    if normalized == "json":
        return render_json(document, layout_config), "application/json; charset=utf-8"
    if normalized in {"docx", "word"}:
        return (
            render_docx(document, layout_config),
            "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        )
    raise ValueError("format 必须是 markdown、txt、json 或 docx")


__all__ = [
    "render_markdown",
    "render_plain_text",
    "render_json",
    "render_docx",
    "render_export",
]
