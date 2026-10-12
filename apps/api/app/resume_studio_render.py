"""Validated Resume Studio data to real Typst PDF, SVG pages and click targets."""
from __future__ import annotations

from collections import OrderedDict
from copy import deepcopy
from dataclasses import dataclass
from hashlib import sha256
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from threading import Lock

import fitz

from .resume_studio_templates import get_template

_SOURCE = Path(__file__).parent / "resume_studio_typst" / "base.typ"
_FONT_PROFILE = "Microsoft YaHei|Noto Sans CJK SC|Libertinus Sans|Arial"
_TEMPLATE_VERSION = "1.0.0"
_CACHE: OrderedDict[str, "RenderResult"] = OrderedDict()
_CACHE_GUARD = Lock()
_KEY_LOCKS: dict[str, Lock] = {}

_SKILL_CATEGORIES = (
    ("language", "语言能力", ("英语", "english", "cet", "雅思", "托福", "ielts", "toefl", "六级", "四级")),
    ("ai", "AI 产品能力", ("llm", "prompt", "agent", "rag", "skill", "模型", "人机协同", "ai 工作流", "ai产品", "ai 产品")),
    ("product", "产品能力", ("需求", "竞品", "prd", "原型", "figma", "axure", "流程", "验收", "迭代", "交互", "用户")),
    ("tools", "技术与工具", ("codex", "cursor", "git", "python", "typescript", "javascript", "sql", "api", "react", "expo", "fastapi", "next.js")),
)


def skill_category(name: str) -> str:
    lowered = name.casefold()
    for key, _, terms in _SKILL_CATEGORIES:
        if any(term in lowered for term in terms):
            return key
    return "other"


def _prepare_render_document(document: dict) -> dict:
    prepared = deepcopy(document)
    for section in prepared.get("sections") or []:
        if section.get("kind") == "skills":
            for entry in section.get("entries") or []:
                entry["skill_category"] = skill_category(entry.get("title", {}).get("text", ""))
    return prepared


class ResumeRenderError(RuntimeError):
    pass


@dataclass(frozen=True)
class RenderResult:
    pdf: bytes
    pages: list[str]
    layout_map: list[dict]
    page_count: int


def typst_binary() -> Path | None:
    configured = os.environ.get("TYPST_BIN")
    if configured and Path(configured).is_file():
        return Path(configured)
    discovered = shutil.which("typst")
    if discovered:
        return Path(discovered)
    local = Path(__file__).resolve().parents[3] / ".runtime" / "typst-0.15.1" / "typst-x86_64-pc-windows-msvc" / "typst.exe"
    return local if local.is_file() else None


def _run(binary: Path, args: list[str], cwd: Path) -> str:
    try:
        result = subprocess.run(
            [str(binary), *args],
            cwd=cwd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=15,
            check=False,
        )
    except subprocess.TimeoutExpired as exc:
        raise ResumeRenderError("Typst 排版超时，请缩短内容后重试。") from exc
    if result.returncode != 0:
        raise ResumeRenderError((result.stderr or result.stdout or "Typst 排版失败。")[:2_000])
    return result.stdout


def _pt(value: object) -> float:
    try:
        return float(str(value).replace("pt", ""))
    except ValueError:
        return 0.0


