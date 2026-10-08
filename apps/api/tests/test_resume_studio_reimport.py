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
