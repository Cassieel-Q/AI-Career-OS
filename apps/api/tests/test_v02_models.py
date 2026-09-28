from datetime import datetime, timezone
from uuid import uuid4

from sqlalchemy import select

from app import models
from app.proof_schemas import InterviewGapType, ReadinessStatus


def test_v02_models_persist_target_job_claim_interview_and_proof_chain(db_session, persisted_profile):
    target_job = models.TargetJob(
        profile_id=persisted_profile.id,
        raw_text="Build an AI product evaluation workflow.",
        source_url="https://example.com/jobs/ai-pm",
        content_hash="a" * 64,
        status="CURRENT",
        requirements=[{"id": str(uuid4()), "name": "LLM evaluation", "category": "SKILL", "evidence_text": "evaluation"}],
        capabilities=[{"name": "AI Product", "summary": "Evaluation workflow", "atomic_requirement_ids": []}],
    )
    db_session.add(target_job)
    db_session.flush()
    claim = models.ResumeClaim(
        target_job_id=target_job.id,
        profile_id=persisted_profile.id,
        claim="Designed an LLM evaluation workflow",
        current_text="Worked on LLM evaluation",
        suggested_text="Designed an LLM evaluation workflow",
        reason="The experience exists but is under-explained.",
        jd_relevance="Directly addresses evaluation responsibilities.",
        matched_capabilities=target_job.capabilities,
        evidence_refs=[str(persisted_profile.skills[0].id)],
        readiness_status=ReadinessStatus.WEAK_EVIDENCE.value,
        confidence=0.7,
        risk_reason="The artifact is not recorded yet.",
        attack_surface=[{"area": "AI", "risk": "Explain evaluation design", "evidence_refs": [str(persisted_profile.skills[0].id)]}],
        fingerprint="b" * 64,
    )
    db_session.add(claim)
    db_session.flush()
    session = models.InterviewSession(
        profile_id=persisted_profile.id,
        target_job_id=target_job.id,
        claim_id=claim.id,
        status="ACTIVE",
        round_count=0,
    )
    db_session.add(session)
    db_session.flush()
    db_session.add(
        models.InterviewTurn(
            session_id=session.id,
            round_number=1,
            skill_id="LLM_EVALUATION",
            question="How did you evaluate the system?",
            answer="I used a small labeled set.",
            followup_dimensions=["dataset", "metrics"],
            evaluation={"gap_type": InterviewGapType.EVIDENCE_GAP.value},
        )
    )
    action = models.ProofAction(
        profile_id=persisted_profile.id,
        claim_id=claim.id,
        session_id=session.id,
        title="Build a 15-case evaluation set",
        why_now="The selected claim needs a concrete artifact.",
        target_claim=claim.claim,
        target_gap=InterviewGapType.EVIDENCE_GAP.value,
        estimated_hours=3,
        artifact_type="DATASET",
        definition_of_done="A versioned dataset exists.",
        expected_evidence="Repository URL.",
        status="PROPOSED",
    )
    db_session.add(action)
    db_session.flush()
    db_session.add(
        models.ProofArtifact(
            profile_id=persisted_profile.id,
            claim_id=claim.id,
            action_id=action.id,
            artifact_type="DATASET",
            artifact_url="https://github.com/example/eval",
            manually_confirmed=True,
            verified_fields=["dataset_cases"],
        )
    )
    db_session.commit()

    loaded = db_session.scalar(select(models.TargetJob).where(models.TargetJob.id == target_job.id))
    assert loaded is not None
    assert loaded.claims[0].interview_sessions[0].turns[0].skill_id == "LLM_EVALUATION"
    assert loaded.claims[0].proof_actions[0].artifacts[0].artifact_url.endswith("/eval")
    assert loaded.claims[0].readiness_status == ReadinessStatus.WEAK_EVIDENCE.value
