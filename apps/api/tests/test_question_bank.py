"""目标三 · 独立题库：三分类、真实题录入、参考答案事实门控。"""
from __future__ import annotations

from uuid import uuid4

from app import models
from app import question_bank_service as svc


def _make_mission(db, profile_id):
    target_job = models.TargetJob(
        profile_id=profile_id, raw_text="QQQ" * 10, content_hash=uuid4().hex + uuid4().hex
    )
    db.add(target_job)
    db.flush()
    mission = models.JobMission(
        profile_id=profile_id, target_job_id=target_job.id, display_name="d", company="示例公司", role="AI产品经理"
    )
    db.add(mission)
    db.commit()
    db.refresh(mission)
    return mission


# ---------------------------------------------------------------------------
# 分类
# ---------------------------------------------------------------------------


def test_classify_question_three_categories() -> None:
    assert svc.classify_question("请做一个自我介绍") == "HR_QUESTIONS"
    assert svc.classify_question("什么是 RAG？") == "BASIC"
    assert svc.classify_question("介绍你负责的那个项目，怎么做取舍的") == "PROJECT_DEEP_DIVE"


def test_category_must_be_one_of_three(db_session, persisted_profile) -> None:
    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="随便一道题")
    assert item.category in svc.CATEGORIES


def test_invalid_category_is_rejected(db_session, persisted_profile) -> None:
    from fastapi import HTTPException
    import pytest

    bank = svc.create_bank(db_session, persisted_profile.id)
    with pytest.raises(HTTPException) as exc:
        svc.add_item(db_session, bank.id, question_text="Q", category="SOMETHING_ELSE")
    assert exc.value.status_code == 422


# ---------------------------------------------------------------------------
# 门控：无证据 → UNKNOWN
# ---------------------------------------------------------------------------


def test_reference_answer_without_evidence_is_unknown(db_session, persisted_profile) -> None:
    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="介绍一个你主导的项目")
    answer = svc.generate_reference_answer(db_session, item.id)
    assert answer.grounding == "UNKNOWN"
    assert answer.evidence_refs == []
    assert "不编造" in answer.answer_text


def test_reference_answer_uses_only_confirmed_claims(db_session, persisted_profile) -> None:
    target_job = models.TargetJob(
        profile_id=persisted_profile.id, raw_text="JD" * 20, content_hash=uuid4().hex + uuid4().hex
    )
    db_session.add(target_job)
    db_session.flush()
    confirmed = models.ResumeClaim(
        target_job_id=target_job.id,
        profile_id=persisted_profile.id,
        claim="主导了指标体系建设并上线看板",
        reason="r",
        jd_relevance="j",
        readiness_status="CONFIRMED",
        confidence=0.9,
        risk_reason="",
        fingerprint=uuid4().hex,
    )
    unconfirmed = models.ResumeClaim(
        target_job_id=target_job.id,
        profile_id=persisted_profile.id,
        claim="未经确认的主张",
        reason="r",
        jd_relevance="j",
        readiness_status="NEEDS_CONFIRMATION",
        confidence=0.2,
        risk_reason="",
        fingerprint=uuid4().hex,
    )
    db_session.add_all([confirmed, unconfirmed])
    db_session.commit()

    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="讲一下你怎么做指标体系建设")
    answer = svc.generate_reference_answer(db_session, item.id)

    assert answer.grounding == "BULLETS"
    assert str(confirmed.id) in answer.evidence_refs
    assert str(unconfirmed.id) not in answer.evidence_refs
    assert "未经确认的主张" not in answer.answer_text
    assert "指标体系建设" in answer.answer_text


# ---------------------------------------------------------------------------
# 真实面试题
# ---------------------------------------------------------------------------


def test_real_interview_question_is_marked(db_session, persisted_profile) -> None:
    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="真实被问到的题", source="REAL_INTERVIEW")
    assert item.source == "REAL_INTERVIEW"


def test_resume_suggestions_flag_missing_grounding(db_session, persisted_profile) -> None:
    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="介绍一下你的项目")
    suggestions = svc.suggest_resume_optimizations(db_session, item.id)
    assert suggestions
    assert suggestions[0]["grounding"] == "NEEDS_CONFIRMATION"


# ---------------------------------------------------------------------------
# 路由
# ---------------------------------------------------------------------------


def test_question_bank_routes_roundtrip(client, persisted_profile) -> None:
    pid = str(persisted_profile.id)
    bank = client.post(f"/api/v1/profiles/{pid}/question-banks", json={"name": "校招题库"}).json()
    assert bank["item_count"] == 0

    item = client.post(
        f"/api/v1/question-banks/{bank['id']}/items",
        json={"question_text": "请做个自我介绍", "difficulty": "EASY"},
    ).json()
    assert item["category"] == "HR_QUESTIONS"
    assert item["source"] == "MODEL"

    real = client.post(
        f"/api/v1/profiles/{pid}/question-items/real",
        json={"question_text": "讲一下你做的 A/B 测试", "mission_id": None},
    ).json()
    assert real["source"] == "REAL_INTERVIEW"
    assert real["category"] == "PROJECT_DEEP_DIVE"

    answer = client.post(f"/api/v1/question-items/{item['id']}/reference-answer").json()
    assert answer["grounding"] in {"UNKNOWN", "BULLETS", "TARGET_RESUME"}

    # 真实面试题复用已有的通用题库，不重复建库
    listed = client.get(f"/api/v1/profiles/{pid}/question-banks").json()
    assert len(listed) == 1
    assert listed[0]["item_count"] == 2
