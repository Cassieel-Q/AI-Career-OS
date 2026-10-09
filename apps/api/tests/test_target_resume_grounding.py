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
    db_session.commit()

    confirm_target_resume(db_session, mission.id)
    db_session.refresh(bullet)
    assert bullet.status == "REJECTED"
