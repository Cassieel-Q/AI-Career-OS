from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session
from sqlalchemy import delete, select

from app import models
from app.profile_schemas import (
    CertificationInput,
    CertificationRead,
    CareerPreferencesInput,
    CareerPreferencesRead,
    EducationInput,
    EducationRead,
    ExperienceInput,
    ExperienceRead,
    ProfileRead,
    ProfileSkillInput,
    ProfileSkillRead,
    ProfileStatus,
    ProfileUpdate,
    SourceType,
)
from app.resume_schemas import ResumeExtractionResult


def _not_found(profile_id: UUID) -> HTTPException:
    return HTTPException(status_code=404, detail=f"Profile {profile_id} was not found")


def _get_profile(db: Session, profile_id: UUID, *, for_update: bool = False) -> models.UserProfile:
    statement = select(models.UserProfile).where(models.UserProfile.id == profile_id)
    if for_update:
        statement = statement.with_for_update()
    profile = db.execute(statement).scalar_one_or_none()
    if profile is None:
        raise _not_found(profile_id)
    return profile


def _profile_read(profile: models.UserProfile) -> ProfileRead:
    return ProfileRead(
        profile_id=profile.id,
        status=ProfileStatus(profile.status),
        full_name=profile.full_name,
        phone=profile.phone,
        email=profile.email,
        city=profile.city,
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        education=[EducationRead.model_validate(item) for item in profile.education],
        skills=[ProfileSkillRead.model_validate(item) for item in profile.skills],
        experiences=[ExperienceRead.model_validate(item) for item in profile.experiences],
        certifications=[CertificationRead.model_validate(item) for item in profile.certifications],
        preferences=_preferences_read(profile.career_preference),
    )


def _preferences_read(
    preference: models.CareerPreference | None,
) -> CareerPreferencesRead | None:
    if preference is None:
        return None
    return CareerPreferencesRead(
        id=preference.id,
        profile_id=preference.profile_id,
        priority_order=[preference.priority_1, preference.priority_2],
        weekly_hours=preference.weekly_hours,
        created_at=preference.created_at,
        updated_at=preference.updated_at,
    )


def create_draft_profile(db: Session, extraction: ResumeExtractionResult) -> models.UserProfile:
    profile = models.UserProfile(
        status=ProfileStatus.DRAFT.value,
        full_name=extraction.full_name,
        phone=extraction.phone,
        email=extraction.email,
        city=extraction.city,
    )
    profile.education = [
        models.Education(
            institution=item.institution,
            degree=item.degree,
            field_of_study=item.field_of_study,
            dates=item.dates,
            relevant_courses=item.relevant_courses,
            evidence_text=item.evidence_text,
            source_type=SourceType.AI_EXTRACTED.value,
            raw_value=item.raw_value,
            canonical_value=item.canonical_value,
            evidence_start=item.evidence_start,
            evidence_end=item.evidence_end,
        )
        for item in extraction.education
    ]
    profile.skills = [
        models.ProfileSkill(
            name=item.name,
            proficiency=None,
            evidence_text=item.evidence_text,
            source_type=SourceType.AI_EXTRACTED.value,
            raw_value=item.raw_value,
            canonical_value=item.canonical_value,
            evidence_start=item.evidence_start,
            evidence_end=item.evidence_end,
        )
        for item in extraction.skills
    ]
    profile.experiences = [
        models.Experience(
            title=item.title,
            organization=item.organization,
            dates=item.dates,
            description=item.description,
            experience_type=item.experience_type.value,
            evidence_text=item.evidence_text,
            source_type=SourceType.AI_EXTRACTED.value,
            raw_value=item.raw_value,
            canonical_value=item.canonical_value,
            evidence_start=item.evidence_start,
            evidence_end=item.evidence_end,
        )
        for item in extraction.experiences
    ]
    profile.certifications = [
        models.Certification(
            name=item.name,
            issuer=item.issuer,
            date=item.date,
            score=item.score,
            status=item.status,
            evidence_text=item.evidence_text,
            source_type=SourceType.AI_EXTRACTED.value,
            raw_value=item.raw_value,
            canonical_value=item.canonical_value,
            evidence_start=item.evidence_start,
            evidence_end=item.evidence_end,
        )
        for item in extraction.certifications
    ]
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def get_profile(db: Session, profile_id: UUID) -> ProfileRead:
    return _profile_read(_get_profile(db, profile_id))


