from __future__ import annotations

import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .profile_schemas import CareerPreferencePriority, ProfileStatus
from .role_exploration_provider import (
    RoleExplorationProviderError,
    RoleExplorationProviderConnectionError,
    RoleExplorationProviderInvalidResponseError,
    RoleExplorationProviderNotConfiguredError,
    RoleExplorationProviderTimeoutError,
    build_role_exploration_context,
    get_role_exploration_provider,
)
from .role_exploration_schemas import (
    RoleExplorationItem,
    RoleExplorationProviderPayload,
    RoleExplorationRead,
    RoleExplorationResult,
)
from .role_profiles import ROLE_PROFILE_BY_CODE, ROLE_PROFILE_VERSION


_MARKET_CLAIM = re.compile(
    r"(?:\b\d+(?:\.\d+)?\s*%|\b(?:percent(?:age)?|probability|probable|likelihood|chance|hiring|demand|salary|wage|market|job openings?|employment rate|growth rate)\b)",
    re.IGNORECASE,
)


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _preference_state(preference: models.CareerPreference) -> tuple[str, str, int]:
    return preference.priority_1, preference.priority_2, preference.weekly_hours


def _load_confirmed_profile(db: Session, profile_id: UUID) -> tuple[models.UserProfile, models.CareerPreference]:
    try:
        profile = db.execute(select(models.UserProfile).where(models.UserProfile.id == profile_id)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if profile is None:
        raise _http(404, "Profile not found")
    if profile.status != ProfileStatus.CONFIRMED.value:
        raise _http(409, "Role exploration requires a confirmed profile")
    try:
        preference = db.execute(select(models.CareerPreference).where(models.CareerPreference.profile_id == profile_id)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if preference is None:
        raise _http(409, "Career preferences are required before role exploration")
    return profile, preference


def _load_profile(db: Session, profile_id: UUID) -> models.UserProfile:
    try:
        profile = db.execute(select(models.UserProfile).where(models.UserProfile.id == profile_id)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if profile is None:
        raise _http(404, "Profile not found")
    return profile


def _validate_market_text(items: list[Any]) -> None:
    for item in items:
        for text in (*item.reasons, *item.concerns):
            if _MARKET_CLAIM.search(text):
                raise ValueError("market claims are not allowed")


def _validate_and_build_result(
    payload: Any,
    profile: models.UserProfile,
    preference: models.CareerPreference,
    *,
    stored: bool = False,
) -> RoleExplorationResult:
    # Provider payloads intentionally omit catalog-owned names/version.  A
    # persisted snapshot must contain the full result envelope, so never allow
    # a provider-shaped object to masquerade as valid stored JSON.
    has_result_envelope = isinstance(payload, RoleExplorationResult) or (
        isinstance(payload, dict) and "role_profile_version" in payload
    )
    if stored and not has_result_envelope:
        raise ValueError("stored role exploration was invalid")
    if has_result_envelope:
        try:
            result = payload if isinstance(payload, RoleExplorationResult) else RoleExplorationResult.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError("stored role exploration was invalid") from exc
        if result.role_profile_version != ROLE_PROFILE_VERSION:
            raise ValueError("stored role profile version is invalid")
        items = list(result.items)
    else:
        try:
            provider_payload = payload if isinstance(payload, RoleExplorationProviderPayload) else RoleExplorationProviderPayload.model_validate(payload)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ValueError("provider output was invalid") from exc
        items = list(provider_payload.items)
    codes = [item.role_code for item in items]
    if len(items) != 6 or len(set(codes)) != 6 or set(codes) != set(ROLE_PROFILE_BY_CODE):
        raise ValueError("provider output did not contain the supported role set")
    if sum(item.level.value == "RECOMMENDED" for item in items) > 3:
        raise ValueError("provider output exceeded recommendation limit")
    _validate_market_text(items)

    evidence_ids = {
        child.id
        for collection in (profile.education, profile.skills, profile.experiences, profile.certifications)
        for child in collection
    }
    preference_values = {CareerPreferencePriority(preference.priority_1), CareerPreferencePriority(preference.priority_2)}
    result_items: list[RoleExplorationItem] = []
    for item in items:
        if any(ref not in evidence_ids for ref in item.evidence_refs):
            raise ValueError("provider output contained an invalid evidence reference")
        if any(ref not in preference_values for ref in item.preference_refs):
            raise ValueError("provider output contained an invalid preference reference")
        expected_name = ROLE_PROFILE_BY_CODE[item.role_code].display_name
        if isinstance(item, RoleExplorationItem) and item.role_name != expected_name:
            raise ValueError("stored role name is invalid")
        result_items.append(RoleExplorationItem(role_code=item.role_code, role_name=expected_name, level=item.level,
                                                reasons=item.reasons, concerns=item.concerns,
                                                evidence_refs=item.evidence_refs, preference_refs=item.preference_refs))
    try:
        return RoleExplorationResult(role_profile_version=ROLE_PROFILE_VERSION, items=result_items)
    except (ValidationError, ValueError) as exc:
        raise ValueError("provider output failed deterministic validation") from exc


def _read_row(row: models.RoleExploration, profile: models.UserProfile, preference: models.CareerPreference) -> RoleExplorationRead:
    try:
        result = _validate_and_build_result(row.result, profile, preference, stored=True)
        if row.role_profile_version != ROLE_PROFILE_VERSION:
            raise ValueError("stored role profile version is invalid")
        return RoleExplorationRead(
            id=row.id,
            profile_id=row.profile_id,
            role_profile_version=ROLE_PROFILE_VERSION,
            result=result,
            created_at=row.created_at,
            updated_at=row.updated_at,
        )
    except (ValidationError, ValueError, TypeError) as exc:
        raise _http(502, "Stored role exploration is invalid") from exc


def create_role_exploration(db: Session, profile_id: UUID) -> RoleExplorationRead:
    profile, preference = _load_confirmed_profile(db, profile_id)
    requested_preference_state = _preference_state(preference)
    try:
        context = build_role_exploration_context(profile, preference)
        payload = get_role_exploration_provider().explore(context)
    except HTTPException:
        raise
    except RoleExplorationProviderTimeoutError as exc:
        raise _http(504, "Role exploration provider timed out") from exc
    except RoleExplorationProviderNotConfiguredError as exc:
        raise _http(503, "Role exploration provider is not configured") from exc
    except (RoleExplorationProviderInvalidResponseError, ValueError, ValidationError, TypeError) as exc:
        raise _http(502, "Role exploration provider returned invalid output") from exc
    except RoleExplorationProviderConnectionError as exc:
        raise _http(503, "Role exploration provider is unavailable") from exc
    except RoleExplorationProviderError as exc:
        raise _http(503, "Role exploration provider is unavailable") from exc
    except Exception as exc:
        raise _http(503, "Role exploration provider is unavailable") from exc
    try:
        current_preference = db.execute(
            select(models.CareerPreference)
            .where(models.CareerPreference.profile_id == profile_id)
            .execution_options(populate_existing=True)
            .with_for_update()
        ).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if current_preference is None or _preference_state(current_preference) != requested_preference_state:
        raise _http(
            409,
            "Career preferences changed during role exploration; please generate again.",
        )
    try:
        result = _validate_and_build_result(payload, profile, current_preference)
    except (ValidationError, ValueError, TypeError) as exc:
        raise _http(502, "Role exploration provider returned invalid output") from exc
    try:
        row = db.execute(select(models.RoleExploration).where(models.RoleExploration.profile_id == profile_id).with_for_update()).scalar_one_or_none()
        now = datetime.now(timezone.utc)
        data = result.model_dump(mode="json")
        if row is None:
            row = models.RoleExploration(profile_id=profile_id, role_profile_version=ROLE_PROFILE_VERSION, result=data, created_at=now, updated_at=now)
            db.add(row)
        else:
            row.role_profile_version = ROLE_PROFILE_VERSION
            row.result = data
            row.updated_at = now
        db.commit()
        db.refresh(row)
        return RoleExplorationRead(id=row.id, profile_id=row.profile_id, role_profile_version=ROLE_PROFILE_VERSION, result=result, created_at=row.created_at, updated_at=row.updated_at)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc


def get_role_exploration(db: Session, profile_id: UUID) -> RoleExplorationRead:
    profile = _load_profile(db, profile_id)
    if profile.status != ProfileStatus.CONFIRMED.value:
        raise _http(409, "Role exploration requires a confirmed profile")
    try:
        preference = db.execute(select(models.CareerPreference).where(models.CareerPreference.profile_id == profile_id)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if preference is None:
        raise _http(409, "Career preferences are required before role exploration")
    try:
        row = db.execute(select(models.RoleExploration).where(models.RoleExploration.profile_id == profile_id)).scalar_one_or_none()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Role exploration persistence failed") from exc
    if row is None:
        raise _http(404, "Role exploration has not been generated")
    return _read_row(row, profile, preference)
