from __future__ import annotations

from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy.orm import Session
from sqlalchemy import select

from app import models
from app.profile_schemas import (
    CertificationInput,
    CertificationRead,
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
        created_at=profile.created_at,
        updated_at=profile.updated_at,
        education=[EducationRead.model_validate(item) for item in profile.education],
        skills=[ProfileSkillRead.model_validate(item) for item in profile.skills],
        experiences=[ExperienceRead.model_validate(item) for item in profile.experiences],
        certifications=[CertificationRead.model_validate(item) for item in profile.certifications],
    )


def create_draft_profile(db: Session, extraction: ResumeExtractionResult) -> models.UserProfile:
    profile = models.UserProfile(status=ProfileStatus.DRAFT.value)
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
