from uuid import uuid4

from app import models
from app.profile_schemas import CareerPreferencePriority, ProfileStatus
from app.role_exploration_provider import set_role_exploration_provider
from app.role_exploration_schemas import ExplorationLevel, RoleCode, RoleExplorationProviderItem, RoleExplorationProviderPayload
from app.role_exploration_service import create_role_exploration


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
    payload = RoleExplorationProviderPayload(
        items=[
            RoleExplorationProviderItem(
                role_code=role_code,
                level=ExplorationLevel.POSSIBLE,
                reasons=["Grounded reason"],
                evidence_refs=[persisted_profile.skills[0].id],
            )
            for role_code in RoleCode
        ]
    )

    class Provider:
        def explore(self, context):
            return payload

    set_role_exploration_provider(Provider())
    try:
        return create_role_exploration(db_session, persisted_profile.id)
    finally:
        set_role_exploration_provider(None)


def test_target_role_put_rejects_unknown_request_keys(client):
    response = client.put(
        f"/api/v1/profiles/{uuid4()}/target-role",
        json={"role_code": RoleCode.AI_PRODUCT_MANAGER.value, "role_name": "forged"},
    )
    assert response.status_code == 422


def test_target_role_get_missing_selection_is_404(client, db_session, persisted_profile):
    _ready_profile(db_session, persisted_profile)

    response = client.get(f"/api/v1/profiles/{persisted_profile.id}/target-role")

    assert response.status_code == 404
    assert response.json()["detail"] == "Target role has not been selected"


def test_target_role_put_and_get_use_canonical_role_fields(client, db_session, persisted_profile):
    exploration = _ready_profile(db_session, persisted_profile)

    put_response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/target-role",
        json={"role_code": RoleCode.AI_SOLUTION_CONSULTANT.value},
    )
    get_response = client.get(f"/api/v1/profiles/{persisted_profile.id}/target-role")

    assert put_response.status_code == 200
    assert get_response.status_code == 200
    payload = get_response.json()
    assert payload["role_code"] == RoleCode.AI_SOLUTION_CONSULTANT.value
    assert payload["role_name"] == "AI Solution Consultant"
    assert payload["role_profile_version"] == "v1"
    assert payload["role_exploration_id"] == str(exploration.id)


def test_target_role_put_requires_current_exploration(client, db_session, persisted_profile):
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

    response = client.put(
        f"/api/v1/profiles/{persisted_profile.id}/target-role",
        json={"role_code": RoleCode.AI_PRODUCT_MANAGER.value},
    )

    assert response.status_code == 409


def test_target_role_put_unknown_profile_is_404(client):
    response = client.put(
        f"/api/v1/profiles/{uuid4()}/target-role",
        json={"role_code": RoleCode.AI_PRODUCT_MANAGER.value},
    )

    assert response.status_code == 404