def _layout_map(binary: Path, cwd: Path, page_widths: list[float]) -> list[dict]:
    expression = "query(metadata).map(it => (id: it.value, page: it.location().page(), x: it.location().position().x, y: it.location().position().y))"
    try:
        output = _run(binary, ["eval", expression, "--in", "main.typ", "--format", "json", "--root", str(cwd)], cwd)
        anchors = json.loads(output)
    except (ResumeRenderError, json.JSONDecodeError):
        return []
    items = []
    for anchor in anchors:
        page = int(anchor.get("page") or 0)
        if not 1 <= page <= len(page_widths):
            continue
        items.append({
            "id": str(anchor.get("id") or ""),
            "page": page,
            "x": round(_pt(anchor.get("x")), 2),
            "y": round(_pt(anchor.get("y")), 2),
            "width": 0.0,
            "height": 15.0,
        })
    items.sort(key=lambda item: (item["page"], item["y"], item["x"]))
    for index, item in enumerate(items):
        width = page_widths[item["page"] - 1] - 42 - item["x"]
        for following in items[index + 1:]:
            if following["page"] != item["page"] or following["y"] - item["y"] > 6:
                break
            if following["x"] > item["x"]:
                width = min(width, following["x"] - item["x"] - 2)
        item["width"] = round(max(18, width), 2)
    return items


def _render_uncached(document: dict, template: dict, binary: Path) -> RenderResult:
    with tempfile.TemporaryDirectory(prefix="ai-career-resume-") as directory:
        cwd = Path(directory)
        shutil.copy2(_SOURCE, cwd / "main.typ")
        (cwd / "resume.json").write_text(json.dumps(_prepare_render_document(document), ensure_ascii=False), encoding="utf-8")
        (cwd / "template.json").write_text(json.dumps(template, ensure_ascii=False), encoding="utf-8")
        _run(binary, ["compile", "--root", str(cwd), "main.typ", "resume.pdf"], cwd)
        _run(binary, ["compile", "--root", str(cwd), "main.typ", "page-{0p}.svg"], cwd)
        pdf = (cwd / "resume.pdf").read_bytes()
        with fitz.open(stream=pdf, filetype="pdf") as reader:
            page_count = len(reader)
            widths = [page.rect.width for page in reader]
        pages = []
        for path in sorted(cwd.glob("page-*.svg")):
            svg = path.read_text(encoding="utf-8")
            pages.append(svg[svg.find("<svg"):])
        if page_count == 0 or len(pages) != page_count:
            raise ResumeRenderError("预览页数与 PDF 页数不一致。")
        return RenderResult(pdf=pdf, pages=pages, layout_map=_layout_map(binary, cwd, widths), page_count=page_count)


def render_document(document: dict, template_id: str, layout_config: dict | None = None) -> RenderResult:
    # 版式配置为单一事实来源：预览与 PDF 使用同一份 layout_config（目标五）。
    from .resume_layout import apply_layout_to_template, apply_section_order, normalize_layout_config

    layout = normalize_layout_config(layout_config) if layout_config else None
    if layout is not None:
        document = apply_section_order(document, layout)
    template = get_template(template_id)
    if layout is not None:
        template = apply_layout_to_template(template, layout)
    binary = typst_binary()
    if binary is None:
        raise ResumeRenderError("未找到 Typst 0.15.1。请安装 Typst 并设置 TYPST_BIN。")
    payload = json.dumps({
        "document": document, "template": template,
        "template_version": _TEMPLATE_VERSION,
        "binary": str(binary), "binary_mtime": binary.stat().st_mtime_ns,
        "source": _SOURCE.stat().st_mtime_ns,
        "fonts": _FONT_PROFILE, "font_paths": os.environ.get("TYPST_FONT_PATHS", ""),
    }, sort_keys=True, ensure_ascii=False)
    key = sha256(payload.encode("utf-8")).hexdigest()
    with _CACHE_GUARD:
        cached = _CACHE.get(key)
        if cached:
            _CACHE.move_to_end(key)
            return cached
        lock = _KEY_LOCKS.setdefault(key, Lock())
    with lock:
        with _CACHE_GUARD:
            cached = _CACHE.get(key)
            if cached:
                return cached
        rendered = _render_uncached(document, template, binary)
        with _CACHE_GUARD:
            _CACHE[key] = rendered
            _CACHE.move_to_end(key)
            while len(_CACHE) > 64:
                _CACHE.popitem(last=False)
            _KEY_LOCKS.pop(key, None)
        return rendered
