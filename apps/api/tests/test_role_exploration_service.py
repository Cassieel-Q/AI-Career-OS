from uuid import uuid4

import pytest
from fastapi import HTTPException
from sqlalchemy.exc import SQLAlchemyError

from app import models
from app.profile_schemas import CareerPreferencePriority, ProfileStatus
from app.role_exploration_provider import set_role_exploration_provider
from app.role_exploration_provider import (
    RoleExplorationProviderConnectionError,
    RoleExplorationProviderInvalidResponseError,
    RoleExplorationProviderNotConfiguredError,
    RoleExplorationProviderTimeoutError,
)
from app.role_exploration_schemas import ExplorationLevel, RoleCode, RoleExplorationProviderItem, RoleExplorationProviderPayload
from app.role_exploration_service import create_role_exploration, get_role_exploration


def _payload(evidence):
    return RoleExplorationProviderPayload(items=[
        RoleExplorationProviderItem(role_code=code, level=ExplorationLevel.POSSIBLE,
                                    reasons=["Grounded reason"], evidence_refs=[evidence], preference_refs=[])
        for code in RoleCode
    ])


class _Provider:
    def __init__(self, payload): self.payload = payload
    def explore(self, context): return self.payload


def _confirmed_with_preferences(db_session, persisted_profile):
    persisted_profile.status = ProfileStatus.CONFIRMED.value
    pref = models.CareerPreference(
        profile_id=persisted_profile.id,
        priority_1=CareerPreferencePriority.CURRENT_FIT.value,
        priority_2=CareerPreferencePriority.LONG_TERM_GROWTH.value,
        weekly_hours=10,
    )
    db_session.add(pref)
    db_session.commit()
    db_session.refresh(persisted_profile)
    return pref


def test_create_upserts_snapshot_without_mutating_sources(db_session, persisted_profile):
    _confirmed_with_preferences(db_session, persisted_profile)
    evidence = persisted_profile.skills[0].id
    set_role_exploration_provider(_Provider(_payload(evidence)))
    try:
        first = create_role_exploration(db_session, persisted_profile.id)
        second = create_role_exploration(db_session, persisted_profile.id)
        assert first.profile_id == second.profile_id == persisted_profile.id
        assert db_session.query(models.RoleExploration).filter_by(profile_id=persisted_profile.id).count() == 1
        assert db_session.get(models.UserProfile, persisted_profile.id).status == ProfileStatus.CONFIRMED.value
    finally:
        set_role_exploration_provider(None)


def test_create_requires_confirmed_profile_and_preferences(db_session, persisted_profile):
    with pytest.raises(HTTPException) as exc:
        create_role_exploration(db_session, persisted_profile.id)
    assert exc.value.status_code == 409


def test_get_missing_snapshot_is_404(db_session, persisted_profile):
    _confirmed_with_preferences(db_session, persisted_profile)
    with pytest.raises(HTTPException) as exc:
        get_role_exploration(db_session, persisted_profile.id)
    assert exc.value.status_code == 404


def test_get_revalidates_persisted_snapshot(db_session, persisted_profile):
    _confirmed_with_preferences(db_session, persisted_profile)
    evidence = persisted_profile.skills[0].id
    set_role_exploration_provider(_Provider(_payload(evidence)))
    try:
        created = create_role_exploration(db_session, persisted_profile.id)
        loaded = get_role_exploration(db_session, persisted_profile.id)
        assert loaded.id == created.id
        row = db_session.query(models.RoleExploration).filter_by(profile_id=persisted_profile.id).one()
        tampered = dict(row.result)
        tampered["items"] = [dict(item) for item in row.result["items"]]
        tampered["items"][0]["role_name"] = "tampered"
        row.result = tampered
        db_session.commit()
        with pytest.raises(HTTPException) as exc:
            get_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502
    finally:
        set_role_exploration_provider(None)


