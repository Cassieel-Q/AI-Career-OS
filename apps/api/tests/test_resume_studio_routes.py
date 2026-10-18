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


def test_unconfirmed_high_risk_fact_blocks_final_confirmation(client, db_session):
    """指令 4.1：未经核实的高风险事实必须阻止正式投递版确认，但草稿仍可导出。"""
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    doc = client.get(base).json()
    entry = next(section for section in doc["document"]["sections"] if section["kind"] == "experience")["entries"][0]

    added = client.patch(base, headers={"If-Match": "1"}, json={"type": "add_bullet", "entry_id": entry["id"], "text": "Raised conversion 37%"})
    assert added.status_code == 200
    bullet = next(section for section in added.json()["document"]["sections"] if section["kind"] == "experience")["entries"][0]["bullets"][-1]
    assert bullet["claim_status"] == "NEEDS_CONFIRMATION"

    # 草稿随时可以导出审阅
    assert client.get(f"{base}/pdf?draft=1").status_code == 200
    # 但正式投递版确认必须被拦下
    blocked = client.post(f"{base}/confirm", headers={"If-Match": "2"})
    assert blocked.status_code == 409
    assert any(item["code"] == "unconfirmed_fact" and item.get("high_risk") for item in blocked.json()["detail"]["checks"])

    # 正文残留占位标记在两种口径下都拦
    edited = client.patch(base, headers={"If-Match": "2"}, json={"type": "set_text", "node_id": bullet["id"], "text": "负责数据看板【待补：量化结果】"})
    assert edited.status_code == 200
    blocked_placeholder = client.post(f"{base}/confirm", headers={"If-Match": "3"})
    assert blocked_placeholder.status_code == 409
    assert any(item["code"] == "placeholder_residue" for item in blocked_placeholder.json()["detail"]["checks"])

    # 改写不等于核对：改掉数字后仍未「显式确认」，正式投递版依旧拦下
    fixed = client.patch(base, headers={"If-Match": "3"}, json={"type": "set_text", "node_id": bullet["id"], "text": "负责数据看板的设计与验证"})
    assert fixed.status_code == 200
    still_blocked = client.post(f"{base}/confirm", headers={"If-Match": "4"})
    assert still_blocked.status_code == 409
    assert any(item["code"] == "unconfirmed_fact" and item.get("high_risk") for item in still_blocked.json()["detail"]["checks"])

    # 只有显式确认事实之后才能生成正式投递版
    confirmed = client.patch(base, headers={"If-Match": "4"}, json={"type": "confirm_fact", "node_id": bullet["id"]})
    assert confirmed.status_code == 200
    assert client.post(f"{base}/confirm", headers={"If-Match": "5"}).status_code == 200
    assert client.get(f"{base}/pdf").status_code == 200
    # 已确认修订版再次被编辑后作废，正式 PDF 重新 409
    assert client.patch(base, headers={"If-Match": "5"}, json={"type": "set_text", "node_id": bullet["id"], "text": "Revised text"}).status_code == 200
    assert client.get(f"{base}/pdf").status_code == 409


def test_draft_and_final_pdf_are_distinguishable(client, db_session):
    """指令 4.2：草稿 PDF 带 DRAFT 标记与 _DRAFT 文件名，且不会被当作投递版。"""
    import fitz

    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"

    # 未确认前：草稿可导出，正式投递版必须先确认
    assert client.get(f"{base}/pdf").status_code == 409
    draft = client.get(f"{base}/pdf?draft=1")
    assert draft.status_code == 200
    assert draft.content.startswith(b"%PDF-")
    assert draft.headers["X-Resume-Draft"] == "1"
    draft_name = draft.headers["X-Resume-Filename"]
    assert "_DRAFT" in draft_name and draft_name.endswith("_v1_DRAFT.pdf")

    assert client.post(f"{base}/confirm", headers={"If-Match": "1"}).status_code == 200
    final = client.get(f"{base}/pdf")
    assert final.status_code == 200
    assert final.headers["X-Resume-Draft"] == "0"
    assert final.headers["X-Resume-Filename"].endswith("_v1.pdf")

    # 草稿正文必须留下可辨认的草稿标记
    with fitz.open(stream=draft.content, filetype="pdf") as document:
        text = "".join(page.get_text() for page in document)
    assert "DRAFT" in text
    with fitz.open(stream=final.content, filetype="pdf") as document:
        final_text = "".join(page.get_text() for page in document)
    assert "DRAFT" not in final_text
    assert draft.content != final.content


def test_new_entry_with_missing_date_is_a_blocking_gap_for_final(client, db_session):
    """缺日期属于「重大缺失」：草稿口径只提示，正式投递版必须拦下。"""
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
    # 草稿口径：只提示
    hits = [item for item in preview.json()["checks"] if item.get("node_id") == entry["date"]["id"]]
    assert hits
    assert all(item["level"] == "warn" and item["code"] == "unconfirmed_fact" for item in hits)
    # 正式口径：阻塞
    final_hits = [item for item in preview.json()["final_checks"] if item.get("node_id") == entry["date"]["id"]]
    assert final_hits and all(item["level"] == "block" for item in final_hits)

    blocked = client.post(f"{base}/confirm", headers={"If-Match": "2"})
    assert blocked.status_code == 409
    assert client.get(f"{base}/pdf?draft=1").status_code == 200

    # 补上日期只是「填写」，还需显式确认后才能真正进入正式投递版
    filled = client.patch(base, headers={"If-Match": "2"}, json={"type": "set_text", "node_id": entry["date"]["id"], "text": "2024.03 - 2024.09"})
    assert filled.status_code == 200
    assert client.post(f"{base}/confirm", headers={"If-Match": "3"}).status_code == 409

    for node in (entry["title"], entry["date"]):
        attested = client.patch(base, headers={"If-Match": str(filled.json()["revision"])}, json={"type": "confirm_fact", "node_id": node["id"]})
        assert attested.status_code == 200
        filled = attested
    assert client.post(f"{base}/confirm", headers={"If-Match": str(filled.json()["revision"])}).status_code == 200
