from app import models
from app.mission_service import confirm_target_resume
from test_resume_studio_document import _mission_with_resume


def test_bulk_confirmation_never_auto_accepts_unsupported_point(db_session):
    mission, _, accepted_id = _mission_with_resume(db_session)
    mission.resume_source = {"profile_id": str(mission.profile_id)}
    mission.workflow_state = "TARGET_RESUME_DRAFT"
    bullet = db_session.get(models.TargetResumeBullet, accepted_id)
    bullet.status = "SUGGESTED"
    bullet.risk_flags = ["GROUNDING:UNSUPPORTED"]
    # 另有一条用户已接受的事实要点：确认才不会触发「零接受要点」防呆（409）
    resume = db_session.get(models.TargetResume, bullet.target_resume_id)
    experience = db_session.get(models.Experience, bullet.source_experience_id)
    db_session.add(
        models.TargetResumeBullet(
            target_resume_id=resume.id,
            source_experience_id=experience.id,
            original_text="Built dashboards",
            suggested_text="Built evaluation dashboards",
            final_text="Built evaluation dashboards",
            reason="Grounded rewrite",
            evidence_refs=[str(experience.id)],
            status="ACCEPTED",
            sort_order=9,
        )
    )
    db_session.commit()

    confirm_target_resume(db_session, mission.id)
    db_session.refresh(bullet)
    assert bullet.status == "REJECTED"
