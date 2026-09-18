from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .job_description_schemas import JobDescriptionCreate, JobDescriptionPatch, JobDescriptionRead
from .profile_schemas import ProfileStatus
from .role_exploration_schemas import RoleCode
from .role_exploration_service import _read_row as read_exploration_row
from .role_profiles import ROLE_PROFILE_VERSION


MAX_JOB_DESCRIPTIONS = 10


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def normalize_content_for_hash(raw_text: str) -> str:
    """Normalize whitespace only; stored evidence remains byte-for-byte unchanged."""
    return " ".join(raw_text.split())


def content_hash(raw_text: str) -> str:
    return hashlib.sha256(normalize_content_for_hash(raw_text).encode("utf-8")).hexdigest()


def _read(row: models.JobDescription) -> JobDescriptionRead:
    return JobDescriptionRead.model_validate(row)


def _target_profile_id(db: Session, target_role_id: UUID) -> UUID:
    try:
        profile_id = db.execute(
            select(models.TargetRole.profile_id).where(models.TargetRole.id == target_role_id)
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc
    if profile_id is None:
        raise _http(404, "Target role not found")
    return profile_id


def _load_current_target(
    db: Session,
    target_role_id: UUID,
    *,
    for_update: bool,
) -> models.TargetRole:
    profile_id = _target_profile_id(db, target_role_id)
    try:
        profile_query = select(models.UserProfile).where(models.UserProfile.id == profile_id)
        if for_update:
            profile_query = profile_query.with_for_update()
        profile = db.execute(profile_query).scalar_one_or_none()
        if profile is None:
            raise _http(404, "Target role not found")

        preference_query = select(models.CareerPreference).where(
            models.CareerPreference.profile_id == profile_id
        )
        exploration_query = select(models.RoleExploration).where(
            models.RoleExploration.profile_id == profile_id
        )
        target_query = select(models.TargetRole).where(
            models.TargetRole.id == target_role_id,
            models.TargetRole.profile_id == profile_id,
        )
        if for_update:
            preference_query = preference_query.with_for_update()
            exploration_query = exploration_query.with_for_update()
            target_query = target_query.with_for_update()
        preference = db.execute(preference_query).scalar_one_or_none()
        exploration = db.execute(exploration_query).scalar_one_or_none()
        target = db.execute(target_query).scalar_one_or_none()
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc

    if target is None:
        raise _http(404, "Target role not found")
    if profile.status != ProfileStatus.CONFIRMED.value:
        raise _http(409, "Job descriptions require a current target role")
    if preference is None or exploration is None:
        raise _http(409, "Job descriptions require a current target role")
    if target.role_exploration_id != exploration.id:
        raise _http(409, "Target role is not current")
    if target.role_profile_version != ROLE_PROFILE_VERSION:
        raise _http(409, "Target role is not current")
    try:
        result = read_exploration_row(exploration, profile, preference).result
        role_code = RoleCode(target.role_code)
    except (HTTPException, ValueError) as exc:
        raise _http(409, "Target role is not current") from exc
    if role_code not in {entry.role_code for entry in result.items}:
        raise _http(409, "Target role is not current")
    return target


def _is_duplicate_integrity_error(exc: IntegrityError) -> bool:
    message = str(exc.orig).lower()
    return (
        "uq_job_descriptions_target_role_content_hash" in message
        or "job_descriptions.target_role_id, job_descriptions.content_hash" in message
    )


def list_job_descriptions(db: Session, target_role_id: UUID) -> list[JobDescriptionRead]:
    _load_current_target(db, target_role_id, for_update=False)
    try:
        rows = db.scalars(
            select(models.JobDescription)
            .where(models.JobDescription.target_role_id == target_role_id)
            .order_by(models.JobDescription.created_at.asc(), models.JobDescription.id.asc())
        ).all()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc
    return [_read(row) for row in rows]


def create_job_description(
    db: Session,
    target_role_id: UUID,
    payload: JobDescriptionCreate,
) -> JobDescriptionRead:
    _load_current_target(db, target_role_id, for_update=True)
    digest = content_hash(payload.raw_text)
    try:
        count = db.scalar(
            select(func.count()).select_from(models.JobDescription).where(
                models.JobDescription.target_role_id == target_role_id
            )
        )
        if count is not None and count >= MAX_JOB_DESCRIPTIONS:
            raise _http(409, "A target role may contain at most 10 job descriptions")
        duplicate = db.scalar(
            select(models.JobDescription.id).where(
                models.JobDescription.target_role_id == target_role_id,
                models.JobDescription.content_hash == digest,
            )
        )
        if duplicate is not None:
            raise _http(409, "This exact job description is already saved")
        now = datetime.now(timezone.utc)
        row = models.JobDescription(
            target_role_id=target_role_id,
            raw_text=payload.raw_text,
            source_url=payload.source_url,
            content_hash=digest,
            created_at=now,
            updated_at=now,
        )
        db.add(row)
        db.commit()
        db.refresh(row)
        return _read(row)
    except HTTPException:
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_integrity_error(exc):
            raise _http(409, "This exact job description is already saved") from exc
        raise _http(503, "Job description persistence failed") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc


def _load_current_item(db: Session, jd_id: UUID, *, for_update: bool) -> models.JobDescription:
    try:
        target_role_id = db.execute(
            select(models.JobDescription.target_role_id).where(models.JobDescription.id == jd_id)
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc
    if target_role_id is None:
        raise _http(404, "Job description not found")
    _load_current_target(db, target_role_id, for_update=for_update)
    try:
        query = select(models.JobDescription).where(
            models.JobDescription.id == jd_id,
            models.JobDescription.target_role_id == target_role_id,
        )
        if for_update:
            query = query.with_for_update()
        row = db.execute(query).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc
    if row is None:
        raise _http(404, "Job description not found")
    return row


def update_job_description(
    db: Session,
    jd_id: UUID,
    payload: JobDescriptionPatch,
) -> JobDescriptionRead:
    row = _load_current_item(db, jd_id, for_update=True)
    fields = payload.model_fields_set
    if not fields:
        return _read(row)
    try:
        if "raw_text" in fields:
            assert payload.raw_text is not None
            digest = content_hash(payload.raw_text)
            duplicate = db.scalar(
                select(models.JobDescription.id).where(
                    models.JobDescription.target_role_id == row.target_role_id,
                    models.JobDescription.content_hash == digest,
                    models.JobDescription.id != row.id,
                )
            )
            if duplicate is not None:
                raise _http(409, "This exact job description is already saved")
            row.raw_text = payload.raw_text
            row.content_hash = digest
        if "source_url" in fields:
            row.source_url = payload.source_url
        row.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(row)
        return _read(row)
    except HTTPException:
        raise
    except IntegrityError as exc:
        db.rollback()
        if _is_duplicate_integrity_error(exc):
            raise _http(409, "This exact job description is already saved") from exc
        raise _http(503, "Job description persistence failed") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc


def delete_job_description(db: Session, jd_id: UUID) -> None:
    row = _load_current_item(db, jd_id, for_update=True)
    try:
        db.delete(row)
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Job description persistence failed") from exc
