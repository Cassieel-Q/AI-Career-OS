from pathlib import Path

import pytest

from test_resume_studio_document import _mission_with_resume


@pytest.fixture(autouse=True)
def configure_typst(monkeypatch):
    binary = Path(__file__).resolve().parents[3] / ".runtime" / "typst-0.15.1" / "typst-x86_64-pc-windows-msvc" / "typst.exe"
    if binary.exists():
        monkeypatch.setenv("TYPST_BIN", str(binary))


def test_preview_and_pdf_are_same_revision_and_real_bytes(client, db_session):
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    doc = client.get(base).json()
    templates = client.get("/api/v1/resume-studio/templates")
    assert templates.status_code == 200
    assert len(templates.json()) == 18
    sample = client.get(templates.json()[0]["sample_preview_url"])
    assert sample.status_code == 200
    assert sample.json()["pages"][0].startswith("<svg")

    preview = client.post(f"{base}/preview", json={"revision": doc["revision"]})
    assert preview.status_code == 200
    assert preview.json()["page_count"] >= 1
    assert len(preview.json()["pages"]) == preview.json()["page_count"]
    assert any(item["id"] == doc["document"]["basics"]["name"]["id"] for item in preview.json()["layout_map"])

    confirmed = client.post(f"{base}/confirm", headers={"If-Match": "1"})
    assert confirmed.status_code == 200
    assert confirmed.json()["confirmed_revision"] == 1
    pdf = client.get(f"{base}/pdf")
    assert pdf.status_code == 200
    assert pdf.content.startswith(b"%PDF-")
    assert "attachment" in pdf.headers["content-disposition"]
    assert "filename*=UTF-8''" in pdf.headers["content-disposition"]


def test_placeholder_blocks_confirmation_and_edit_invalidates_pdf(client, db_session):
    """「事实核对」已下线：未核对的量化要点只提示；真正拦门的只剩占位残留。"""
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    doc = client.get(base).json()
    entry = next(section for section in doc["document"]["sections"] if section["kind"] == "experience")["entries"][0]

    added = client.patch(base, headers={"If-Match": "1"}, json={"type": "add_bullet", "entry_id": entry["id"], "text": "Raised conversion 37%"})
    assert added.status_code == 200
    bullet = next(section for section in added.json()["document"]["sections"] if section["kind"] == "experience")["entries"][0]["bullets"][-1]
    assert bullet["claim_status"] == "NEEDS_CONFIRMATION"

    # 未核对事实不再拦截确认
    assert client.post(f"{base}/confirm", headers={"If-Match": "2"}).status_code == 200
    assert client.get(f"{base}/pdf").status_code == 200

    # 正文残留占位标记仍然拦截
    edited = client.patch(base, headers={"If-Match": "2"}, json={"type": "set_text", "node_id": bullet["id"], "text": "负责数据看板【待补：量化结果】"})
    assert edited.status_code == 200
    blocked = client.post(f"{base}/confirm", headers={"If-Match": "3"})
    assert blocked.status_code == 409
    assert any(item["code"] == "placeholder_residue" for item in blocked.json()["detail"]["checks"])

    # 补全后可确认；再次编辑会作废已确认修订版，PDF 重新 409
    fixed = client.patch(base, headers={"If-Match": "3"}, json={"type": "set_text", "node_id": bullet["id"], "text": "Raised conversion 37%"})
    assert fixed.status_code == 200
    assert client.post(f"{base}/confirm", headers={"If-Match": "4"}).status_code == 200
    assert client.get(f"{base}/pdf").status_code == 200
    assert client.patch(base, headers={"If-Match": "4"}, json={"type": "set_text", "node_id": bullet["id"], "text": "Revised text"}).status_code == 200
    assert client.get(f"{base}/pdf").status_code == 409


def test_new_entry_with_missing_date_warns_but_does_not_block(client, db_session):
    """缺日期的条目只出提示（warn），不再拦截确认。"""
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    doc = client.get(base).json()
    section = next(item for item in doc["document"]["sections"] if item["kind"] == "experience")
    added = client.patch(base, headers={"If-Match": "1"}, json={"type": "add_entry", "section_id": section["id"], "title": "New role"})
    assert added.status_code == 200
    entry = next(item for item in added.json()["document"]["sections"] if item["id"] == section["id"])["entries"][-1]
    assert entry["date"]["claim_status"] == "BLOCKED_MISSING"

    preview = client.post(f"{base}/preview", json={"revision": 2})
    assert preview.status_code == 200
    hits = [item for item in preview.json()["checks"] if item.get("node_id") == entry["date"]["id"]]
    assert hits
    assert all(item["level"] == "warn" and item["code"] == "unconfirmed_fact" for item in hits)

    assert client.post(f"{base}/confirm", headers={"If-Match": "2"}).status_code == 200
