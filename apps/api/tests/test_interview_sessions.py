from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app import models
from app.interview_provider import set_interview_provider
from app.proof_schemas import ClaimProposalPayload, InterviewResponsePayload, TargetJobCreate, InterviewTurnCreate, InterviewSessionRead
from app.proof_service import create_target_job, generate_claim_analysis, list_interview_sessions, start_interview_session, submit_interview_turn


class FakeClaimProvider:
    def analyze(self, *, target_job, profile_facts):
        return ClaimProposalPayload.model_validate({
            "claims": [{
                "claim": "Designed an LLM evaluation workflow",
                "current_text": "Worked on LLM evaluation",
                "suggested_text": "Designed an LLM evaluation workflow",
                "reason": "The experience is present but under-explained.",
                "jd_relevance": "Matches evaluation work.",
                "matched_capabilities": [{"name": "LLM evaluation", "summary": "Evaluation design", "atomic_requirement_ids": []}],
                "evidence_refs": [str(profile_facts[0]["id"])],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.7,
                "risk_reason": "No artifact is recorded.",
                "attack_surface": [{"area": "AI", "risk": "Explain evaluation design", "evidence_refs": [str(profile_facts[0]["id"])]}],
            }]
        })


class FakeInterviewProvider:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        self.calls += 1
        if self.calls < 4:
            return InterviewResponsePayload.model_validate({
                "question": f"Follow-up {self.calls}",
                "skill_id": "LLM_EVALUATION",
                "followup_dimensions": ["dataset", "rubric"],
                "evaluation": {"strong_points": ["specific example"], "weak_points": ["artifact missing"]},
            })
        return InterviewResponsePayload.model_validate({
            "question": None,
            "skill_id": None,
            "followup_dimensions": [],
            "evaluation": {
                "strong_points": ["clear ownership"],
                "weak_points": ["no reproducible artifact"],
                "gap_type": "EVIDENCE_GAP",
                "why": "The answer describes the idea but does not point to a saved artifact.",
                "evidence_refs": [],
                "recommended_next_action": "Build a small labeled evaluation set.",
            },
        })


class EarlyCompleteProvider:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        self.calls += 1
        if answer is None:
            return InterviewResponsePayload.model_validate({
                "question": "请先说明你负责的部分。",
                "skill_id": "OWNERSHIP",
                "followup_dimensions": [],
                "evaluation": {"strong_points": [], "weak_points": []},
            })
        return InterviewResponsePayload.model_validate({
            "question": None,
            "skill_id": None,
            "followup_dimensions": [],
            "evaluation": {
                "strong_points": ["回答具体"],
                "weak_points": [],
                "gap_type": "EVIDENCE_GAP",
                "why": "还需要更多证据",
                "evidence_refs": [],
                "recommended_next_action": "补充材料",
            },
        })


class FiveRoundProvider:
    def __init__(self) -> None:
        self.calls = 0

    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        self.calls += 1
        if self.calls <= 5:
            return InterviewResponsePayload.model_validate({
                "question": f"第 {self.calls + 1} 轮：请继续说明你的决策依据。",
                "skill_id": "DECISION_MAKING",
                "followup_dimensions": ["决策", "结果"],
                "evaluation": {"strong_points": ["回答具体"], "weak_points": ["还可补充证据"]},
            })
        return InterviewResponsePayload.model_validate({
            "question": None,
            "skill_id": None,
            "followup_dimensions": [],
            "evaluation": {
                "strong_points": ["连续回答"],
                "weak_points": ["需要保留证据"],
                "gap_type": "EVIDENCE_GAP",
                "why": "需要继续沉淀证据",
                "evidence_refs": [],
                "recommended_next_action": "整理项目材料",
            },
        })


class CapturingInterviewProvider:
    def __init__(self) -> None:
        self.target_job = None

    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        self.target_job = target_job
        return InterviewResponsePayload.model_validate({
            "question": "请说明你的测试指标。",
            "skill_id": "PRODUCT_METRICS",
            "followup_dimensions": ["指标"],
            "evaluation": {"strong_points": [], "weak_points": []},
        })


def prepared_claim(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI evaluation workflow."))
    analysis = generate_claim_analysis(db_session, target_job.id, provider=FakeClaimProvider())
    return analysis.claims[0].id


def test_interview_requires_three_rounds_and_persists_debrief(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    provider = FakeInterviewProvider()
    set_interview_provider(provider)
    try:
        session = start_interview_session(db_session, claim_id)
        assert session.status.value == "ACTIVE"
        assert session.next_question == "Follow-up 1"  # first response is the opening question, then provider asks next
        assert session.round_count == 0

        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="I used a labeled set."))
        assert session.status.value == "ACTIVE"
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="I reviewed errors."))
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="I compared regressions."))
        assert session.status.value == "COMPLETED"
        assert session.round_count == 3
        assert session.gap_type.value == "EVIDENCE_GAP"
        assert len(session.turns) == 3
    finally:
        set_interview_provider(None)


def test_completed_interview_rejects_more_answers_without_mutating_history(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    provider = FakeInterviewProvider()
    set_interview_provider(provider)
    try:
        session = start_interview_session(db_session, claim_id)
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="one"))
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="two"))
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="three"))

        with pytest.raises(HTTPException) as caught:
            submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="three more"))

        assert caught.value.status_code == 409
        assert db_session.query(models.InterviewTurn).count() == 3
    finally:
        set_interview_provider(None)


