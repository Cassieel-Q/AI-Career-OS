from app.roadmap_provider import set_roadmap_provider
from test_roadmap import _proposal
from test_priorities import _setup


def test_task_progress_updates_without_invalidating_market_evidence(client, db_session, persisted_profile):
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
    updated = client.patch(f"/api/v1/roadmap-tasks/{task_id}", json={"status": "DONE"})
    assert updated.status_code == 200
    assert updated.json()["status"] == "DONE"
    reread = client.get(f"/api/v1/profiles/{profile.id}/roadmap")
    assert reread.json()["progress_ratio"] == 0.25
    assert db_session.query(__import__("app.models", fromlist=["MarketProfile"]).MarketProfile).one().status == "VALID"


def test_replan_creates_a_new_revision_and_preserves_prior_history(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class Provider:
        def __init__(self):
            self.contexts = []

        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            self.contexts.append(remaining_context)
            return _proposal(priorities)

    provider = Provider()
    set_roadmap_provider(provider)
    try:
        first = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
        task_id = first.json()["weeks"][0]["tasks"][0]["id"]
        assert client.patch(f"/api/v1/roadmap-tasks/{task_id}", json={"status": "DONE"}).status_code == 200
        second = client.post(f"/api/v1/profiles/{profile.id}/roadmap/replan", json={"remaining_weeks": 3})
    finally:
        set_roadmap_provider(None)
    assert first.status_code == 200
    assert second.status_code == 200, second.text
    assert second.json()["revision"] == 2
    assert provider.contexts[-1]["remaining_weeks"] == 3
    assert provider.contexts[-1]["completed_tasks"]
    from app import models
    roadmaps = db_session.query(models.Roadmap).order_by(models.Roadmap.revision).all()
    assert [row.status for row in roadmaps] == ["SUPERSEDED", "VALID"]
    assert roadmaps[0].weeks[0].tasks[0].status == "DONE"
