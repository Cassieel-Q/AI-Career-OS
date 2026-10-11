from app.resume_studio_export import render_export, render_json, render_markdown, render_plain_text
from app.resume_studio_service import export_checks
from test_resume_studio_document import _mission_with_resume


def _node(text, claim_status="CONFIRMED", risk_level="LOW"):
    return {"id": "n", "text": text, "source_kind": "user_entered", "source_id": None,
            "evidence_refs": [], "risk_level": risk_level, "claim_status": claim_status}


def _document():
    return {
        "schema_version": 1,
        "basics": {"name": _node("Ada Chen"), "phone": _node("13800000000"), "email": _node("ada@example.com"), "location": _node("Shanghai")},
        "sections": [
            {"id": "s1", "kind": "experience", "title": _node("工作与项目经历"),
             "entries": [
                 {"id": "e1", "status": "INCLUDED",
                  "title": _node("Product Intern"), "subtitle": _node("Acme"), "date": _node("2025.01–2025.06"), "location": _node(""),
                  "bullets": [_node("Built evaluation dashboards"), _node("Drove on-time delivery")]},
             ]},
            {"id": "s2", "kind": "skills", "title": _node("技能"),
             "entries": [
                 {"id": "e2", "status": "INCLUDED", "title": _node("Python"), "subtitle": _node("熟练"), "date": _node(""), "location": _node(""), "bullets": []},
                 {"id": "e3", "status": "OMITTED", "title": _node("应省略技能"), "subtitle": _node(""), "date": _node(""), "location": _node(""), "bullets": []},
             ]},
        ],
    }


def test_placeholder_residue_blocks_export():
    doc = _document()
    doc["sections"][0]["entries"][0]["bullets"][0]["text"] = "搭建评测看板【待补：补充量化结果】"
    checks = export_checks(doc)
    hits = [item for item in checks if item["code"] == "placeholder_residue"]
    assert hits
    assert all(item["level"] == "block" for item in hits)
    assert "工作与项目经历" in hits[0]["message"]


def test_plain_text_export_skips_omitted_entries():
    doc = _document()
    body, media = render_export(doc, "txt")
    assert media == "text/plain; charset=utf-8"
    assert "Ada Chen" in body
    assert "Built evaluation dashboards" in body
    assert "应省略技能" not in body
    assert "Python" in body


def test_markdown_export_contains_headers():
    doc = _document()
    body, media = render_export(doc, "markdown")
    assert media == "text/markdown; charset=utf-8"
    assert "# Ada Chen" in body
    assert "## 工作与项目经历" in body
    assert "- Built evaluation dashboards" in body


def test_json_export_is_structured_and_skips_omitted():
    doc = _document()
    body, media = render_export(doc, "json")
    assert media == "application/json; charset=utf-8"
    import json
    data = json.loads(body)
    assert data["basics"]["name"] == "Ada Chen"
    skills = next(item for item in data["sections"] if item["kind"] == "skills")
    assert [entry["title"] for entry in skills["entries"]] == ["Python"]


def test_render_export_rejects_unknown_format():
    doc = _document()
    try:
        render_export(doc, "docx")
    except ValueError as exc:
        assert "markdown" in str(exc)
    else:
        raise AssertionError("expected ValueError for unsupported format")


def test_export_endpoint_serves_text_and_respects_draft(client, db_session):
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio/export"
    markdown = client.get(f"{base}?format=markdown")
    assert markdown.status_code == 200
    assert markdown.headers["content-type"].startswith("text/markdown")
    assert "Ada Chen" in markdown.text
    assert markdown.headers["content-disposition"].startswith("attachment")

    txt = client.get(f"{base}?format=txt")
    assert txt.status_code == 200
    assert txt.headers["content-type"].startswith("text/plain")

    js = client.get(f"{base}?format=json")
    assert js.status_code == 200
    assert js.json()["basics"]["name"] == "Ada Chen"

    unknown = client.get(f"{base}?format=docx")
    assert unknown.status_code == 422
