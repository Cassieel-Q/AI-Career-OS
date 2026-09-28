"""Empty interview debrief must not save or advance mission state."""
from __future__ import annotations

from uuid import UUID

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app import models
from app.mission_provider import set_mission_provider
from app.mission_schemas import MissionOutcomeCreate
from tests.test_integrated_mission_api import StubIntegratedProvider


def test_mission_outcome_schema_rejects_empty_debrief():
    with pytest.raises(ValidationError) as exc:
        MissionOutcomeCreate.model_validate(
            {
                "application_status": "INTERVIEWING",
                "interview_round": "",
                "questions_asked": [],
                "where_struggled": "",
                "interviewer_feedback": "",
                "notes": "only notes should not count",
            }
        )
    assert "请至少填写" in str(exc.value)


def test_mission_outcome_schema_accepts_one_field():
    payload = MissionOutcomeCreate.model_validate(
        {
            "application_status": "INTERVIEWING",
            "interview_round": "一面",
        }
    )
    assert payload.interview_round == "一面"


def test_empty_outcome_api_returns_422_without_state_change(client, db_session, persisted_profile):
    set_mission_provider(StubIntegratedProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/job-missions",
            json={"raw_text": "Baidu AI PM: own evaluation workflows and quality evaluation."},
        )
        assert created.status_code == 201, created.text
        mission_id = created.json()["id"]
        before = client.get(f"/api/v1/job-missions/{mission_id}")
        assert before.status_code == 200
        before_status = before.json().get("status")
        before_workflow = before.json().get("workflow_state")

        empty = client.post(
            f"/api/v1/job-missions/{mission_id}/outcomes",
            json={
                "application_status": "INTERVIEWING",
                "interview_round": "",
                "questions_asked": [],
                "where_struggled": "",
                "interviewer_feedback": "",
                "notes": "",
            },
        )
        assert empty.status_code == 422, empty.text
        assert "请至少填写" in empty.text

        after = client.get(f"/api/v1/job-missions/{mission_id}")
        assert after.status_code == 200
        assert after.json().get("status") == before_status
        assert after.json().get("workflow_state") == before_workflow

        rows = list(
            db_session.scalars(
                select(models.InterviewOutcome).where(models.InterviewOutcome.mission_id == UUID(mission_id))
            ).all()
        )
        assert rows == []
    finally:
        set_mission_provider(None)
