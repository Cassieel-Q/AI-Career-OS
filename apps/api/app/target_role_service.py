from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .profile_schemas import ProfileStatus
from .role_exploration_schemas import RoleCode
from .role_exploration_service import _read_row as read_exploration_row
from .role_profiles import ROLE_PROFILE_BY_CODE, ROLE_PROFILE_VERSION
from .target_role_schemas import TargetRoleRead


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _load_context(
    db: Session,
    profile_id: UUID,
    *,
    for_update: bool,
) -> tuple[models.UserProfile, models.CareerPreference, models.RoleExploration]:
    try:
        profile_query = select(models.UserProfile).where(models.UserProfile.id == profile_id)
        if for_update:
            profile_query = profile_query.with_for_update()
        profile = db.execute(profile_query).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target role persistence failed") from exc
    if profile is None:
        raise _http(404, "Profile not found")
    if profile.status != ProfileStatus.CONFIRMED.value:
        raise _http(409, "Target role requires a confirmed profile")

    try:
        preference_query = select(models.CareerPreference).where(
            models.CareerPreference.profile_id == profile_id
        )
        exploration_query = select(models.RoleExploration).where(
            models.RoleExploration.profile_id == profile_id
        )
        if for_update:
            preference_query = preference_query.with_for_update()
            exploration_query = exploration_query.with_for_update()
        preference = db.execute(preference_query).scalar_one_or_none()
        exploration = db.execute(exploration_query).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target role persistence failed") from exc
    if preference is None:
        raise _http(409, "Career preferences are required before target role selection")
    if exploration is None:
        raise _http(409, "Role exploration is required before target role selection")
    return profile, preference, exploration


def _validated_exploration(
    exploration: models.RoleExploration,
    profile: models.UserProfile,
    preference: models.CareerPreference,
):
    try:
        return read_exploration_row(exploration, profile, preference)
    except HTTPException as exc:
        raise _http(502, "Current role exploration is invalid") from exc


def _read_target_role(
    row: models.TargetRole,
    exploration_id: UUID,
    *,
    require_current_binding: bool = True,
) -> TargetRoleRead:
    try:
        role_code = RoleCode(row.role_code)
    except ValueError as exc:
        raise _http(502, "Stored target role is invalid") from exc
    if row.role_profile_version != ROLE_PROFILE_VERSION:
        raise _http(502, "Stored target role is invalid")
    if require_current_binding and row.role_exploration_id != exploration_id:
        raise _http(409, "Target role requires a current role exploration")
    return TargetRoleRead(
        id=row.id,
        profile_id=row.profile_id,
        role_code=role_code,
        role_name=ROLE_PROFILE_BY_CODE[role_code].display_name,
        role_profile_version=ROLE_PROFILE_VERSION,
        role_exploration_id=row.role_exploration_id,
        selected_at=row.selected_at,
        updated_at=row.updated_at,
    )


def select_target_role(db: Session, profile_id: UUID, role_code: RoleCode) -> TargetRoleRead:
    profile, preference, exploration = _load_context(db, profile_id, for_update=True)
    current_exploration = _validated_exploration(exploration, profile, preference)
    if role_code not in {item.role_code for item in current_exploration.result.items}:
        raise _http(409, "Selected role is not available in the current role exploration")

    try:
        row = db.execute(
            select(models.TargetRole)
            .where(models.TargetRole.profile_id == profile_id)
            .with_for_update()
        ).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        replace_row = row is not None and (
            row.role_code != role_code.value
            or row.role_profile_version != current_exploration.role_profile_version
            or row.role_exploration_id != exploration.id
        )
        if replace_row:
            db.delete(row)
            db.flush()
            row = None
        if row is None:
            row = models.TargetRole(
                profile_id=profile_id,
                role_code=role_code.value,
                role_profile_version=current_exploration.role_profile_version,
                role_exploration_id=exploration.id,
                selected_at=now,
                updated_at=now,
            )
            db.add(row)
        else:
            row.selected_at = now
            row.updated_at = now
        db.commit()
        db.refresh(row)
        return _read_target_role(row, exploration.id)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target role persistence failed") from exc


def get_target_role(db: Session, profile_id: UUID) -> TargetRoleRead:
    profile, preference, exploration = _load_context(db, profile_id, for_update=False)
    current_exploration = _validated_exploration(exploration, profile, preference)
    try:
        row = db.execute(
            select(models.TargetRole).where(models.TargetRole.profile_id == profile_id)
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target role persistence failed") from exc
    if row is None:
        raise _http(404, "Target role has not been selected")
    if row.role_code not in {item.role_code.value for item in current_exploration.result.items}:
        raise _http(502, "Stored target role is invalid")
    return _read_target_role(row, exploration.id)