def test_get_rejects_provider_shaped_stored_json_without_result_envelope(db_session, persisted_profile):
    _confirmed_with_preferences(db_session, persisted_profile)
    evidence = persisted_profile.skills[0].id
    set_role_exploration_provider(_Provider(_payload(evidence)))
    try:
        create_role_exploration(db_session, persisted_profile.id)
    finally:
        set_role_exploration_provider(None)
    row = db_session.query(models.RoleExploration).filter_by(profile_id=persisted_profile.id).one()
    row.result = {"items": row.result["items"]}
    db_session.commit()
    with pytest.raises(HTTPException) as exc:
        get_role_exploration(db_session, persisted_profile.id)
    assert exc.value.status_code == 502


@pytest.mark.parametrize(
    "provider_error, expected_status",
    [
        (RoleExplorationProviderNotConfiguredError("missing"), 503),
        (RoleExplorationProviderConnectionError("offline"), 503),
        (RoleExplorationProviderInvalidResponseError("bad json"), 502),
        (RoleExplorationProviderTimeoutError("slow"), 504),
    ],
)
def test_provider_failures_map_to_stable_http_errors(
    db_session, persisted_profile, provider_error, expected_status
):
    _confirmed_with_preferences(db_session, persisted_profile)

    class FailingProvider:
        def explore(self, context):
            raise provider_error

    set_role_exploration_provider(FailingProvider())
    try:
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == expected_status
        assert str(provider_error) not in str(exc.value.detail)
    finally:
        set_role_exploration_provider(None)


def test_invalid_references_and_market_claims_are_rejected_before_persisting(
    db_session, persisted_profile
):
    _confirmed_with_preferences(db_session, persisted_profile)
    evidence = persisted_profile.skills[0].id
    payload = _payload(evidence).model_dump(mode="json")
    payload["items"][0]["evidence_refs"] = [str(uuid4())]

    set_role_exploration_provider(_Provider(payload))
    try:
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502
        assert db_session.query(models.RoleExploration).count() == 0

        payload["items"][0]["evidence_refs"] = [str(evidence)]
        payload["items"][0]["reasons"] = ["There is a 70% hiring probability"]
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502
    finally:
        set_role_exploration_provider(None)


def test_invalid_preference_reference_and_recommendation_cap_are_rejected(
    db_session, persisted_profile
):
    _confirmed_with_preferences(db_session, persisted_profile)
    payload = _payload(persisted_profile.skills[0].id).model_dump(mode="json")
    payload["items"][0]["preference_refs"] = ["COMPENSATION"]
    set_role_exploration_provider(_Provider(payload))
    try:
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502

        for item in payload["items"][:4]:
            item["preference_refs"] = []
            item["level"] = "RECOMMENDED"
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502
    finally:
        set_role_exploration_provider(None)


@pytest.mark.parametrize(
    "mutator",
    [
        lambda payload: payload["items"].pop(),
        lambda payload: payload["items"].__setitem__(1, payload["items"][0]),
        lambda payload: payload["items"].__setitem__(0, {**payload["items"][0], "role_code": "UNKNOWN_ROLE"}),
        lambda payload: payload["items"].__setitem__(0, {**payload["items"][0], "level": "INVALID"}),
    ],
)
def test_role_set_and_level_validation_returns_502(db_session, persisted_profile, mutator):
    _confirmed_with_preferences(db_session, persisted_profile)
    payload = _payload(persisted_profile.skills[0].id).model_dump(mode="json")
    mutator(payload)
    set_role_exploration_provider(_Provider(payload))
    try:
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 502
    finally:
        set_role_exploration_provider(None)


def test_persistence_failure_rolls_back_and_maps_to_503(db_session, persisted_profile, monkeypatch):
    _confirmed_with_preferences(db_session, persisted_profile)
    set_role_exploration_provider(_Provider(_payload(persisted_profile.skills[0].id)))
    def fail_commit():
        raise SQLAlchemyError("database internals")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    try:
        with pytest.raises(HTTPException) as exc:
            create_role_exploration(db_session, persisted_profile.id)
        assert exc.value.status_code == 503
        assert "database internals" not in str(exc.value.detail)
    finally:
        set_role_exploration_provider(None)
