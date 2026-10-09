from copy import deepcopy
from pathlib import Path

import fitz
import pytest

from app.resume_studio_render import render_document, skill_category, typst_binary
from app.resume_studio_templates import list_templates
from app.resume_studio_service import get_or_create_document
from test_resume_studio_document import _mission_with_resume


@pytest.fixture(autouse=True)
def require_typst(monkeypatch):
    binary = Path(__file__).resolve().parents[3] / ".runtime" / "typst-0.15.1" / "typst-x86_64-pc-windows-msvc" / "typst.exe"
    if binary.exists():
        monkeypatch.setenv("TYPST_BIN", str(binary))
    if typst_binary() is None:
        pytest.skip("Typst 0.15.1 is not installed")


def test_catalog_has_nine_real_templates_per_language():
    templates = list_templates()
    assert len(templates) == 18
    assert len({item["id"] for item in templates}) == 18
    assert sum(item["language"] == "zh" for item in templates) == 9
    assert sum(item["language"] == "en" for item in templates) == 9
    assert all(item["spdx"] == "LicenseRef-AICareerOS-Original" for item in templates)


def test_ai_skill_takes_precedence_over_product_wording():
    assert skill_category("LLM 需求分析") == "ai"


def test_every_template_renders_all_pages_as_real_pdf_and_svg(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    original = get_or_create_document(db_session, mission.id).document_json
    for template in list_templates():
        document = deepcopy(original)
        if template["language"] == "en":
            document["sections"][0]["title"]["text"] = "Education"
            document["sections"][1]["title"]["text"] = "Experience"
            document["sections"][2]["title"]["text"] = "Skills"
            document["sections"][3]["title"]["text"] = "Certificates"
        result = render_document(document, template["id"])
        pdf = fitz.open(stream=result.pdf, filetype="pdf")
        assert result.pdf.startswith(b"%PDF-"), template["id"]
        assert result.page_count == len(pdf) == len(result.pages), template["id"]
        assert all(svg.lstrip().startswith("<svg") for svg in result.pages), template["id"]
        assert "Ada Chen" in "".join(page.get_text() for page in pdf), template["id"]
        assert any(item["id"] == document["basics"]["name"]["id"] for item in result.layout_map), template["id"]


def test_two_resumes_render_different_selectable_text(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    first = get_or_create_document(db_session, mission.id).document_json
    second = deepcopy(first)
    second["basics"]["name"]["text"] = "Grace Lin"
    a = render_document(first, "zh-classic")
    b = render_document(second, "zh-classic")
    assert a.pdf != b.pdf
    assert "Grace Lin" in fitz.open(stream=b.pdf, filetype="pdf")[0].get_text()


def test_skills_render_as_compact_categorized_paragraph(db_session):
    from app.resume_studio_service import _entry, _node, _section
    from uuid import uuid4

    mission, _, _ = _mission_with_resume(db_session)
    document = deepcopy(get_or_create_document(db_session, mission.id).document_json)
    names = ["需求分析", "PRD 撰写", "LLM", "Prompt Engineering", "Codex", "Python", "CET-6"]
    document["sections"][2] = _section("skills", "专业技能", [
        _entry(uuid4(), title=_node(name, source_kind="profile"), subtitle=_node("", source_kind="system"),
               date=_node("", source_kind="system"), location=_node("", source_kind="system"), bullets=[])
        for name in names
    ])
    pdf = fitz.open(stream=render_document(document, "zh-classic").pdf, filetype="pdf")
    text = "".join(page.get_text() for page in pdf)
    compact_text = "".join(text.split())
    assert all("".join(label.split()) in compact_text for label in ("产品能力", "AI 产品能力", "技术与工具", "语言能力"))
    assert all(name in text for name in names)
    assert len(pdf) == 1
