from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.profile_schemas import CareerPreferencePriority, CareerPreferencesInput, ProfileStatus
from app.profile_service import upsert_career_preferences
from app.role_exploration_provider import set_role_exploration_provider
from app.role_exploration_schemas import ExplorationLevel, RoleCode, RoleExplorationProviderItem, RoleExplorationProviderPayload
from app.role_exploration_service import create_role_exploration
from app.target_role_service import get_target_role, select_target_role


def _exploration_payload(evidence):
    return RoleExplorationProviderPayload(
        items=[
            RoleExplorationProviderItem(
                role_code=role_code,
                level=ExplorationLevel.LOW_PRIORITY,
                reasons=["Grounded reason"],
                evidence_refs=[evidence],
            )
            for role_code in RoleCode
        ]
    )


class _Provider:
    def __init__(self, payload):
        self.payload = payload

    def explore(self, context):
        return self.payload


def _ready_profile(db_session, persisted_profile):
    persisted_profile.status = ProfileStatus.CONFIRMED.value
    db_session.add(
        models.CareerPreference(
            profile_id=persisted_profile.id,
            priority_1=CareerPreferencePriority.CURRENT_FIT.value,
            priority_2=CareerPreferencePriority.LONG_TERM_GROWTH.value,
            weekly_hours=10,
        )
    )
    db_session.commit()
    set_role_exploration_provider(_Provider(_exploration_payload(persisted_profile.skills[0].id)))
    try:
        exploration = create_role_exploration(db_session, persisted_profile.id)
    finally:
        set_role_exploration_provider(None)
    return exploration


def test_select_target_role_accepts_low_priority_and_derives_catalog_fields(db_session, persisted_profile):
    exploration = _ready_profile(db_session, persisted_profile)

    selected = select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_OPERATIONS)

    assert selected.profile_id == persisted_profile.id
    assert selected.role_code is RoleCode.AI_PRODUCT_OPERATIONS
    assert selected.role_name == "AI Product Operations"
    assert selected.role_profile_version == "v1"
    assert selected.role_exploration_id == exploration.id


def test_select_target_role_replaces_the_single_active_selection(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)

    first = select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    second = select_target_role(db_session, persisted_profile.id, RoleCode.LLM_ALGORITHM_ENGINEER)

    assert second.id == first.id
    assert second.role_code is RoleCode.LLM_ALGORITHM_ENGINEER
    assert db_session.query(models.TargetRole).filter_by(profile_id=persisted_profile.id).count() == 1


def test_get_target_role_returns_the_saved_selection(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    selected = select_target_role(db_session, persisted_profile.id, RoleCode.AI_DATA_ANALYST)

    loaded = get_target_role(db_session, persisted_profile.id)

    assert loaded.id == selected.id
    assert loaded.role_code is RoleCode.AI_DATA_ANALYST


def test_preference_invalidation_cascades_to_the_bound_target_role(db_session, persisted_profile):
    db_session.connection().exec_driver_sql("PRAGMA foreign_keys=ON")
    _ready_profile(db_session, persisted_profile)
    select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)

    upsert_career_preferences(
        db_session,
        persisted_profile.id,
        CareerPreferencesInput(
            priority_order=[CareerPreferencePriority.FAST_EMPLOYMENT, CareerPreferencePriority.LESS_CODING],
            weekly_hours=24,
        ),
    )

    assert db_session.query(models.RoleExploration).filter_by(profile_id=persisted_profile.id).count() == 0
    assert db_session.query(models.TargetRole).filter_by(profile_id=persisted_profile.id).count() == 0


def test_get_target_role_rejects_a_selection_bound_to_an_old_exploration(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)
    selected = select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    other_profile = models.UserProfile(status=ProfileStatus.CONFIRMED.value)
    db_session.add(other_profile)
    db_session.commit()
    old_exploration = models.RoleExploration(
        profile_id=other_profile.id,
        role_profile_version="v1",
        result={"role_profile_version": "v1", "items": []},
    )
    db_session.add(old_exploration)
    db_session.commit()
    row = db_session.query(models.TargetRole).filter_by(profile_id=persisted_profile.id).one()
    row.role_exploration_id = old_exploration.id
    db_session.commit()

    with pytest.raises(HTTPException) as exc:
        get_target_role(db_session, persisted_profile.id)

    assert exc.value.status_code == 409
    assert selected.role_exploration_id != row.role_exploration_id


def test_target_role_requires_confirmed_profile_and_current_exploration(db_session, persisted_profile):
    with pytest.raises(HTTPException) as exc:
        select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    assert exc.value.status_code == 409

    persisted_profile.status = ProfileStatus.CONFIRMED.value
    db_session.add(
        models.CareerPreference(
            profile_id=persisted_profile.id,
            priority_1=CareerPreferencePriority.CURRENT_FIT.value,
            priority_2=CareerPreferencePriority.LONG_TERM_GROWTH.value,
            weekly_hours=10,
        )
    )
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    assert exc.value.status_code == 409
    assert "Role exploration" in exc.value.detail


def test_get_target_role_missing_selection_is_404(db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)

    with pytest.raises(HTTPException) as exc:
        get_target_role(db_session, persisted_profile.id)

    assert exc.value.status_code == 404


def test_missing_profile_is_404(db_session):
    with pytest.raises(HTTPException) as exc:
        get_target_role(db_session, uuid4())
    assert exc.value.status_code == 404


def test_select_target_role_persistence_failure_maps_to_503(db_session, persisted_profile, monkeypatch):
    _ready_profile(db_session, persisted_profile)

    def fail_commit():
        raise SQLAlchemyError("database internals")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(HTTPException) as exc:
        select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)

    assert exc.value.status_code == 503
    assert "database internals" not in str(exc.value.detail)
