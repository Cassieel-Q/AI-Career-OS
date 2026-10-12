"""版式配置单一事实来源（目标五）。

Preview / PDF / Word / Markdown 统一读同一份 `layout_config`：
- 预览与 PDF：由 Typst 模板 + 文档 sections 顺序渲染；
- Word / Markdown：由导出模块读同一份配置。

本模块负责：默认值、归一化、section_order 应用到文档、模板视觉覆盖、以及 HTML 清洗。
"""
from __future__ import annotations

import re

DEFAULT_LAYOUT_CONFIG: dict = {
    "template": "zh-classic",
    "page_limit": 1,
    "font_scale": 1.0,
    "line_height": 1.5,
    "section_gap": 12,
    "columns": 1,
    "accent_color": "#111111",
    "photo_enabled": False,
    "section_order": ["education", "experience", "projects", "honors", "skills"],
}

_ALLOWED_KEYS = tuple(DEFAULT_LAYOUT_CONFIG.keys())
_HEX_COLOR_RE = re.compile(r"^#[0-9a-fA-F]{6}$")

# 清洗 HTML 模板：脚本、外部资源、内联事件一律移除。
_SCRIPT_RE = re.compile(r"<\s*(script|iframe|object|embed)\b.*?<\s*/\s*\1\s*>", re.IGNORECASE | re.DOTALL)
_SCRIPT_SELF_RE = re.compile(r"<\s*(script|iframe|object|embed)\b[^>]*/?>", re.IGNORECASE)
_LINK_RE = re.compile(r"<\s*link\b[^>]*>", re.IGNORECASE)
_EVENT_ATTR_RE = re.compile(r"\son[a-zA-Z]+\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s>]+)", re.IGNORECASE)
_JS_URL_RE = re.compile(r"(href|src)\s*=\s*(\"|')\s*javascript:[^\"']*(\"|')", re.IGNORECASE)
_HTTP_URL_RE = re.compile(r"(href|src)\s*=\s*(\"|')\s*https?://[^\"']*(\"|')", re.IGNORECASE)


def normalize_layout_config(raw: dict | None) -> dict:
    """把任意输入归一化成受控的版式配置（含默认值补齐与类型校正）。"""
    data = dict(DEFAULT_LAYOUT_CONFIG)
    if isinstance(raw, dict):
        for key in _ALLOWED_KEYS:
            if key in raw and raw[key] is not None:
                data[key] = raw[key]

    data["template"] = str(data.get("template") or DEFAULT_LAYOUT_CONFIG["template"])[:64]
    data["page_limit"] = _int_in(data.get("page_limit"), 1, 1, 5)
    data["font_scale"] = _float_in(data.get("font_scale"), 1.0, 0.6, 1.6)
    data["line_height"] = _float_in(data.get("line_height"), 1.5, 1.0, 2.5)
    data["section_gap"] = _int_in(data.get("section_gap"), 12, 0, 48)
    data["columns"] = _int_in(data.get("columns"), 1, 1, 2)
    data["photo_enabled"] = bool(data.get("photo_enabled"))
    accent = str(data.get("accent_color") or DEFAULT_LAYOUT_CONFIG["accent_color"]).strip()
    data["accent_color"] = accent if _HEX_COLOR_RE.match(accent) else DEFAULT_LAYOUT_CONFIG["accent_color"]

    order = data.get("section_order")
    if isinstance(order, str):
        order = [part.strip() for part in order.split(",")]
    if not isinstance(order, list):
        order = list(DEFAULT_LAYOUT_CONFIG["section_order"])
    cleaned_order = [str(item).strip().lower() for item in order if str(item).strip()]
    data["section_order"] = list(dict.fromkeys(cleaned_order)) or list(DEFAULT_LAYOUT_CONFIG["section_order"])
    return data


def _int_in(value: object, default: int, low: int, high: int) -> int:
    try:
        number = int(float(str(value)))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, number))


def _float_in(value: object, default: float, low: float, high: float) -> float:
    try:
        number = float(str(value))
    except (TypeError, ValueError):
        return default
    return max(low, min(high, round(number, 2)))


# ---------------------------------------------------------------------------
# 应用到文档 / 模板
# ---------------------------------------------------------------------------


def apply_section_order(document: dict, layout_config: dict | None) -> dict:
    """按 section_order 重排文档 sections；未列出的 section 保持相对顺序排在最后。"""
    layout = normalize_layout_config(layout_config)
    order = layout["section_order"]
    sections = list((document or {}).get("sections") or [])
    if not sections:
        return dict(document or {})

    def sort_key(section: dict) -> tuple[int, int]:
        kind = str(section.get("kind") or section.get("id") or "").strip().lower()
        try:
            return (order.index(kind), 0)
        except ValueError:
            return (len(order), 0)

    reordered = sorted(sections, key=sort_key)
    result = dict(document or {})
    result["sections"] = reordered
    return result


def apply_layout_to_template(template: dict, layout_config: dict | None) -> dict:
    """把版式配置映射到 Typst 模板字段（accent 等）。未知键会被 Typst 忽略。"""
    layout = normalize_layout_config(layout_config)
    merged = dict(template or {})
    merged["accent"] = layout["accent_color"]
    merged["font_scale"] = layout["font_scale"]
    merged["line_height"] = layout["line_height"]
    merged["section_gap"] = layout["section_gap"]
    merged["columns"] = layout["columns"]
    merged["photo_enabled"] = layout["photo_enabled"]
    return merged


# ---------------------------------------------------------------------------
# HTML 模板清洗
# ---------------------------------------------------------------------------


def sanitize_template_html(html: str) -> tuple[str, list[str]]:
    """清洗 HTML 模板，返回 (安全 HTML, warnings)。

    - 移除 script/iframe/object/embed 与外部 <link>；
    - 移除内联事件（on*）与 javascript: / http(s): 外链；
    - 不做语义改写，只做移除。
    """
    warnings: list[str] = []
    text = html or ""
    if _SCRIPT_RE.search(text) or _SCRIPT_SELF_RE.search(text):
        warnings.append("removed_script")
    text = _SCRIPT_RE.sub("", text)
    text = _SCRIPT_SELF_RE.sub("", text)
    if _LINK_RE.search(text):
        warnings.append("removed_external_link")
    text = _LINK_RE.sub("", text)
    if _EVENT_ATTR_RE.search(text):
        warnings.append("removed_inline_event")
    text = _EVENT_ATTR_RE.sub("", text)
    if _JS_URL_RE.search(text):
        warnings.append("removed_javascript_url")
    text = _JS_URL_RE.sub(r'\1="#"', text)
    if _HTTP_URL_RE.search(text):
        warnings.append("removed_external_url")
    text = _HTTP_URL_RE.sub(r'\1="#"', text)
    return text, warnings


def layout_config_from_html(html: str) -> dict:
    """从 HTML 模板里粗提取版式线索（accent 颜色、分栏），形成草稿配置。"""
    layout = dict(DEFAULT_LAYOUT_CONFIG)
    cleaned, _ = sanitize_template_html(html)
    color_match = re.search(r"#[0-9a-fA-F]{6}", cleaned)
    if color_match:
        layout["accent_color"] = color_match.group(0)
    if re.search(r"column-?count\s*:\s*2|grid-template-columns\s*:\s*1fr\s+1fr", cleaned, re.IGNORECASE):
        layout["columns"] = 2
    return normalize_layout_config(layout)


__all__ = [
    "DEFAULT_LAYOUT_CONFIG",
    "normalize_layout_config",
    "apply_section_order",
    "apply_layout_to_template",
    "sanitize_template_html",
    "layout_config_from_html",
]
