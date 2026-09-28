from app.profile_schemas import ProfileUpdate
from app.profile_service import create_draft_profile, get_profile, update_draft_profile
from app.resume_schemas import ResumeExtractionResult


def test_profile_contact_fields_round_trip_from_resume_and_confirmation_edit(db_session):
    profile = create_draft_profile(db_session, ResumeExtractionResult(
        full_name="潘佳琪",
        phone="13800138000",
        email="pan@example.com",
        city="上海",
        education=[{"institution": "上海大学", "evidence_text": "上海大学"}],
    ))
    read = get_profile(db_session, profile.id)
    assert (read.full_name, read.phone, read.email, read.city) == ("潘佳琪", "13800138000", "pan@example.com", "上海")

    updated = update_draft_profile(db_session, profile.id, ProfileUpdate(
        full_name="潘佳琪",
        phone="13900139000",
        email="new@example.com",
        city="北京",
        education=[{"id": read.education[0].id, "institution": "上海大学"}],
    ))
    assert (updated.phone, updated.email, updated.city) == ("13900139000", "new@example.com", "北京")
