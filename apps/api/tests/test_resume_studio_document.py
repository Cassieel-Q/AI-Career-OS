from uuid import uuid4

from app import models
from app.resume_studio_service import get_or_create_document, read_document


def _mission_with_resume(db_session):
    profile = models.UserProfile(status="CONFIRMED", full_name="Ada Chen", phone="13800000000", email="ada@example.com")
    db_session.add(profile)
    db_session.flush()
    experience = models.Experience(
        profile_id=profile.id,
        title="Product Intern",
        organization="Acme",
        dates="2025.01–2025.06",
        description="Built evaluation dashboards",
        evidence_text="Product Intern at Acme; built evaluation dashboards",
        experience_type="INTERNSHIP",
    )
    education = models.Education(profile_id=profile.id, institution="Example University", degree="MSc", evidence_text="Example University MSc")
    db_session.add_all([experience, education])
    db_session.flush()
    job = models.TargetJob(profile_id=profile.id, raw_text="Product manager", content_hash="x" * 64)
    db_session.add(job)
    db_session.flush()
    mission = models.JobMission(profile_id=profile.id, target_job_id=job.id, display_name="Acme PM", company="Acme", role="PM")
    db_session.add(mission)
    db_session.flush()
    resume = models.TargetResume(mission_id=mission.id, version=1, status="CONFIRMED", recommended_experience_order=[str(experience.id)])
    db_session.add(resume)
    db_session.flush()
    accepted_id = uuid4()
    db_session.add_all([
        models.TargetResumeBullet(
            id=accepted_id,
            target_resume_id=resume.id,
            source_experience_id=experience.id,
            original_text="Built dashboards",
            suggested_text="Built evaluation dashboards",
            final_text="Built product evaluation dashboards",
            reason="Grounded rewrite",
            evidence_refs=[str(experience.id)],
            status="EDITED",
            sort_order=0,
        ),
        models.TargetResumeBullet(
            target_resume_id=resume.id,
            source_experience_id=experience.id,
            original_text="Unused alternative",
            suggested_text="Unused alternative",
            reason="Alternative",
            status="REJECTED",
            sort_order=1,
        ),
    ])
    db_session.commit()
    return mission, experience, accepted_id


def test_studio_imports_confirmed_resume_once_with_stable_bullet_ids(db_session):
    mission, experience, accepted_id = _mission_with_resume(db_session)

    first = read_document(get_or_create_document(db_session, mission.id))
    second = read_document(get_or_create_document(db_session, mission.id))

    assert first["id"] == second["id"]
    assert first["revision"] == second["revision"] == 1
    assert first["document"]["basics"]["name"]["text"] == "Ada Chen"
    sections = first["document"]["sections"]
    assert any(section["kind"] == "education" for section in sections)
    experience_entry = next(section for section in sections if section["kind"] == "experience")["entries"][0]
    assert experience_entry["id"] == str(experience.id)
    assert [bullet["id"] for bullet in experience_entry["bullets"]] == [str(accepted_id)]
    assert experience_entry["bullets"][0]["evidence_refs"] == [str(experience.id)]
    assert experience_entry["bullets"][0]["text"] == "Built product evaluation dashboards"


def test_studio_requires_a_confirmed_target_resume(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    db_session.query(models.TargetResume).filter_by(mission_id=mission.id).update({"status": "DRAFT"})
    db_session.commit()

    from fastapi import HTTPException
    import pytest

    with pytest.raises(HTTPException) as caught:
        get_or_create_document(db_session, mission.id)
    assert caught.value.status_code == 409


def test_studio_splits_structured_project_points_into_pdf_bullets(db_session):
    mission, _, accepted_id = _mission_with_resume(db_session)
    bullet = db_session.get(models.TargetResumeBullet, accepted_id)
    bullet.final_text = "产品设计：设计点击爆泡反馈。\n开发上线：完成小游戏上线。"
    db_session.commit()
    entry = next(section for section in get_or_create_document(db_session, mission.id).document_json["sections"] if section["kind"] == "experience")["entries"][0]
    assert [node["text"] for node in entry["bullets"]] == ["产品设计：设计点击爆泡反馈。", "开发上线：完成小游戏上线。"]
    assert entry["bullets"][0]["id"] == str(accepted_id)


def test_studio_includes_only_fact_confirmed_synthetic_project(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    resume = db_session.query(models.TargetResume).filter_by(mission_id=mission.id).one()
    resume.strategy = {"_generation": {"bullet_project_titles": [None, None, "项目草案：AI Career OS"]}}
    synthetic = models.TargetResumeBullet(
        target_resume_id=resume.id, source_experience_id=None, original_text="项目草案",
        suggested_text="产品设计：设计岗位解析流程。\n开发验证：完成原型测试。",
        reason="作品集项目", risk_flags=["SYNTHETIC_PROJECT", "FACT_CONFIRMED"],
        status="ACCEPTED", sort_order=2,
    )
    db_session.add(synthetic)
    db_session.commit()
    document = get_or_create_document(db_session, mission.id).document_json
    entries = next(section for section in document["sections"] if section["kind"] == "experience")["entries"]
    project = next(entry for entry in entries if entry["title"]["text"] == "AI Career OS")
    assert project["title"]["text"] == "AI Career OS"
    assert [item["text"] for item in project["bullets"]] == ["产品设计：设计岗位解析流程。", "开发验证：完成原型测试。"]
