from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError
from sqlalchemy import create_engine, inspect

from app.database import Base
from app.models import RoleExploration, UserProfile
from app.profile_schemas import CareerPreferencePriority
from app.role_exploration_schemas import (
    CodingIntensity,
    EntryBarrier,
    ExplorationLevel,
    RoleCode,
    RoleExplorationItem,
    RoleExplorationProviderItem,
    RoleExplorationProviderPayload,
    RoleExplorationRead,
    RoleExplorationRequest,
    RoleExplorationResult,
)
from app.role_profiles import ROLE_PROFILE_BY_CODE, ROLE_PROFILE_VERSION, ROLE_PROFILES


def _provider_item(role_code: RoleCode, *, level: ExplorationLevel = ExplorationLevel.POSSIBLE) -> RoleExplorationProviderItem:
    return RoleExplorationProviderItem(
        role_code=role_code,
        level=level,
        reasons=["Grounded reason"],
        concerns=[],
        evidence_refs=[uuid4()],
        preference_refs=[],
    )


def _result_item(role_code: RoleCode, *, level: ExplorationLevel = ExplorationLevel.POSSIBLE) -> RoleExplorationItem:
    return RoleExplorationItem(
        role_code=role_code,
        role_name=ROLE_PROFILE_BY_CODE[role_code].display_name,
        level=level,
        reasons=["Grounded reason"],
        concerns=[],
        evidence_refs=[uuid4()],
        preference_refs=[],
    )


def test_role_catalog_is_exactly_six_codes_and_v1() -> None:
    assert ROLE_PROFILE_VERSION == "v1"
    assert len(ROLE_PROFILES) == 6
    assert set(ROLE_PROFILE_BY_CODE) == set(RoleCode)
    assert {profile.role_code for profile in ROLE_PROFILES} == set(RoleCode)


def test_strict_provider_payload_and_bounded_references() -> None:
    evidence = uuid4()
    item = RoleExplorationProviderItem(
        role_code=RoleCode.AI_PRODUCT_MANAGER,
        level=ExplorationLevel.RECOMMENDED,
        reasons=["Product discovery experience"],
        concerns=["May need domain context"],
        evidence_refs=[evidence],
        preference_refs=[CareerPreferencePriority.CURRENT_FIT],
    )
    payload = RoleExplorationProviderPayload(
        items=[item] + [_provider_item(role_code) for role_code in list(RoleCode)[1:]]
    )
    assert payload.items[0].evidence_refs == [evidence]
    with pytest.raises(ValidationError):
        RoleExplorationProviderItem(
            role_code=RoleCode.AI_PRODUCT_MANAGER,
            level=ExplorationLevel.POSSIBLE,
            reasons=[],
            concerns=[],
            evidence_refs=[evidence],
            unknown="reject",
        )


@pytest.mark.parametrize("model", [RoleExplorationProviderItem, RoleExplorationItem])
@pytest.mark.parametrize("field", ["reasons", "concerns"])
def test_role_exploration_text_lists_reject_blank_after_strip(model, field: str) -> None:
    kwargs = {
        "role_code": RoleCode.AI_PRODUCT_MANAGER,
        "level": ExplorationLevel.POSSIBLE,
        "reasons": ["Grounded reason"],
        "concerns": [],
        "evidence_refs": [uuid4()],
    }
    if model is RoleExplorationItem:
        kwargs["role_name"] = "AI Product Manager"
    kwargs[field] = ["   "]
    with pytest.raises(ValidationError):
        model(**kwargs)


def test_result_requires_exact_role_set_without_duplicates_and_caps_recommendations() -> None:
    items = [_result_item(role_code) for role_code in RoleCode]
    result = RoleExplorationResult(role_profile_version=ROLE_PROFILE_VERSION, items=items)
    assert {item.role_code for item in result.items} == set(RoleCode)

    with pytest.raises(ValidationError):
        RoleExplorationResult(role_profile_version=ROLE_PROFILE_VERSION, items=items[:-1] + [items[0]])

    too_many_recommended = [
        _result_item(role_code, level=ExplorationLevel.RECOMMENDED if index < 4 else ExplorationLevel.POSSIBLE)
        for index, role_code in enumerate(RoleCode)
    ]
    with pytest.raises(ValidationError):
        RoleExplorationResult(role_profile_version=ROLE_PROFILE_VERSION, items=too_many_recommended)


def test_result_and_read_models_serialize_uuid_fields_and_recommendation_level() -> None:
    evidence = uuid4()
    item = RoleExplorationItem(
        role_code=RoleCode.AI_PRODUCT_MANAGER,
        role_name="AI Product Manager",
        level=ExplorationLevel.RECOMMENDED,
        reasons=["Grounded reason"],
        concerns=[],
        evidence_refs=[evidence],
        preference_refs=[],
    )
    result = RoleExplorationResult(
        role_profile_version=ROLE_PROFILE_VERSION,
        items=[item] + [_result_item(role_code) for role_code in list(RoleCode)[1:]],
    )
    read = RoleExplorationRead(
        id=uuid4(),
        profile_id=uuid4(),
        role_profile_version=ROLE_PROFILE_VERSION,
        result=result,
        created_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )
    assert read.model_dump(mode="json")["result"]["items"][0]["evidence_refs"] == [str(evidence)]


def test_request_rejects_unknown_keys() -> None:
    with pytest.raises(ValidationError):
        RoleExplorationRequest(profile_id=uuid4(), extra="reject")


def test_role_exploration_model_relationship_and_unique_profile_id() -> None:
    assert UserProfile.role_exploration.property.uselist is False
    assert RoleExploration.profile.property.back_populates == "role_exploration"
    assert RoleExploration.__table__.c.profile_id.unique is True
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    assert "role_explorations" in inspect(engine).get_table_names()
