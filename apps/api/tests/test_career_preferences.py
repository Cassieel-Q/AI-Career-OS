from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect
from sqlalchemy.exc import SQLAlchemyError

from app.database import Base
from app import models
from app.models import CareerPreference, UserProfile
from app.profile_service import upsert_career_preferences
from app.profile_schemas import (
    CareerPreferencesInput,
    CareerPreferencePriority,
    CareerPreferencesRead,
)


def test_preferences_accept_two_ordered_priorities_and_hours() -> None:
    payload = CareerPreferencesInput(
        priority_order=["FAST_EMPLOYMENT", "CURRENT_FIT"],
        weekly_hours=20,
    )
    assert payload.priority_order == [
        CareerPreferencePriority.FAST_EMPLOYMENT,
        CareerPreferencePriority.CURRENT_FIT,
    ]
    assert payload.weekly_hours == 20


@pytest.mark.parametrize(
    "value",
    [[], ["FAST_EMPLOYMENT"], ["FAST_EMPLOYMENT", "CURRENT_FIT", "COMPENSATION"]],
)
def test_preferences_require_exactly_two_priorities(value: list[str]) -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=value, weekly_hours=20)


def test_preferences_reject_duplicate_or_unknown_priority() -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=["CURRENT_FIT", "CURRENT_FIT"], weekly_hours=20)
    with pytest.raises(ValidationError):
        CareerPreferencesInput(priority_order=["CURRENT_FIT", "UNKNOWN"], weekly_hours=20)


@pytest.mark.parametrize("hours", [0, 61, 20.0, "20"])
def test_preferences_require_strict_integer_hours_in_range(hours: object) -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(
            priority_order=["CURRENT_FIT", "COMPENSATION"],
            weekly_hours=hours,
        )


def test_preferences_reject_extra_fields() -> None:
    with pytest.raises(ValidationError):
        CareerPreferencesInput(
            priority_order=["CURRENT_FIT", "COMPENSATION"], weekly_hours=20, extra="nope"
        )


def test_preferences_read_exposes_stored_order() -> None:
    result = CareerPreferencesRead(
        id=uuid4(),
        profile_id=uuid4(),
        priority_order=["COMPENSATION", "LESS_CODING"],
        weekly_hours=12,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert result.priority_order[0] is CareerPreferencePriority.COMPENSATION


def test_preferences_read_maps_orm_priority_columns() -> None:
    preference = CareerPreference(
        id=uuid4(),
        profile_id=uuid4(),
        priority_1="COMPENSATION",
        priority_2="LESS_CODING",
        weekly_hours=12,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    result = CareerPreferencesRead.model_validate(preference)
    assert result.priority_order == [
        CareerPreferencePriority.COMPENSATION,
        CareerPreferencePriority.LESS_CODING,
    ]


def test_career_preference_model_is_one_to_one_and_metadata_creates_table() -> None:
    assert UserProfile.career_preference.property.uselist is False
    assert CareerPreference.profile.property.back_populates == "career_preference"
    assert CareerPreference.__table__.c.profile_id.unique is True

    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert "career_preferences" in inspect(engine).get_table_names()


def test_preferences_accept_weekly_hours_boundaries() -> None:
    assert CareerPreferencesInput(
        priority_order=["FAST_EMPLOYMENT", "CURRENT_FIT"], weekly_hours=1
    ).weekly_hours == 1
    assert CareerPreferencesInput(
        priority_order=["FAST_EMPLOYMENT", "CURRENT_FIT"], weekly_hours=60
    ).weekly_hours == 60


def test_missing_profile_preferences_returns_404(client) -> None:
    response = client.put(
        f"/api/v1/profiles/{uuid4()}/preferences",
        json={"priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"], "weekly_hours": 20},
    )
    assert response.status_code == 404


def test_draft_profile_preferences_returns_conflict(client, persisted_profile) -> None:
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"], "weekly_hours": 20},
    )
    assert response.status_code == 409
    assert response.json()["detail"] == "Career preferences require a confirmed profile"


def test_profile_without_preferences_returns_null_preferences(client, persisted_profile) -> None:
    response = client.get(f"/api/v1/profiles/{persisted_profile.id}")
    assert response.status_code == 200
    assert response.json()["preferences"] is None


def test_confirmed_profile_can_create_and_read_preferences(client, persisted_profile) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"], "weekly_hours": 20},
    )
    assert response.status_code == 200
    assert response.json()["priority_order"] == ["FAST_EMPLOYMENT", "CURRENT_FIT"]
    read_response = client.get(f"/api/v1/profiles/{persisted_profile.id}")
    assert read_response.json()["preferences"]["weekly_hours"] == 20


@pytest.mark.parametrize("weekly_hours", [1, 60])
def test_confirmed_profile_accepts_weekly_hours_boundaries(
    client, persisted_profile, weekly_hours: int
) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={
            "priority_order": ["FAST_EMPLOYMENT", "CURRENT_FIT"],
            "weekly_hours": weekly_hours,
        },
    )
    assert response.status_code == 200
    assert response.json()["weekly_hours"] == weekly_hours


def test_second_put_updates_one_row_and_keeps_profile_facts(
    client, db_session, persisted_profile
) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    before = client.get(f"/api/v1/profiles/{persisted_profile.id}").json()
    first = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["COMPENSATION", "LESS_CODING"], "weekly_hours": 12},
    ).json()
    second = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["CURRENT_FIT", "LONG_TERM_GROWTH"], "weekly_hours": 30},
    ).json()
    assert second["id"] == first["id"]
    after = client.get(f"/api/v1/profiles/{persisted_profile.id}").json()
    for fact_collection in ("education", "skills", "experiences", "certifications"):
        assert after[fact_collection] == before[fact_collection]
    assert (
        db_session.query(models.CareerPreference)
        .filter_by(profile_id=persisted_profile.id)
        .count()
        == 1
    )


def test_invalid_preferences_request_returns_422(client, persisted_profile) -> None:
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/confirm").status_code == 200
    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/preferences",
        json={"priority_order": ["CURRENT_FIT", "CURRENT_FIT"], "weekly_hours": 20},
    )
    assert response.status_code == 422


def test_preference_persistence_failure_returns_safe_503(
    db_session, persisted_profile, monkeypatch
) -> None:
    persisted_profile.status = "CONFIRMED"
    db_session.commit()

    def fail_commit() -> None:
        raise SQLAlchemyError("database details must not leak")

    monkeypatch.setattr(db_session, "commit", fail_commit)
    with pytest.raises(HTTPException) as error:
        upsert_career_preferences(
            db_session,
            persisted_profile.id,
            CareerPreferencesInput(
                priority_order=["CURRENT_FIT", "COMPENSATION"], weekly_hours=20
            ),
        )
    assert error.value.status_code == 503
    assert error.value.detail == "Career preferences persistence failed"
    assert "database details" not in error.value.detail
