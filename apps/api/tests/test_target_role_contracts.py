from datetime import datetime, timezone
from uuid import uuid4

import pytest
from pydantic import ValidationError

from app import models
from app.role_exploration_schemas import RoleCode
from app.target_role_schemas import TargetRoleInput, TargetRoleRead


def test_target_role_input_accepts_all_supported_codes_and_rejects_unknown_keys() -> None:
    for role_code in RoleCode:
        payload = TargetRoleInput.model_validate({"role_code": role_code.value})
        assert payload.role_code is role_code

    with pytest.raises(ValidationError):
        TargetRoleInput.model_validate({"role_code": "NOT_A_SUPPORTED_ROLE"})
    with pytest.raises(ValidationError):
        TargetRoleInput.model_validate(
            {"role_code": RoleCode.AI_PRODUCT_MANAGER.value, "role_name": "forged"}
        )


def test_target_role_read_contains_catalog_binding_and_serializes() -> None:
    exploration_id = uuid4()
    payload = TargetRoleRead(
        id=uuid4(),
        profile_id=uuid4(),
        role_code=RoleCode.AI_APPLICATION_ENGINEER,
        role_name="AI Application Engineer",
        role_profile_version="v1",
        role_exploration_id=exploration_id,
        selected_at=datetime.now(timezone.utc),
        updated_at=datetime.now(timezone.utc),
    )

    assert payload.model_dump(mode="json")["role_exploration_id"] == str(exploration_id)
    assert payload.role_code is RoleCode.AI_APPLICATION_ENGINEER


def test_target_role_model_is_one_to_one_with_profile_and_exploration() -> None:
    profile_relationship = models.UserProfile.target_role.property
    assert profile_relationship.uselist is False
    assert models.TargetRole.__tablename__ == "target_roles"
    assert models.TargetRole.__table__.c.profile_id.unique is True
    assert models.TargetRole.__table__.c.role_exploration_id.unique is True

    foreign_keys = {
        (foreign_key.target_fullname, foreign_key.ondelete)
        for column_name in ("profile_id", "role_exploration_id")
        for foreign_key in models.TargetRole.__table__.c[column_name].foreign_keys
    }
    assert ("user_profiles.id", "CASCADE") in foreign_keys
    assert ("role_explorations.id", "CASCADE") in foreign_keys