def delete_profile(db: Session, profile_id: UUID) -> None:
    """Permanently delete a profile and every profile-scoped workflow record."""
    profile = _get_profile(db, profile_id, for_update=True)
    try:
        mission_ids = select(models.JobMission.id).where(models.JobMission.profile_id == profile_id)
        resume_ids = select(models.TargetResume.id).where(models.TargetResume.mission_id.in_(mission_ids))
        session_ids = select(models.InterviewSession.id).where(models.InterviewSession.profile_id == profile_id)
        # Delete leaves first so this remains deterministic when a deployment
        # has SQLite foreign keys disabled or a legacy FK uses SET NULL.
        db.execute(delete(models.ProofArtifact).where(models.ProofArtifact.profile_id == profile_id))
        db.execute(delete(models.InterviewTurn).where(models.InterviewTurn.session_id.in_(session_ids)))
        db.execute(delete(models.TargetResumeBullet).where(models.TargetResumeBullet.target_resume_id.in_(resume_ids)))
        db.execute(delete(models.ProofAction).where(models.ProofAction.profile_id == profile_id))
        db.execute(delete(models.InterviewSession).where(models.InterviewSession.profile_id == profile_id))
        db.execute(delete(models.TargetResume).where(models.TargetResume.mission_id.in_(mission_ids)))
        db.execute(delete(models.RedTeamReport).where(models.RedTeamReport.mission_id.in_(mission_ids)))
        db.execute(delete(models.InterviewPack).where(models.InterviewPack.mission_id.in_(mission_ids)))
        db.execute(delete(models.InterviewOutcome).where(models.InterviewOutcome.mission_id.in_(mission_ids)))
        db.execute(delete(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id.in_(mission_ids)))
        db.execute(delete(models.ResumeClaim).where(models.ResumeClaim.profile_id == profile_id))
        db.execute(delete(models.JobMission).where(models.JobMission.profile_id == profile_id))
        db.execute(delete(models.TargetJob).where(models.TargetJob.profile_id == profile_id))
        db.execute(delete(models.GapAnalysis).where(models.GapAnalysis.profile_id == profile_id))
        db.execute(delete(models.Roadmap).where(models.Roadmap.profile_id == profile_id))

        # Load passive-deletes collections before deleting the parent. Loaded
        # collections are handled by the ORM cascade even when SQLite foreign
        # keys are disabled in a test database.
        list(profile.job_missions)
        list(profile.target_jobs)
        db.delete(profile)
        db.commit()
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Profile deletion failed") from error


def _has_changed(existing: Any, item: Any, fields: tuple[str, ...]) -> bool:
    return any(getattr(existing, field) != getattr(item, field) for field in fields)


def _source_for_item(existing: Any | None, item: Any, fields: tuple[str, ...]) -> str:
    if existing is None:
        return SourceType.USER_ENTERED.value
    if not _has_changed(existing, item, fields):
        return existing.source_type
    if existing.source_type == SourceType.USER_ENTERED.value:
        return SourceType.USER_ENTERED.value
    return SourceType.USER_EDITED.value


def _replace_collection(
    profile: models.UserProfile,
    collection_name: str,
    items: list[Any],
    fields: tuple[str, ...],
    model_type: type[Any],
) -> None:
    existing_items = list(getattr(profile, collection_name))
    existing_by_id = {item.id: item for item in existing_items}
    seen_ids: set[UUID] = set()
    replacement: list[Any] = []
    for item in items:
        if item.id is not None:
            if item.id in seen_ids:
                raise HTTPException(status_code=422, detail="A profile item ID may appear only once")
            seen_ids.add(item.id)
            existing = existing_by_id.get(item.id)
            if existing is None:
                raise HTTPException(status_code=422, detail="Profile item does not belong to this profile")
            source_type = _source_for_item(existing, item, fields)
            for field in fields:
                setattr(existing, field, getattr(item, field))
            # Evidence is server-owned once a row exists. The API has no source
            # resume text on PUT, so accepting a replacement would allow an
            # AI anchor to be deleted or falsified without re-validation.
            existing.source_type = source_type
            replacement.append(existing)
        else:
            values = {field: getattr(item, field) for field in fields}
            values.update(
                evidence_text=item.evidence_text,
                source_type=SourceType.USER_ENTERED.value,
            )
            replacement.append(model_type(**values))
    setattr(profile, collection_name, replacement)


def update_draft_profile(db: Session, profile_id: UUID, payload: ProfileUpdate) -> ProfileRead:
    profile = _get_profile(db, profile_id, for_update=True)
    if profile.status == ProfileStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="Confirmed profiles cannot be edited")
    profile.full_name = payload.full_name.strip() if payload.full_name else None
    profile.phone = payload.phone.strip() if payload.phone else None
    profile.email = payload.email.strip() if payload.email else None
    profile.city = payload.city.strip() if payload.city else None
    _replace_collection(
        profile,
        "education",
        payload.education,
        ("institution", "degree", "field_of_study", "dates", "relevant_courses"),
        models.Education,
    )
    _replace_collection(profile, "skills", payload.skills, ("name", "proficiency"), models.ProfileSkill)
    _replace_collection(
        profile,
        "experiences",
        payload.experiences,
        ("title", "organization", "dates", "description", "experience_type"),
        models.Experience,
    )
    _replace_collection(
        profile,
        "certifications",
        payload.certifications,
        ("name", "issuer", "date", "score", "status"),
        models.Certification,
    )
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)


