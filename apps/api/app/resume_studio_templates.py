"""Static, original Typst template catalog."""
from __future__ import annotations

import json
from pathlib import Path

from fastapi import HTTPException

_CATALOG = json.loads((Path(__file__).parent / "resume_studio_typst" / "templates.json").read_text(encoding="utf-8"))
_BY_ID = {item["id"]: item for item in _CATALOG}


def list_templates() -> list[dict]:
    return [{
        **item,
        "author": "AI Career OS",
        "source_version": "1.0.0",
        "runtime_version": "Typst 0.15.1",
        "font_profile": ["Microsoft YaHei", "Noto Sans CJK SC", "Libertinus Sans", "Arial"],
        "font_license": "system-dependent; fonts are not redistributed",
    } for item in _CATALOG]


def get_template(template_id: str) -> dict:
    try:
        return dict(_BY_ID[template_id])
    except KeyError as exc:
        raise HTTPException(404, "模板不存在。") from exc
