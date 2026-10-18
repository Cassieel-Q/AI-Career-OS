"""Sprint E：多岗位复用与面试版本一致性（指令 5.1 / 5.2 / 5.3）。

覆盖：
- 一份经历投多个岗位时，岗位之间互不干扰；
- 事实更新后能给出「关联了 N 份，其中 M 份可能需要更新」，且绝不自动覆盖；
- 面试准备默认读取**实际投递**的那一版，而不是最新 Studio；
- 历史投递快照不可变。
"""
from pathlib import Path
from uuid import uuid4

import pytest

from app import models
from test_resume_studio_document import _mission_with_resume


@pytest.fixture(autouse=True)
def configure_typst(monkeypatch):
    binary = Path(__file__).resolve().parents[3] / ".runtime" / "typst-0.15.1" / "typst-x86_64-pc-windows-msvc" / "typst.exe"
    if binary.exists():
        monkeypatch.setenv("TYPST_BIN", str(binary))


def _add_mission(db_session, profile, experience, *, company: str, role: str) -> models.JobMission:
    """在同一份档案下再加一个岗位，复用同一条经历。"""
    job = models.TargetJob(profile_id=profile.id, raw_text=f"{company} {role}", content_hash=uuid4().hex)
    db_session.add(job)
    db_session.flush()
    mission = models.JobMission(
        profile_id=profile.id, target_job_id=job.id,
        display_name=f"{company} {role}", company=company, role=role,
    )
    db_session.add(mission)
    db_session.flush()
    resume = models.TargetResume(
        mission_id=mission.id, version=1, status="CONFIRMED",
        recommended_experience_order=[str(experience.id)],
    )
    db_session.add(resume)
    db_session.flush()
    db_session.add(models.TargetResumeBullet(
        target_resume_id=resume.id,
        source_experience_id=experience.id,
        original_text="Built dashboards",
        suggested_text="Built evaluation dashboards",
        final_text="Built product evaluation dashboards",
        reason="Grounded rewrite",
        evidence_refs=[str(experience.id)],
        status="EDITED",
        sort_order=0,
    ))
    db_session.commit()
    return mission


def _studio_document(db_session, mission_id):
    from app.resume_studio_service import get_or_create_document
    return get_or_create_document(db_session, mission_id)


def _profile_of(db_session, mission):
    return db_session.get(models.UserProfile, mission.profile_id)


# ---------------------------------------------------------------------------
# 5.1 一份经历投多个岗位
# ---------------------------------------------------------------------------


def test_each_mission_keeps_its_own_studio_document(db_session):
    """岗位 A 的编辑不得改变岗位 B（指令 5.1）。"""
    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission_a)
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    mission_c = _add_mission(db_session, profile, experience, company="Gamma", role="APM")

    doc_a = _studio_document(db_session, mission_a.id)
    doc_b = _studio_document(db_session, mission_b.id)
    doc_c = _studio_document(db_session, mission_c.id)
    assert len({doc_a.id, doc_b.id, doc_c.id}) == 3

    # 只改岗位 A 的要点
    entry_a = next(s for s in doc_a.document_json["sections"] if s["kind"] == "experience")["entries"][0]
    entry_a["bullets"][0]["text"] = "只在 A 岗位改过的要点"
    doc_a.revision = 2
    db_session.commit()

    entry_b = next(s for s in _studio_document(db_session, mission_b.id).document_json["sections"] if s["kind"] == "experience")["entries"][0]
    entry_c = next(s for s in _studio_document(db_session, mission_c.id).document_json["sections"] if s["kind"] == "experience")["entries"][0]
    assert entry_b["bullets"][0]["text"] == "Built product evaluation dashboards"
    assert entry_c["bullets"][0]["text"] == "Built product evaluation dashboards"
    assert _studio_document(db_session, mission_b.id).revision == 1
    assert _studio_document(db_session, mission_c.id).revision == 1


def test_edit_order_in_one_mission_does_not_touch_others(db_session):
    """调整岗位 A 的强调顺序不影响岗位 B。"""
    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission_a)
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    doc_a = _studio_document(db_session, mission_a.id)
    doc_b = _studio_document(db_session, mission_b.id)

    sections_a = doc_a.document_json["sections"]
    sections_a.reverse()
    doc_a.document_json["sections"] = sections_a
    db_session.commit()

    kinds_b = [section["kind"] for section in _studio_document(db_session, mission_b.id).document_json["sections"]]
    assert kinds_b == ["education", "experience", "skills", "certifications"]


