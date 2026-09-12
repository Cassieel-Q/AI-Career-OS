from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import CareerPreference, UserProfile
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
