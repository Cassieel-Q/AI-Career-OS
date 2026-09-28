import json
from types import SimpleNamespace
from uuid import UUID, uuid4

from app import models
from app.roadmap_provider import OpenAIRoadmapProvider, RoadmapProviderAuthenticationError, set_roadmap_provider
from app.roadmap_schemas import RoadmapProposal, RoadmapTaskProposal, RoadmapWeekProposal
from test_priorities import _setup


def _proposal(priorities, minutes=30):
    gap_id = UUID(priorities[0]["gap_id"])
    return RoadmapProposal(weeks=[RoadmapWeekProposal(
        week_number=index,
        objective=f"Week {index} objective",
        focus_gap_ids=[gap_id],
        measurable_outcome=f"Week {index} outcome",
        tasks=[RoadmapTaskProposal(
            title=f"Complete exercise {index}-{task_index}",
            objective="Produce a reviewable artifact",
            estimated_minutes=minutes,
            related_gap_id=gap_id,
            completion_criteria="Artifact is saved and reviewed",
        ) for task_index in range(1, 6 if minutes >= 600 else 2)],
    ) for index in range(1, 5)])


def test_four_week_roadmap_is_persisted_with_actionable_tasks(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)
    captured = {}

    class Provider:
        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            captured["priorities"] = priorities
            captured["remaining_context"] = remaining_context
            return _proposal(priorities)

    set_roadmap_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
    finally:
        set_roadmap_provider(None)
    assert response.status_code == 200, response.text
    payload = response.json()
    assert len(payload["weeks"]) == 4
    assert all(week["tasks"][0]["estimated_minutes"] == 30 for week in payload["weeks"])
    assert payload["progress_ratio"] == 0
    assert client.get(f"/api/v1/profiles/{profile.id}/roadmap").status_code == 200
    assert {item["capability_name"] for item in captured["priorities"]} == {"Technical capability", "Product execution"}
    assert captured["priorities"][0]["atomic_requirements"]
    assert all("raw_text" not in item for item in captured["priorities"])
    assert captured["remaining_context"]["profile_evidence"]
    assert captured["remaining_context"]["capability_count"] == 2
    assert "job_descriptions" not in captured["remaining_context"]


def test_valid_json_object_from_provider_is_strictly_parsed_and_persisted(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class StructuredClient:
        class _Completions:
            @staticmethod
            def create(**request):
                gap_id = json.loads(request["messages"][1]["content"])["priorities"][0]["gap_id"]
                return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({
                    "weeks": [{
                        "week_number": week_number,
                        "objective": f"Objective {week_number}",
                        "focus_gap_ids": [gap_id],
                        "measurable_outcome": f"Outcome {week_number}",
                        "tasks": [{
                            "title": f"Task {week_number}",
                            "objective": "Create a reviewable artifact",
                            "estimated_minutes": 30,
                            "related_gap_id": gap_id,
                            "completion_criteria": "Artifact is saved",
                        }],
                    } for week_number in range(1, 5)]
                })))] )

        chat = SimpleNamespace(completions=_Completions())

    set_roadmap_provider(OpenAIRoadmapProvider(client=StructuredClient()))
    try:
        response = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
    finally:
        set_roadmap_provider(None)

    assert response.status_code == 200, response.text
    assert [week["week_number"] for week in response.json()["weeks"]] == [1, 2, 3, 4]
    assert db_session.query(models.Roadmap).filter_by(profile_id=profile.id, status="VALID").count() == 1


def test_roadmap_rejects_plan_over_weekly_budget(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class Provider:
        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            return _proposal(priorities, minutes=600)

    set_roadmap_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
    finally:
        set_roadmap_provider(None)
    assert response.status_code == 422
    assert "weekly budget" in response.json()["detail"]


def test_roadmap_rejects_untrusted_week_focus_gap_reference(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class Provider:
        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            proposal = _proposal(priorities)
            return proposal.model_copy(update={
                "weeks": [week.model_copy(update={"focus_gap_ids": [uuid4()]}) for week in proposal.weeks],
            })

    set_roadmap_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
    finally:
        set_roadmap_provider(None)
    assert response.status_code == 502
    assert "无法核验" in response.json()["detail"]


def test_roadmap_requires_gap_analysis(client, db_session, persisted_profile):
    from app.profile_service import confirm_profile
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    response = client.post(f"/api/v1/profiles/{persisted_profile.id}/roadmap")
    assert response.status_code == 409


def test_roadmap_provider_authentication_failure_is_classified_for_retry(client, db_session, persisted_profile):
    profile = _setup(client, db_session, persisted_profile)

    class Provider:
        def plan(self, *, target_role, weekly_hours, priorities, remaining_context=None):
            raise RoadmapProviderAuthenticationError("provider authentication failed")

    set_roadmap_provider(Provider())
    try:
        response = client.post(f"/api/v1/profiles/{profile.id}/roadmap")
    finally:
        set_roadmap_provider(None)
    assert response.status_code == 502
    assert "认证失败" in response.json()["detail"]