# ---------------------------------------------------------------------------
# 5.2 一个事实发生更新
# ---------------------------------------------------------------------------


def test_fact_impact_reports_affected_missions_without_changing_anything(db_session):
    """「这项事实关联了 3 份岗位简历，其中 N 份可能需要更新」——只读，不自动改。"""
    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission_a)
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    mission_c = _add_mission(db_session, profile, experience, company="Gamma", role="APM")
    for mission in (mission_a, mission_b, mission_c):
        _studio_document(db_session, mission.id)

    # 事实更新：把「仅完成原型」改成「实际完成上线」并核对
    experience.description = "完成原型设计并已上线，日活提升 30%（经核对）"
    db_session.commit()

    from app.fact_impact_service import analyze_impact
    report = analyze_impact(db_session, profile.id, "experience", experience.id)

    assert report["total_missions"] == 3
    assert report["auto_update"] is False
    assert report["summary"] == "这项事实关联了 3 份岗位简历，其中 3 份可能需要更新。"
    assert {item["mission_id"] for item in report["missions"]} == {
        str(mission_a.id), str(mission_b.id), str(mission_c.id)
    }
    # 只读：任何一份的修订号都没有变
    assert all(_studio_document(db_session, m.id).revision == 1 for m in (mission_a, mission_b, mission_c))


def test_selective_sync_updates_only_the_chosen_mission(db_session):
    """只更新用户选择的那一份，另外两份保持原版本（指令 5.2）。"""
    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission_a)
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    mission_c = _add_mission(db_session, profile, experience, company="Gamma", role="APM")
    for mission in (mission_a, mission_b, mission_c):
        _studio_document(db_session, mission.id)

    experience.dates = "2025.01–2025.09"
    db_session.commit()

    from app.fact_impact_service import sync_mission
    result = sync_mission(db_session, profile.id, "experience", experience.id, mission_b.id, expected_revision=1)
    assert result["changed"] is True
    assert _studio_document(db_session, mission_b.id).revision == 2

    def date_text(mission):
        entry = next(s for s in _studio_document(db_session, mission.id).document_json["sections"] if s["kind"] == "experience")["entries"][0]
        return entry["date"]["text"]

    assert date_text(mission_b) == "2025.01–2025.09"
    assert date_text(mission_a) == "2025.01–2025.06"
    assert date_text(mission_c) == "2025.01–2025.06"
    assert _studio_document(db_session, mission_a.id).revision == 1
    assert _studio_document(db_session, mission_c.id).revision == 1


def test_sync_marks_node_unconfirmed_and_invalidates_delivery_confirmation(db_session):
    """源事实变了，旧的人工核对不再适用：节点回到 NEEDS_CONFIRMATION，投递确认作废。"""
    mission, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    doc = _studio_document(db_session, mission.id)
    doc.confirmed_revision = 1
    db_session.commit()

    experience.organization = "Acme China"
    db_session.commit()

    from app.fact_impact_service import sync_mission
    sync_mission(db_session, profile.id, "experience", experience.id, mission.id, expected_revision=1)

    entry = next(s for s in _studio_document(db_session, mission.id).document_json["sections"] if s["kind"] == "experience")["entries"][0]
    assert entry["subtitle"]["text"] == "Acme China"
    assert entry["subtitle"]["claim_status"] == "NEEDS_CONFIRMATION"
    assert _studio_document(db_session, mission.id).confirmed_revision is None


def test_sync_never_rewrites_ai_bullets(db_session):
    """AI 改写要点不会被系统自动改写，只在 skipped 里给出说明。"""
    mission, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    _studio_document(db_session, mission.id)
    experience.description = "完全不同的新描述"
    db_session.commit()

    from app.fact_impact_service import sync_mission
    result = sync_mission(db_session, profile.id, "experience", experience.id, mission.id, expected_revision=1)
    assert result["updated"] == [] or all(item["location"].endswith(("/title", "/subtitle", "/date")) for item in result["updated"])
    assert any("改写" in item["reason"] for item in result["skipped"])


