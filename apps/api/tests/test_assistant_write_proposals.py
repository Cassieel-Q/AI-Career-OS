"""目标七验收：助手写入提案 → 确认 → 执行 → 回执。"""
import pytest

from app import models
from app.assistant_capabilities import (
    capability_catalog,
    confirm_proposal,
    propose_write,
    reject_proposal,
)
from app.assistant_service import execute_tool


def test_catalog_only_exposes_non_destructive_capabilities():
    names = {item["name"] for item in capability_catalog()}
    assert names == {"create_interview_experience", "create_referral", "create_reminder"}
    assert not any("delete" in name or "remove" in name for name in names)
    for item in capability_catalog():
        assert "parameters" in item and item["parameters"]["type"] == "object"


def test_execute_tool_proposes_without_writing(db_session, persisted_profile):
    before = db_session.query(models.InterviewRecord).count()
    text, changed, _ = execute_tool(
        "create_interview_experience",
        {"company": "Acme", "role": "PM", "round": "一面", "date": "2026-01-02"},
        db_session,
        str(persisted_profile.id),
    )
    # 提案不落库：面经表不变，changed 恒为 False
    assert changed is False
    assert db_session.query(models.InterviewRecord).count() == before
    proposals = db_session.query(models.WriteProposal).all()
    assert len(proposals) == 1
    assert proposals[0].status == "PROPOSED"
    assert "提案" in text
    assert "尚未生效" in text or "不会直接写入" in text


def test_confirm_proposal_writes_target_and_receipt(db_session, persisted_profile):
    proposal = propose_write(
        db_session,
        "create_reminder",
        {"title": "下周一跟进 HR", "due_at": "2026-01-05 09:00"},
        profile_id=persisted_profile.id,
    )
    assert db_session.query(models.Reminder).count() == 0  # 仍未写目标数据

    receipt = confirm_proposal(db_session, proposal.id)
    assert db_session.query(models.Reminder).count() == 1
    reminder = db_session.query(models.Reminder).one()
    assert reminder.title == "下周一跟进 HR"
    assert receipt.target_table == "reminders"
    assert receipt.target_id == str(reminder.id)
    assert receipt.diff["title"] == "下周一跟进 HR"

    refreshed = db_session.get(models.WriteProposal, proposal.id)
    assert refreshed.status == "EXECUTED"


def test_double_confirm_is_rejected(db_session, persisted_profile):
    proposal = propose_write(db_session, "create_referral", {"company": "Acme"}, profile_id=persisted_profile.id)
    confirm_proposal(db_session, proposal.id)
    with pytest.raises(Exception) as exc:
        confirm_proposal(db_session, proposal.id)
    assert "409" in str(exc.value) or "不能重复" in str(exc.value)
    assert db_session.query(models.Referral).count() == 1


def test_reject_proposal_does_not_write(db_session, persisted_profile):
    proposal = propose_write(db_session, "create_referral", {"company": "Acme"}, profile_id=persisted_profile.id)
    reject_proposal(db_session, proposal.id)
    assert db_session.query(models.Referral).count() == 0
    assert db_session.get(models.WriteProposal, proposal.id).status == "REJECTED"


def test_invalid_args_are_caught_before_proposal(db_session, persisted_profile):
    text, changed, _ = execute_tool("create_reminder", {"title": ""}, db_session, str(persisted_profile.id))
    assert changed is False
    assert db_session.query(models.WriteProposal).count() == 0
    assert "不合法" in text or "提案" in text


def test_proposal_routes_roundtrip(client, persisted_profile, db_session):
    proposal = propose_write(
        db_session,
        "create_interview_experience",
        {"company": "ByteDance", "role": "PM", "round": "二面", "date": "2026-02-03"},
        profile_id=persisted_profile.id,
    )
    listed = client.get("/api/v1/assistant/proposals", params={"status": "PROPOSED"})
    assert listed.status_code == 200
    assert [p["id"] for p in listed.json()] == [str(proposal.id)]

    confirm = client.post(f"/api/v1/assistant/proposals/{proposal.id}/confirm", json={})
    assert confirm.status_code == 200
    body = confirm.json()
    assert body["status"] == "EXECUTED"
    assert body["receipt"]["target_table"] == "interview_records"

    caps = client.get("/api/v1/assistant/capabilities")
    assert caps.status_code == 200
    assert {c["name"] for c in caps.json()} == {
        "create_interview_experience", "create_referral", "create_reminder",
    }
