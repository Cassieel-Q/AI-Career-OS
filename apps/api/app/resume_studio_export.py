"""Render a Resume Studio document to portable text formats without Typst.

These exports are pure functions over ``document_json``: they never require the
Typst binary or a system font, so a user can always keep a Markdown / plain-text
archive or a structured JSON backup even on machines without the PDF toolchain.
"""
from __future__ import annotations

import json


def _node_text(node: dict | None) -> str:
    if not isinstance(node, dict):
        return ""
    return str(node.get("text") or "").strip()


def _included_entries(document: dict) -> list[tuple[str, list[dict]]]:
    """Return [(section_title, [included entries])] with omitted nodes dropped."""
    result: list[tuple[str, list[dict]]] = []
    for section in document.get("sections") or []:
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


def render_markdown(document: dict) -> str:
    """Markdown export: full fields except photos, suitable for text archival."""
    basics = _basics(document)
    lines: list[str] = []
    name = basics.pop("姓名", "")
    lines.append(f"# {name}".strip())
    contact = " · ".join(value for value in basics.values() if value)
    if contact:
        lines.append("")
        lines.append(contact)
    for section_title, entries in _included_entries(document):
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


def render_plain_text(document: dict) -> str:
    """Plain-text export: the simplest archive with no Markdown markup."""
    basics = _basics(document)
    lines: list[str] = []
    name = basics.pop("姓名", "")
    if name:
        lines.append(name)
    contact = " · ".join(value for value in basics.values() if value)
    if contact:
        lines.append(contact)
    for section_title, entries in _included_entries(document):
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


def render_json(document: dict) -> str:
    """JSON export: structured backup for later processing (photos excluded)."""
    basics = document.get("basics") or {}
    labels = {"name": "name", "phone": "phone", "email": "email", "location": "location"}
    sections: list[dict[str, object]] = []
    for section in document.get("sections") or []:
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


def render_export(document: dict, format: str) -> tuple[str, str]:
    """Return (body, media_type) for the requested export format."""
    normalized = (format or "").strip().lower()
    if normalized == "markdown":
        return render_markdown(document), "text/markdown; charset=utf-8"
    if normalized == "txt":
        return render_plain_text(document), "text/plain; charset=utf-8"
    if normalized == "json":
        return render_json(document), "application/json; charset=utf-8"
    raise ValueError("format 必须是 markdown、txt 或 json")