def test_impact_flags_already_delivered_missions(db_session):
    """已投递的岗位要在影响清单里标出来，避免用户误改已投出去的版本。"""
    mission, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    _studio_document(db_session, mission.id)
    resume = db_session.query(models.TargetResume).filter_by(mission_id=mission.id).one()
    db_session.add(models.JobApplication(
        profile_id=profile.id, mission_id=mission.id, company="Acme", role="PM",
        status="APPLIED", resume_version_id=resume.id, studio_revision=1,
    ))
    db_session.commit()

    from app.fact_impact_service import analyze_impact
    report = analyze_impact(db_session, profile.id, "experience", experience.id)
    assert report["missions"][0]["already_delivered"] is True


def test_impact_endpoint_and_sync_endpoint(client, db_session):
    """HTTP 接口：impact 只读，sync 只改指定岗位。"""
    mission_a, experience, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission_a)
    mission_b = _add_mission(db_session, profile, experience, company="Beta", role="PM")
    for mission in (mission_a, mission_b):
        _studio_document(db_session, mission.id)
    experience.title = "Senior Product Intern"
    db_session.commit()

    base = f"/api/v1/profiles/{profile.id}/facts/experience/{experience.id}"
    impact = client.get(f"{base}/impact")
    assert impact.status_code == 200
    assert impact.json()["total_missions"] == 2
    assert "可能需要更新" in impact.json()["summary"]

    synced = client.post(f"{base}/sync", json={"mission_id": str(mission_b.id), "expected_revision": 1})
    assert synced.status_code == 200
    assert synced.json()["changed"] is True

    entry_a = next(s for s in _studio_document(db_session, mission_a.id).document_json["sections"] if s["kind"] == "experience")["entries"][0]
    assert entry_a["title"]["text"] == "Product Intern"


# ---------------------------------------------------------------------------
# 5.3 面试使用实际投递版本
# ---------------------------------------------------------------------------


def test_interview_resume_says_no_delivery_when_not_applied(client, db_session):
    """工作台版本已确认但尚未投递：明确标注「尚无正式投递版本，当前使用准备中的简历。」"""
    mission, _, _ = _mission_with_resume(db_session)
    _studio_document(db_session, mission.id)
    assert client.post(f"/api/v1/job-missions/{mission.id}/resume-studio/confirm", headers={"If-Match": "1"}).status_code == 200

    payload = client.get(f"/api/v1/job-missions/{mission.id}/interview-resume").json()
    assert payload["source"] == "resume_studio"
    assert payload["delivered"] is False
    assert payload["label"] == "尚无正式投递版本，当前使用准备中的简历。"
    assert payload["versions"] == []


def test_confirming_final_version_records_an_immutable_snapshot(client, db_session):
    """确认正式投递版 → 生成快照；之后编辑 Studio，快照内容不变。"""
    mission, _, _ = _mission_with_resume(db_session)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    confirmed = client.post(f"{base}/confirm", headers={"If-Match": "1"})
    assert confirmed.status_code == 200
    snapshot_id = confirmed.json()["snapshot_id"]
    assert snapshot_id

    from app.delivery_version_service import content_hash
    from app.resume_studio_service import get_or_create_document
    studio = get_or_create_document(db_session, mission.id)
    before_hash = content_hash(studio.document_json)

    edited = client.patch(base, headers={"If-Match": "1"}, json={"type": "add_bullet", "entry_id": studio.document_json["sections"][1]["entries"][0]["id"], "text": "投递之后才新增的经历"})
    assert edited.status_code == 200

    snapshot = db_session.get(models.DeliverySnapshot, __import__("uuid").UUID(snapshot_id))
    assert snapshot.studio_revision == 1
    assert content_hash(snapshot.document_json) == before_hash
    assert "投递之后才新增的经历" not in str(snapshot.document_json)


