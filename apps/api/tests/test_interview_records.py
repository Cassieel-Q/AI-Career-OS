# -*- coding: utf-8 -*-
"""Unit tests for interview records library (no LLM)."""

from __future__ import annotations

from datetime import date, datetime, timezone
from uuid import uuid4

import pytest
from sqlalchemy import select

from app import models

from app.interview_record_schemas import (
    InterviewRecordCreate,
    InterviewRecordItemCreate,
    InterviewRecordRead,
)
from app.interview_record_service import _company_key, _group_companies
from app.resume_studio_service import get_or_create_document
from test_resume_studio_document import _mission_with_resume


def test_create_schema_requires_round_and_items():
    item = InterviewRecordItemCreate(question="Q1", my_answer="A1")
    row = InterviewRecordCreate(
        company="示例公司",
        interview_round="一面",
        interviewed_on=date(2026, 10, 1),
        items=[item],
    )
    assert row.company == "示例公司"
    with pytest.raises(Exception):
        InterviewRecordCreate(
            company="示例公司",
            interview_round="四面",
            interviewed_on=date(2026, 10, 1),
            items=[item],
        )


def test_company_key_and_grouping():
    now = datetime.now(timezone.utc)
    pid = uuid4()

    def make(company: str, round_name: str, day: date) -> InterviewRecordRead:
        return InterviewRecordRead(
            id=uuid4(),
            profile_id=pid,
            mission_id=None,
            company=company,
            role=None,
            interview_round=round_name,
            interviewed_on=day,
            notes=None,
            status="DRAFT",
            strong_points=[],
            weak_points=[],
            gap_type=None,
            gap_why=None,
            recommended_next_action=None,
            coaching=None,
            items=[],
            created_at=now,
            updated_at=now,
            evaluated=False,
        )

    records = [
        make("Alpha", "一面", date(2026, 9, 1)),
        make("Alpha", "二面", date(2026, 9, 10)),
        make("Beta", "一面", date(2026, 8, 1)),
    ]
    groups = _group_companies(records)
    assert [g.company for g in groups] == ["Alpha", "Beta"]
    assert groups[0].record_count == 2
    assert groups[0].company_key == _company_key("Alpha")
    assert "一面" in groups[0].rounds and "二面" in groups[0].rounds


def test_record_routes_and_profile_delete_remove_items(client, db_session, persisted_profile):
    profile_id = persisted_profile.id
    response = client.post(
        f"/api/v1/profiles/{profile_id}/interview-records",
        json={
            "company": "示例公司",
            "role": "产品实习生",
            "interview_round": "一面",
            "interviewed_on": "2026-10-08",
            "items": [{"question": "介绍一次项目取舍", "my_answer": "我比较了两种方案。"}],
        },
    )
    assert response.status_code == 201
    record_id = response.json()["id"]
    assert client.get(f"/api/v1/interview-records/{record_id}").status_code == 200
    listing = client.get(f"/api/v1/profiles/{profile_id}/interview-records")
    assert listing.status_code == 200
    assert listing.json()["companies"][0]["record_count"] == 1

    assert client.delete(f"/api/v1/profiles/{profile_id}").status_code == 204
    assert db_session.scalars(select(models.InterviewRecord)).all() == []
    assert db_session.scalars(select(models.InterviewRecordItem)).all() == []


def test_mission_delete_preserves_interview_record_and_cleans_studio(client, db_session):
    mission, _, _ = _mission_with_resume(db_session)
    studio = get_or_create_document(db_session, mission.id)
    studio_id = studio.id
    created = client.post(
        f"/api/v1/profiles/{mission.profile_id}/interview-records",
        json={
            "company": "Acme",
            "interview_round": "一面",
            "interviewed_on": "2026-10-08",
            "mission_id": str(mission.id),
            "items": [{"question": "为什么选择该方案？", "my_answer": "因为更易于验证。"}],
        },
    )
    assert created.status_code == 201
    assert client.delete(f"/api/v1/job-missions/{mission.id}").status_code == 200
    saved = client.get(f"/api/v1/interview-records/{created.json()['id']}")
    assert saved.status_code == 200
    assert saved.json()["mission_id"] is None
    db_session.expire_all()
    assert db_session.get(models.ResumeStudioDocument, studio_id) is None


def test_patch_rejects_another_profiles_mission_and_invalid_required_fields(client, db_session, persisted_profile):
    other_mission, _, _ = _mission_with_resume(db_session)
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/interview-records",
        json={
            "company": "Acme",
            "interview_round": "一面",
            "interviewed_on": "2026-10-08",
            "items": [{"question": "为什么这样做？", "my_answer": "为了验证方案。"}],
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]

    assert client.patch(
        f"/api/v1/interview-records/{record_id}", json={"mission_id": str(other_mission.id)}
    ).status_code == 404
    assert client.patch(
        f"/api/v1/interview-records/{record_id}", json={"mission_id": str(uuid4())}
    ).status_code == 404
    for payload in ({"company": None}, {"company": "  "}, {"interview_round": None},
                    {"interview_round": "四面"}, {"interviewed_on": None}):
        assert client.patch(f"/api/v1/interview-records/{record_id}", json=payload).status_code == 422

    saved = client.get(f"/api/v1/interview-records/{record_id}").json()
    assert saved["mission_id"] is None
    assert saved["company"] == "Acme"
    assert saved["interview_round"] == "一面"


def test_patch_replaces_existing_question_at_same_order(client, persisted_profile):
    created = client.post(
        f"/api/v1/profiles/{persisted_profile.id}/interview-records",
        json={
            "company": "Acme",
            "interview_round": "一面",
            "interviewed_on": "2026-10-08",
            "items": [{"question": "旧问题", "my_answer": "旧回答", "sort_order": 0}],
        },
    )
    assert created.status_code == 201
    record_id = created.json()["id"]
    updated = client.patch(
        f"/api/v1/interview-records/{record_id}",
        json={"items": [{"question": "新问题", "my_answer": "新回答", "sort_order": 0}]},
    )
    assert updated.status_code == 200
    assert [item["question"] for item in updated.json()["items"]] == ["新问题"]


def test_duplicate_question_order_is_rejected(client, persisted_profile):
    payload = {
        "company": "Acme",
        "interview_round": "一面",
        "interviewed_on": "2026-10-08",
        "items": [
            {"question": "问题一", "my_answer": "回答一", "sort_order": 0},
            {"question": "问题二", "my_answer": "回答二", "sort_order": 0},
        ],
    }
    assert client.post(f"/api/v1/profiles/{persisted_profile.id}/interview-records", json=payload).status_code == 422

    payload["items"][1]["sort_order"] = 1
    created = client.post(f"/api/v1/profiles/{persisted_profile.id}/interview-records", json=payload)
    assert created.status_code == 201
    payload["items"][1]["sort_order"] = 0
    assert client.patch(f"/api/v1/interview-records/{created.json()['id']}", json={"items": payload["items"]}).status_code == 422
