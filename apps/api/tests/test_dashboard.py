from app.roadmap_provider import set_roadmap_provider
from test_roadmap import _proposal
from test_priorities import _setup


def test_dashboard_returns_a_safe_partial_state_before_market_analysis(client, db_session, persisted_profile):
    from app.role_exploration_schemas import RoleCode
    from app.target_role_service import select_target_role
    from test_target_role_service import _ready_profile

    _ready_profile(db_session, persisted_profile)
    select_target_role(db_session, persisted_profile.id, RoleCode.AI_PRODUCT_MANAGER)
    response = client.get(f"/api/v1/profiles/{persisted_profile.id}/dashboard")
    assert response.status_code == 200
    assert response.json()["market_ready"] is False
    assert response.json()["top_requirements"] == []


def test_dashboard_aggregates_current_market_gaps_priorities_and_progress(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class Provider:
        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            return _proposal(priorities)

    set_roadmap_provider(Provider())
    try:
        roadmap = client.post(f"/api/v1/profiles/{profile.id}/roadmap").json()
    finally:
        set_roadmap_provider(None)
    task_id = roadmap["weeks"][0]["tasks"][0]["id"]
    assert client.patch(f"/api/v1/roadmap-tasks/{task_id}", json={"status": "DONE"}).status_code == 200
    response = client.get(f"/api/v1/profiles/{profile.id}/dashboard")
    assert response.status_code == 200, response.text
    payload = response.json()
    assert payload["target_role"]["role_code"] == "AI_PRODUCT_MANAGER"
    assert payload["market_ready"] is True
    assert payload["jd_sample_count"] == 3
    assert payload["top_requirements"]
    assert all(item["category"] == "CAPABILITY" for item in payload["top_requirements"])
    assert payload["top_gaps"]
    assert payload["confirmed_priorities"]
    assert payload["progress_ratio"] == 0.25
    assert payload["replan_available"] is True
