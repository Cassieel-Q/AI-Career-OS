from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

import pytest
from fastapi import HTTPException

from app import models
from app.proof_action_provider import set_proof_action_provider
from app.proof_schemas import (
    ClaimProposalPayload,
    InterviewGapType,
    ProofActionCreate,
    ProofArtifactCreate,
    ProofGuidanceRead,
    TargetJobCreate,
)
from app.proof_service import (
    create_target_job,
    generate_claim_analysis,
    generate_proof_actions,
    generate_proof_guidance,
    reevaluate_claim,
    submit_proof_artifact,
)


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


class FakeActionProvider:
    def plan(self, *, claim, debrief, evidence):
        return ProofActionCreate.model_validate({
            "actions": [{
                "title": "Build a 15-case evaluation set",
                "why_now": "The selected claim needs a concrete artifact.",
                "target_claim": "Designed an LLM evaluation workflow",
                "target_gap": "EVIDENCE_GAP",
                "estimated_hours": 3,
                "artifact_type": "DATASET",
                "definition_of_done": "A versioned labeled set exists.",
                "expected_evidence": "Repository URL and README.",
            }]
        })

    def guidance(self, *, claim, debrief, evidence, action_type):
        return ProofGuidanceRead.model_validate({
            "claim_id": claim["id"],
            "action_type": action_type,
            "title": "事实追问",
            "summary": "补充可核对事实。",
            "questions": ["你亲自做了什么？", "结果如何验证？", "依据什么做决定？"],
            "generated_by": "llm",
        })


class CapturingGuidanceProvider(FakeActionProvider):
    def __init__(self) -> None:
        self.debrief = None

    def guidance(self, *, claim, debrief, evidence, action_type):
        self.debrief = debrief
        return super().guidance(claim=claim, debrief=debrief, evidence=evidence, action_type=action_type)


def prepared_claim(db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    target_job = create_target_job(db_session, persisted_profile.id, TargetJobCreate(raw_text="Build an AI evaluation workflow."))
    result = generate_claim_analysis(db_session, target_job.id, provider=FakeClaimProvider())
    claim = db_session.get(models.ResumeClaim, result.claims[0].id)
    session = models.InterviewSession(
        profile_id=persisted_profile.id,
        target_job_id=target_job.id,
        claim_id=claim.id,
        status="COMPLETED",
        round_count=3,
        gap_type=InterviewGapType.EVIDENCE_GAP.value,
        gap_why="No reproducible artifact is recorded.",
        recommended_next_action="Build a small labeled set.",
    )
    db_session.add(session)
    db_session.commit()
    return claim.id


def test_proof_actions_are_artifact_producing_and_bounded(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    set_proof_action_provider(FakeActionProvider())
    try:
        actions = generate_proof_actions(db_session, claim_id)
    finally:
        set_proof_action_provider(None)

    assert len(actions) == 1
    assert actions[0].artifact_type == "DATASET"
    assert actions[0].status.value == "PROPOSED"


def test_artifact_submission_completes_action_and_re_evaluation_moves_weak_evidence_to_defendable(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    set_proof_action_provider(FakeActionProvider())
    try:
        action = generate_proof_actions(db_session, claim_id)[0]
    finally:
        set_proof_action_provider(None)

    artifact = submit_proof_artifact(
        db_session,
        action.id,
        ProofArtifactCreate(action_id=action.id, artifact_type="DATASET", artifact_url="https://github.com/example/eval", manually_confirmed=True),
    )
    reevaluated = reevaluate_claim(db_session, claim_id)

    assert artifact.artifact_url.endswith("/eval")
    assert reevaluated.before_readiness.value == "WEAK_EVIDENCE"
    assert reevaluated.after_readiness.value == "DEFENDABLE"
    assert artifact.id in reevaluated.new_evidence_refs


def test_artifact_submission_rejects_another_action_id(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    set_proof_action_provider(FakeActionProvider())
    try:
        action = generate_proof_actions(db_session, claim_id)[0]
    finally:
        set_proof_action_provider(None)

    with pytest.raises(HTTPException) as caught:
        submit_proof_artifact(db_session, action.id, ProofArtifactCreate(action_id=uuid4(), artifact_type="REPORT", artifact_text="done"))

    assert caught.value.status_code in {409, 422}


def test_guidance_generates_questions_without_an_artifact(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    set_proof_action_provider(FakeActionProvider())
    try:
        guidance = generate_proof_guidance(db_session, claim_id, "FACT_QA_NOTES")
    finally:
        set_proof_action_provider(None)

    assert guidance.generated_by == "llm"
    assert len(guidance.questions) == 3
    assert guidance.action_type == "FACT_QA_NOTES"
    assert db_session.query(models.ProofArtifact).count() == 0


def test_guidance_passes_curated_interview_intel_to_provider(db_session, persisted_profile):
    claim_id = prepared_claim(db_session, persisted_profile)
    claim = db_session.get(models.ResumeClaim, claim_id)
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
    provider = CapturingGuidanceProvider()
    set_proof_action_provider(provider)
    try:
        generate_proof_guidance(db_session, claim_id, "FACT_QA_NOTES")
    finally:
        set_proof_action_provider(None)

    assert provider.debrief["interview_intel"][0]["question_patterns"] == ["你如何定义测试指标？"]
