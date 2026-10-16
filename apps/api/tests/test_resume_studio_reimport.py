from app import models
from app.resume_studio_service import get_or_create_document
from test_resume_studio_document import _mission_with_resume


def test_new_confirmed_source_requires_explicit_reimport(client, db_session):
    mission, experience, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    first = client.get(base).json()
    original_source = first["source_target_resume_id"]
    new_resume = models.TargetResume(mission_id=mission.id, version=2, status="CONFIRMED", recommended_experience_order=[str(experience.id)])
    db_session.add(new_resume)
    db_session.flush()
    db_session.add(models.TargetResumeBullet(
        target_resume_id=new_resume.id,
        source_experience_id=experience.id,
        original_text="New evidence",
        suggested_text="Built a newer evidence dashboard",
        final_text="Built a newer evidence dashboard",
        reason="New approved rewrite",
        evidence_refs=[str(experience.id)],
        status="ACCEPTED", sort_order=0,
    ))
    db_session.commit()

    unchanged = client.get(base).json()
    assert unchanged["source_target_resume_id"] == original_source
    difference = client.get(f"{base}/source-diff")
    assert difference.status_code == 200
    assert difference.json()["update_available"] is True
    assert "Built a newer evidence dashboard" in difference.json()["added_bullets"]
    assert "Built product evaluation dashboards" in difference.json()["removed_bullets"]

    assert client.post(f"{base}/reimport", headers={"If-Match": "0"}).status_code == 409
    imported = client.post(f"{base}/reimport", headers={"If-Match": "1"})
    assert imported.status_code == 200
    assert imported.json()["revision"] == 2
    assert imported.json()["source_target_resume_id"] == str(new_resume.id)
    assert imported.json()["confirmed_revision"] is None
    assert client.get(f"{base}/source-diff").json()["update_available"] is False


def test_source_diff_reports_sections_and_manual_edits(client, db_session):
    """差异确认弹窗的数据契约：按板块给新增/删除/修改/不变，并列出会被替换的人工编辑。"""
    mission, experience, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"

    # 用户先在 Studio 里手工新增一条要点（会被更新替换，必须被明确提示）
    from app.resume_studio_schemas import StudioOperation

    first = client.get(base).json()
    section_id = first["document"]["sections"][0]["id"]
    added = client.patch(base, json={"type": "add_bullet", "entry_id": first["document"]["sections"][0]["entries"][0]["id"], "text": "手工补充的要点"}, headers={"If-Match": str(first["revision"])})
    assert added.status_code == 200, added.text
    manual_revision = added.json()["revision"]

    new_resume = models.TargetResume(mission_id=mission.id, version=3, status="CONFIRMED", recommended_experience_order=[str(experience.id)])
    db_session.add(new_resume)
    db_session.flush()
    db_session.add(models.TargetResumeBullet(
        target_resume_id=new_resume.id,
        source_experience_id=experience.id,
        original_text="New evidence",
        suggested_text="Built a v3 evidence dashboard",
        final_text="Built a v3 evidence dashboard",
        reason="v3 rewrite",
        evidence_refs=[str(experience.id)],
        status="ACCEPTED", sort_order=0,
    ))
    db_session.commit()

    diff = client.get(f"{base}/source-diff").json()
    assert diff["update_available"] is True
    assert diff["manual_edit_count"] >= 1
    assert any("手工补充的要点" in text for text in diff["manual_edit_samples"])
    assert diff["sections"], "必须返回板块级差异"
    statuses = {item["status"] for item in diff["sections"]}
    assert statuses & {"changed", "added", "removed", "unchanged"}
    # 板块级统计必须是真实条数，不能恒为 0（曾经把 section 当成 document 传参，导致全 0）
    counted = sum(len(item["added"]) + len(item["removed"]) + item["kept"] for item in diff["sections"])
    assert counted > 0, "板块差异必须统计出真实条目数"
    assert sum(len(item["added"]) for item in diff["sections"]) > 0, "新版新增要点必须归属到具体板块"

    # 修订冲突：带着过期修订号请求 → 409，响应里带最新版本
    stale = client.post(f"{base}/reimport", headers={"If-Match": str(manual_revision - 1)})
    assert stale.status_code == 409
    assert "latest" in stale.json()["detail"]

    ok = client.post(f"{base}/reimport", headers={"If-Match": str(manual_revision)})
    assert ok.status_code == 200
    body = ok.json()
    assert body["revision"] == manual_revision + 1
    assert body["confirmed_revision"] is None


def test_confirm_target_resume_with_zero_accepted_bullets_is_rejected(client, db_session):
    """防呆：没有任何被接受要点时确认投递版必须 409，不能生成空白经历的简历。"""
    from app.mission_service import confirm_target_resume

    mission, _experience, _resume = _mission_with_resume(db_session)
    empty_resume = models.TargetResume(mission_id=mission.id, version=9, status="DRAFT")
    db_session.add(empty_resume)
    db_session.flush()
    db_session.add(models.TargetResumeBullet(
        target_resume_id=empty_resume.id,
        source_experience_id=None,
        original_text="草案",
        suggested_text="项目草案：合成项目内容",
        reason="synthetic",
        risk_flags=["SYNTHETIC_PROJECT"],
        status="SUGGESTED", sort_order=0,
    ))
    db_session.commit()
    try:
        confirm_target_resume(db_session, mission.id)
        raised = None
    except Exception as exc:
        raised = exc
    assert raised is not None, "零接受要点时必须报错"
    assert "409" in str(raised) or "接受" in str(getattr(raised, "detail", ""))


def test_section_breakdown_counts_real_bullets():
    """板块差异必须逐板块统计真实条数：新增/删除/保留都要能算出来。"""
    from app.resume_studio_service import _section_breakdown

    def doc(*sections):
        return {"sections": list(sections)}

    def section(title, texts, omitted_entry=False):
        return {
            "title": {"text": title},
            "entries": [
                {
                    "status": "OMITTED" if omitted_entry else "KEPT",
                    "bullets": [
                        {"text": text, "claim_status": "OMITTED" if text.startswith("~") else "SUPPORTED"}
                        for text in texts
                    ],
                }
            ],
        }

    old = doc(section("实习经历", ["A", "B"]), section("项目经历", ["C"]))
    new = doc(section("实习经历", ["A", "D"]), section("项目经历", ["C"]), section("技能", ["E"]))
    breakdown = {item["section"]: item for item in _section_breakdown(old, new)}

    assert breakdown["实习经历"]["status"] == "changed"
    assert breakdown["实习经历"]["added"] == ["D"]
    assert breakdown["实习经历"]["removed"] == ["B"]
    assert breakdown["实习经历"]["kept"] == 1
    assert breakdown["项目经历"]["status"] == "unchanged"
    assert breakdown["项目经历"]["kept"] == 1
    assert breakdown["技能"]["status"] == "added"
    assert breakdown["技能"]["added"] == ["E"]

    # 被 OMIT 的条目 / 要点不计入
    only_omitted = _section_breakdown(doc(section("教育经历", ["~X"], omitted_entry=True)), doc(section("教育经历", ["~X"], omitted_entry=True)))
    assert only_omitted[0]["status"] == "unchanged"
    assert only_omitted[0]["kept"] == 0
