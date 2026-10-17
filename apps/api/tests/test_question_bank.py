"""目标三 · 独立题库：三分类、真实题录入、参考答案事实门控。"""
from __future__ import annotations

from uuid import uuid4

from app import models
from app import question_bank_service as svc


def _offline_model(**_kwargs):
    """模拟模型不可用：验证降级路径时完全不依赖网络与模型输出。"""
    raise RuntimeError("model offline")


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


def test_reference_answer_uses_only_confirmed_claims(db_session, persisted_profile, monkeypatch) -> None:
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
    # 走「模型不可用」降级路径：断言点在于只用已确认事实，与模型输出无关。
    monkeypatch.setattr(svc, "generate_answer", _offline_model)
    answer = svc.generate_reference_answer(db_session, item.id)

    assert answer.grounding == "BULLETS"
    assert str(confirmed.id) in answer.evidence_refs
    assert str(unconfirmed.id) not in answer.evidence_refs
    assert "未经确认的主张" not in answer.answer_text
    assert "指标体系建设" in answer.answer_text


def test_reference_answer_uses_llm_when_available(db_session, persisted_profile, monkeypatch) -> None:
    """模型可用时走 LLM 生成路径，grounding 标记为 LLM_GROUNDED。"""
    target_job = models.TargetJob(
        profile_id=persisted_profile.id, raw_text="J" * 30, content_hash=uuid4().hex + uuid4().hex
    )
    db_session.add(target_job)
    db_session.flush()
    confirmed = models.ResumeClaim(
        target_job_id=target_job.id,
        profile_id=persisted_profile.id,
        claim="主导过指标体系建设",
        reason="r",
        jd_relevance="j",
        readiness_status="SUPPORTED",
        confidence=0.9,
        risk_reason="",
        fingerprint=uuid4().hex,
    )
    db_session.add(confirmed)
    db_session.commit()

    bank = svc.create_bank(db_session, persisted_profile.id)
    item = svc.add_item(db_session, bank.id, question_text="讲一下你怎么做指标体系建设")
    monkeypatch.setattr(svc, "generate_answer", lambda **_kwargs: "我会先梳理核心指标，再逐层搭建看板。")
    answer = svc.generate_reference_answer(db_session, item.id)

    assert answer.grounding == "LLM_GROUNDED"
    assert answer.answer_text == "我会先梳理核心指标，再逐层搭建看板。"


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


# ---------------------------------------------------------------------------
# 相关性：门槛条件不出题 + REJECTED 要点不算已验证事实
# ---------------------------------------------------------------------------


def test_threshold_requirements_never_become_questions(db_session, persisted_profile) -> None:
    """学历/年限这类门槛条件是筛选标准，不展开成「你如何满足本科及以上学历」。"""
    from types import SimpleNamespace

    from app.question_bank_service import _is_threshold_requirement, generate_bank_from_context

    assert _is_threshold_requirement("本科及以上学历，计算机相关专业优先")
    assert _is_threshold_requirement("8年以上互联网产品经验")
    assert not _is_threshold_requirement("熟悉主流AIGC技术栈，理解Diffusion Transformer")

    mission = _make_mission(db_session, persisted_profile.id)
    mission.parsed_jd = {
        "requirements": [
            "本科及以上学历，计算机相关专业优先",
            "8年以上互联网产品经验",
            "熟悉主流AIGC技术栈，能独立完成prompt设计与评测",
        ]
    }
    db_session.commit()

    bank = generate_bank_from_context(db_session, persisted_profile.id, mission_id=mission.id)
    questions = [item.question_text for item in bank.items]
    assert all("本科及以上学历" not in q for q in questions), questions
    assert any("AIGC" in q for q in questions), questions


def test_rejected_bullet_is_never_verified_evidence() -> None:
    """用户明确拒绝（REJECTED）的要点，即使带证据也不能进「已验证」通道。"""
    from types import SimpleNamespace

    from app.mission_interview_context import _bullet_claim_status

    assert _bullet_claim_status(SimpleNamespace(status="REJECTED", evidence_refs=["e1"])) == "REJECTED"
    assert _bullet_claim_status(SimpleNamespace(status="ACCEPTED", evidence_refs=["e1"])) == "CONFIRMED"
    assert _bullet_claim_status(SimpleNamespace(status="PENDING", evidence_refs=["e1"])) == "SUPPORTED"
    assert _bullet_claim_status(SimpleNamespace(status="ACCEPTED", evidence_refs=[])) == "NEEDS_CONFIRMATION"
