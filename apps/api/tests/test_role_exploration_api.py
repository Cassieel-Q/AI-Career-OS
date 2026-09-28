from uuid import uuid4

from app import models
from app.profile_schemas import CareerPreferencePriority, ProfileStatus
from app.role_exploration_provider import RoleExplorationProviderTimeoutError, set_role_exploration_provider


def _confirmed_profile(db_session, persisted_profile):
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
    return persisted_profile


def test_role_exploration_request_rejects_unknown_keys(client):
    response = client.post("/api/v1/role-explorations", json={"profile_id": str(uuid4()), "extra": 1})
    assert response.status_code == 422


def test_role_exploration_route_not_found(client):
    response = client.get(f"/api/v1/profiles/{uuid4()}/role-exploration")
    assert response.status_code == 404


def test_post_requires_confirmed_profile_and_saved_preferences(client, persisted_profile):
    response = client.post("/api/v1/role-explorations", json={"profile_id": str(persisted_profile.id)})
    assert response.status_code == 409


def test_post_timeout_maps_to_504(client, db_session, persisted_profile):
    _confirmed_profile(db_session, persisted_profile)

    class TimeoutProvider:
        def explore(self, context):
            raise RoleExplorationProviderTimeoutError("provider details")

    set_role_exploration_provider(TimeoutProvider())
    try:
        response = client.post("/api/v1/role-explorations", json={"profile_id": str(persisted_profile.id)})
    finally:
        set_role_exploration_provider(None)
    assert response.status_code == 504
    assert "provider details" not in response.text
