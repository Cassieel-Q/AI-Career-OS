"""目标五验收：版式配置（单一事实来源）、section_order 同步、HTML 清洗、模板草稿。

- HTML 清洗测试（script/外链/内联事件被移除）
- section_order 同步预览和导出测试
- 模板识别草稿确认测试
"""
import io
import zipfile

from app.resume_layout import (
    DEFAULT_LAYOUT_CONFIG,
    apply_section_order,
    layout_config_from_html,
    normalize_layout_config,
    sanitize_template_html,
)
from app.resume_studio_export import render_docx, render_export, render_markdown


DANGEROUS_HTML = """<!DOCTYPE html>
<html><head>
  <script>alert('x')</script>
  <link rel="stylesheet" href="https://evil.example/x.css">
</head>
<body onload="steal()">
  <div class="page" style="color:#2b6cb0">
    <h1>Resume</h1>
    <img src="javascript:alert(1)">
    <a href="https://evil.example">x</a>
  </div>
</body></html>
"""


def test_sanitize_template_html_removes_scripts_links_events_and_urls():
    cleaned, warnings = sanitize_template_html(DANGEROUS_HTML)
    lowered = cleaned.lower()
    assert "<script" not in lowered
    assert "alert('x')" not in lowered
    assert "<link" not in lowered
    assert "onload" not in lowered
    assert "javascript:" not in cleaned
    assert "https://evil.example" not in cleaned
    # 结构保留（不做语义改写）
    assert "Resume" in cleaned
    assert set(warnings) >= {"removed_script", "removed_external_link", "removed_inline_event"}


def test_normalize_layout_config_is_a_whitelist_with_clamps():
    layout = normalize_layout_config(
        {
            "accent_color": "not-a-color",
            "font_scale": 99,
            "columns": 7,
            "section_order": "skills, experience ,skills",
            "evil": "x",
        }
    )
    assert layout["accent_color"] == DEFAULT_LAYOUT_CONFIG["accent_color"]
    assert layout["font_scale"] == 1.6
    assert layout["columns"] == 2
    assert layout["section_order"] == ["skills", "experience"]
    assert "evil" not in layout
    assert set(layout) == set(DEFAULT_LAYOUT_CONFIG)


def test_apply_section_order_puts_unlisted_sections_last():
    document = {
        "sections": [
            {"id": "a", "kind": "honors"},
            {"id": "b", "kind": "skills"},
            {"id": "c", "kind": "education"},
        ]
    }
    ordered = apply_section_order(document, {"section_order": ["education", "skills"]})
    assert [s["kind"] for s in ordered["sections"]] == ["education", "skills", "honors"]


def test_layout_config_from_html_extracts_accent_and_columns():
    html = "<html><style>.page{color:#ff8800;column-count:2}</style></html>"
    layout = layout_config_from_html(html)
    assert layout["accent_color"] == "#ff8800"
    assert layout["columns"] == 2


def _doc():
    return {
        "schema_version": 1,
        "basics": {"name": {"text": "Ada Chen", "type": "text"}},
        "sections": [
            {"kind": "experience", "title": {"text": "经历"},
             "entries": [{"id": "e1", "status": "INCLUDED", "title": {"text": "Intern"},
                          "subtitle": {"text": "Acme"}, "date": {"text": ""}, "bullets": [{"text": "Built X", "claim_status": "CONFIRMED"}]}]},
            {"kind": "skills", "title": {"text": "技能"},
             "entries": [{"id": "e2", "status": "INCLUDED", "title": {"text": "Python"}, "subtitle": {"text": ""}, "date": {"text": ""}, "bullets": []}]},
        ],
    }


def test_section_order_is_shared_by_markdown_and_docx():
    layout = {"section_order": ["skills", "experience"]}
    md = render_markdown(_doc(), layout)
    assert md.index("## 技能") < md.index("## 经历")
    body, _ = render_export(_doc(), "docx", layout)
    with zipfile.ZipFile(io.BytesIO(bytes(body))) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert xml.index("技能") < xml.index("经历")


def test_docx_uses_accent_color_from_layout():
    body = render_docx(_doc(), {"accent_color": "#ff0000"})
    with zipfile.ZipFile(io.BytesIO(body)) as archive:
        xml = archive.read("word/document.xml").decode("utf-8")
    assert 'w:val="FF0000"' in xml


# ---------------------------------------------------------------------------
# 模板草稿：识别 → 草稿 → 用户确认
# ---------------------------------------------------------------------------


def test_html_template_draft_confirm_flow(client, persisted_profile):
    pid = str(persisted_profile.id)
    created = client.post(
        f"/api/v1/profiles/{pid}/resume-template-drafts/html",
        json={"html": DANGEROUS_HTML, "source_ref": "my-template.html"},
    )
    assert created.status_code == 201
    draft = created.json()
    assert draft["status"] == "DRAFT"
    assert draft["source_kind"] == "HTML"
    assert "removed_script" in draft["warnings"]
    assert "<script" not in (draft["sanitized_html"] or "").lower()

    # 列表能查到
    listed = client.get(f"/api/v1/profiles/{pid}/resume-template-drafts")
    assert listed.status_code == 200
    assert [d["id"] for d in listed.json()] == [draft["id"]]

    # 用户同时改了颜色/栏目顺序 → 归一化落库
    patched = client.patch(
        f"/api/v1/resume-template-drafts/{draft['id']}",
        json={"layout_config": {"accent_color": "#123456", "section_order": ["skills", "education"]}},
    )
    assert patched.status_code == 200
    assert patched.json()["layout_config"]["accent_color"] == "#123456"

    confirmed = client.post(f"/api/v1/resume-template-drafts/{draft['id']}/confirm")
    assert confirmed.status_code == 200
    assert confirmed.json()["status"] == "CONFIRMED"


def test_upload_reference_template_image_marks_manual_review(client, persisted_profile):
    pid = str(persisted_profile.id)
    fake_png = b"\x89PNG\r\n\x1a\n" + b"0" * 32
    res = client.post(
        f"/api/v1/profiles/{pid}/resume-template-drafts/upload",
        files={"file": ("ref.png", fake_png, "image/png")},
    )
    assert res.status_code == 201
    body = res.json()
    assert body["source_kind"] == "IMAGE"
    # 诚实标注：无法在本地做视觉识别，交给用户手动调整
    assert "image_requires_manual_review" in body["warnings"]


def test_set_layout_operation_persists_and_bumps_revision(client, db_session):
    from test_resume_studio_document import _mission_with_resume

    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    read = client.get(base).json()
    revision = read["revision"]

    res = client.patch(
        base,
        json={"type": "set_layout", "layout_config": {"accent_color": "#00ff00", "section_order": ["projects"]}},
        headers={"If-Match": str(revision)},
    )
    assert res.status_code == 200, res.text
    updated = res.json()
    assert updated["revision"] == revision + 1
    assert updated["layout_config"]["accent_color"] == "#00ff00"
    assert updated["layout_config"]["section_order"] == ["projects"]
