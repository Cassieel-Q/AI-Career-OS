from app.proof_service import _final_resume_context
from app.resume_studio_service import apply_operation, get_or_create_document
from test_resume_studio_document import _mission_with_resume


def test_interview_prefers_confirmed_studio_and_ignores_unconfirmed_edit(db_session):
    mission, _, _ = _mission_with_resume(db_session)
    legacy = _final_resume_context(mission)
    assert legacy and legacy["bullets"]

    row = get_or_create_document(db_session, mission.id)
    bullet = next(section for section in row.document_json["sections"] if section["kind"] == "experience")["entries"][0]["bullets"][0]
    edited = apply_operation(db_session, mission.id, 1, {"type": "set_text", "node_id": bullet["id"], "text": "Verified Studio achievement"})
    row.confirmed_revision = edited["revision"]
    db_session.commit()
    confirmed = _final_resume_context(mission)
    assert confirmed["source"] == "resume_studio"
    assert confirmed["revision"] == 2
    assert any(item["text"] == "Verified Studio achievement" for item in confirmed["bullets"])

    apply_operation(db_session, mission.id, 2, {"type": "set_text", "node_id": bullet["id"], "text": "Unconfirmed Studio achievement"})
    unconfirmed = _final_resume_context(mission)
    assert "Unconfirmed Studio achievement" not in [item["text"] for item in unconfirmed["bullets"]]