def test_interview_reads_delivered_version_not_latest_studio(client, db_session):
    """投递之后新增的经历，不能出现在面试准备里（指令 5.3）。"""
    mission, _, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    assert client.post(f"{base}/confirm", headers={"If-Match": "1"}).status_code == 200

    resume = db_session.query(models.TargetResume).filter_by(mission_id=mission.id).one()
    application = models.JobApplication(
        profile_id=profile.id, mission_id=mission.id, company="Acme", role="PM",
        status="APPLIED", applied_at=__import__("datetime").date(2026, 10, 18),
        resume_version_id=resume.id, studio_revision=1,
    )
    db_session.add(application)
    db_session.commit()
    # 绑定投递版本 → 写入正文快照
    bound = client.post(f"/api/v1/applications/{application.id}/bind-resume", json={"mission_id": str(mission.id)})
    assert bound.status_code == 200

    from app.resume_studio_service import get_or_create_document
    studio = get_or_create_document(db_session, mission.id)
    client.patch(base, headers={"If-Match": "1"}, json={"type": "add_bullet", "entry_id": studio.document_json["sections"][1]["entries"][0]["id"], "text": "面试前才补的新经历"})

    payload = client.get(f"/api/v1/job-missions/{mission.id}/interview-resume").json()
    assert payload["source"] == "delivered_snapshot"
    assert "实际投递的版本" in payload["label"]
    texts = [bullet["text"] for bullet in payload["bullets"]]
    assert "面试前才补的新经历" not in texts
    assert "Built product evaluation dashboards" in texts


def test_multiple_deliveries_can_be_selected_explicitly(client, db_session):
    """多次投递时，可以明确选择使用哪一次的版本。"""
    mission, _, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    base = f"/api/v1/job-missions/{mission.id}/resume-studio"
    assert client.post(f"{base}/confirm", headers={"If-Match": "1"}).status_code == 200
    resume = db_session.query(models.TargetResume).filter_by(mission_id=mission.id).one()

    first = models.JobApplication(
        profile_id=profile.id, mission_id=mission.id, company="Acme", role="PM",
        status="CLOSED", applied_at=__import__("datetime").date(2026, 9, 1),
        resume_version_id=resume.id, studio_revision=1,
    )
    second = models.JobApplication(
        profile_id=profile.id, mission_id=mission.id, company="Acme", role="PM",
        status="APPLIED", applied_at=__import__("datetime").date(2026, 10, 1),
        resume_version_id=resume.id, studio_revision=1,
    )
    db_session.add_all([first, second])
    db_session.commit()
    for application in (first, second):
        assert client.post(f"/api/v1/applications/{application.id}/bind-resume", json={"mission_id": str(mission.id)}).status_code == 200

    versions = client.get(f"/api/v1/job-missions/{mission.id}/delivery-versions").json()["versions"]
    assert len(versions) == 2

    chosen = client.get(f"/api/v1/job-missions/{mission.id}/interview-resume", params={"application_id": str(first.id)}).json()
    assert chosen["application_id"] == str(first.id)
    assert chosen["delivered_at"] == "2026-09-01"


def test_proof_service_interview_context_prefers_delivered_snapshot(db_session):
    """proof_service 的面试上下文也走投递快照，而不是最新 Studio。"""
    mission, _, _ = _mission_with_resume(db_session)
    profile = _profile_of(db_session, mission)
    studio = _studio_document(db_session, mission.id)
    resume = db_session.query(models.TargetResume).filter_by(mission_id=mission.id).one()

    from app.delivery_version_service import record_snapshot
    snapshot = record_snapshot(db_session, mission, studio, application_id=None, source="STUDIO_CONFIRM")
    db_session.add(models.JobApplication(
        profile_id=profile.id, mission_id=mission.id, company="Acme", role="PM",
        status="APPLIED", applied_at=__import__("datetime").date(2026, 10, 18),
        resume_version_id=resume.id, studio_revision=1,
    ))
    db_session.commit()

    # 投递后再改 Studio
    studio.document_json["sections"][1]["entries"][0]["bullets"][0]["text"] = "投递之后改过的内容"
    studio.revision = 2
    db_session.commit()

    from app.proof_service import _final_resume_context
    context = _final_resume_context(db_session.get(models.JobMission, mission.id))
    assert context is not None
    assert context["source"] == "delivered_snapshot"
    assert "投递之后改过的内容" not in [bullet["text"] for bullet in context["bullets"]]
    assert context["snapshot_id"] == str(snapshot.id)