def confirm_profile(db: Session, profile_id: UUID) -> ProfileRead:
    profile = _get_profile(db, profile_id, for_update=True)
    if profile.status == ProfileStatus.CONFIRMED.value:
        return _profile_read(profile)
    if not any((profile.education, profile.skills, profile.experiences, profile.certifications)):
        raise HTTPException(status_code=422, detail="A profile must contain at least one item before confirmation")
    profile.status = ProfileStatus.CONFIRMED.value
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)


def upsert_career_preferences(
    db: Session,
    profile_id: UUID,
    payload: CareerPreferencesInput,
) -> CareerPreferencesRead:
    try:
        profile = _get_profile(db, profile_id, for_update=True)
        if profile.status != ProfileStatus.CONFIRMED.value:
            raise HTTPException(
                status_code=409,
                detail="Career preferences require a confirmed profile",
            )
        preference = db.execute(
            select(models.CareerPreference)
            .where(models.CareerPreference.profile_id == profile_id)
            .with_for_update()
        ).scalar_one_or_none()
        values = {
            "priority_1": payload.priority_order[0].value,
            "priority_2": payload.priority_order[1].value,
            "weekly_hours": payload.weekly_hours,
            "updated_at": datetime.now(timezone.utc),
        }
        preferences_changed = preference is None or any(
            getattr(preference, field) != value
            for field, value in values.items()
            if field != "updated_at"
        )
        if preferences_changed:
            role_exploration = db.execute(
                select(models.RoleExploration)
                .where(models.RoleExploration.profile_id == profile_id)
                .with_for_update()
            ).scalar_one_or_none()
            if role_exploration is not None:
                db.delete(role_exploration)
        if preference is None:
            preference = models.CareerPreference(profile_id=profile_id, **values)
            db.add(preference)
        else:
            for field, value in values.items():
                setattr(preference, field, value)
        db.commit()
        db.refresh(preference)
    except HTTPException:
        raise
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(
            status_code=503,
            detail="Career preferences persistence failed",
        ) from error
    return _preferences_read(preference)  # type: ignore[return-value]


def create_empty_draft_profile(db: Session) -> ProfileRead:
    profile = models.UserProfile(status=ProfileStatus.DRAFT.value)
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)


def replace_profile_from_extraction(db: Session, profile_id: UUID, extraction: ResumeExtractionResult) -> ProfileRead:
    """Re-ingest a resume into an existing draft profile (clears collections first)."""
    profile = _get_profile(db, profile_id, for_update=True)
    if profile.status == ProfileStatus.CONFIRMED.value:
        raise HTTPException(status_code=409, detail="Confirmed profiles cannot be replaced from a resume upload")
    profile.education = []
    profile.skills = []
    profile.experiences = []
    profile.certifications = []
    profile.full_name = extraction.full_name
    profile.phone = extraction.phone
    profile.email = extraction.email
    profile.city = extraction.city
    db.flush()
    for item in extraction.education:
        profile.education.append(
            models.Education(
                institution=item.institution,
                degree=item.degree,
                field_of_study=item.field_of_study,
                dates=item.dates,
                relevant_courses=item.relevant_courses,
                evidence_text=item.evidence_text,
                source_type=SourceType.AI_EXTRACTED.value,
                raw_value=item.raw_value,
                canonical_value=item.canonical_value,
                evidence_start=item.evidence_start,
                evidence_end=item.evidence_end,
            )
        )
    for item in extraction.skills:
        profile.skills.append(
            models.ProfileSkill(
                name=item.name,
                proficiency=None,
                evidence_text=item.evidence_text,
                source_type=SourceType.AI_EXTRACTED.value,
                raw_value=item.raw_value,
                canonical_value=item.canonical_value,
                evidence_start=item.evidence_start,
                evidence_end=item.evidence_end,
            )
        )
    for item in extraction.experiences:
        profile.experiences.append(
            models.Experience(
                title=item.title,
                organization=item.organization,
                dates=item.dates,
                description=item.description,
                experience_type=item.experience_type.value,
                evidence_text=item.evidence_text,
                source_type=SourceType.AI_EXTRACTED.value,
                raw_value=item.raw_value,
                canonical_value=item.canonical_value,
                evidence_start=item.evidence_start,
                evidence_end=item.evidence_end,
            )
        )
    for item in extraction.certifications:
        profile.certifications.append(
            models.Certification(
                name=item.name,
                issuer=item.issuer,
                date=item.date,
                score=item.score,
                status=item.status,
                evidence_text=item.evidence_text,
                source_type=SourceType.AI_EXTRACTED.value,
                raw_value=item.raw_value,
                canonical_value=item.canonical_value,
                evidence_start=item.evidence_start,
                evidence_end=item.evidence_end,
            )
        )
    profile.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(profile)
    return _profile_read(profile)