def test_interview_start_passes_bounded_curated_intel_to_provider(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    claim = db_session.get(models.ResumeClaim, claim_id)
    assert claim is not None
    mission = models.JobMission(
        profile_id=persisted_profile.id,
        target_job_id=claim.target_job_id,
        display_name="百度 AI 产品经理",
        interview_intel=[{
            "skill_id": "CURATED_BAIDU_AI_PRODUCT",
            "name": "Baidu curated AI_PRODUCT interview signals",
            "company_relevance": "SAME_COMPANY",
            "provenance": "CURATED",
            "source_refs": ["https://example.test/niuke"],
            "body": "## Question patterns\n- 你如何定义测试指标？ [项目]",
        }],
    )
    db_session.add(mission)
    db_session.commit()
    provider = CapturingInterviewProvider()
    set_interview_provider(provider)
    try:
        start_interview_session(db_session, claim_id)
    finally:
        set_interview_provider(None)

    assert provider.target_job is not None
    assert provider.target_job["interview_intel"][0]["question_patterns"] == ["你如何定义测试指标？"]
    assert "body" not in provider.target_job["interview_intel"][0]


def test_interview_uses_current_pack_topics_schema(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    claim = db_session.get(models.ResumeClaim, claim_id)
    assert claim is not None
    mission = models.JobMission(
        profile_id=persisted_profile.id,
        target_job_id=claim.target_job_id,
        display_name="通用岗位面试任务",
    )
    db_session.add(mission)
    db_session.flush()
    db_session.add(models.InterviewPack(
        mission_id=mission.id,
        version=1,
        topics=[{
            "priority": "HIGH",
            "topic": "项目决策与验证",
            "why": "验证候选人的真实项目能力",
            "claims": ["完成项目验证"],
            "capabilities": ["项目决策"],
            "intel_refs": [],
            "question_patterns": ["你如何选择测试指标？"],
            "evidence_expected": ["测试方案"],
        }],
    ))
    db_session.commit()

    provider = CapturingInterviewProvider()
    start_interview_session(db_session, claim_id, provider=provider)

    assert provider.target_job is not None
    assert provider.target_job["interview_pack"][0]["topic"] == "项目决策与验证"


def test_starting_fresh_interview_invalidates_previous_active_session(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    provider = FakeInterviewProvider()
    set_interview_provider(provider)
    try:
        first = start_interview_session(db_session, claim_id)
        second = start_interview_session(db_session, claim_id)
        sessions = list_interview_sessions(db_session, claim_id)
        assert second.status.value == "ACTIVE"
        assert next(item for item in sessions if item.id == first.id).status.value == "INVALIDATED"
        assert sum(item.status.value == "ACTIVE" for item in sessions) == 1
    finally:
        set_interview_provider(None)


def test_early_provider_completion_continues_until_three_answered_rounds(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    provider = EarlyCompleteProvider()
    set_interview_provider(provider)
    try:
        session = start_interview_session(db_session, claim_id)
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="我负责了方案设计。"))
        assert session.status.value == "ACTIVE"
        assert session.round_count == 1
        assert session.next_question
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="我还做了验证。"))
        assert session.status.value == "ACTIVE"
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="我根据结果迭代。"))
        assert session.status.value == "COMPLETED"
        assert session.round_count == 3
    finally:
        set_interview_provider(None)


def test_interview_can_complete_five_continuous_rounds(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    set_interview_provider(FiveRoundProvider())
    try:
        session = start_interview_session(db_session, claim_id)
        for index in range(5):
            session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer=f"第 {index + 1} 轮回答"))
        assert session.status.value == "COMPLETED"
        assert session.round_count == 5
        assert len(session.turns) == 5
    finally:
        set_interview_provider(None)


def test_repeated_provider_question_is_replaced_with_new_dimension(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)

    class RepeatingProvider:
        def ask(self, **kwargs):
            from app.proof_schemas import InterviewResponsePayload

            return InterviewResponsePayload.model_validate({
                "question": "请具体说明优化目标、关键约束以及你对比的方案。",
                "skill_id": "DECISION_MAKING",
                "followup_dimensions": ["方案取舍"],
                "evaluation": {"score": 5, "strong_points": [], "weak_points": []},
            })

    set_interview_provider(RepeatingProvider())
    try:
        session = start_interview_session(db_session, claim_id)
        first_question = session.next_question
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="我比较了两种方案。"))
        assert session.next_question != first_question
        second_question = session.next_question
        session = submit_interview_turn(db_session, session.id, InterviewTurnCreate(answer="我使用了模拟结果。"))
        assert session.next_question not in {first_question, second_question}
    finally:
        set_interview_provider(None)


def test_interview_contract_allows_up_to_five_rounds():
    payload = InterviewSessionRead.model_validate({
        "id": "00000000-0000-0000-0000-000000000001",
        "profile_id": "00000000-0000-0000-0000-000000000003",
        "target_job_id": "00000000-0000-0000-0000-000000000004",
        "claim_id": "00000000-0000-0000-0000-000000000002",
        "status": "ACTIVE",
        "round_count": 5,
        "next_question": "Continue",
        "next_skill_id": "METRICS",
        "strong_points": [],
        "weak_points": [],
        "gap_type": None,
        "gap_why": None,
        "gap_evidence": [],
        "recommended_next_action": None,
        "turns": [],
        "created_at": datetime.now(timezone.utc),
        "updated_at": datetime.now(timezone.utc),
    })
    assert payload.round_count == 5
