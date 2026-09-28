"""Regression: mission-local claims bind to bound_profile_id; strengthen buttons must not English-error."""
from __future__ import annotations

from uuid import UUID

from app import models
import app.proof_service as proof_service
from app.mission_schemas import ConfirmResumeSource, MissionCreate, RecoverEvidenceCreate, ResumeSourceMode
from app.mission_service import (
    bind_mission_resume_from_extraction,
    confirm_resume_source,
    create_mission,
    create_mission_proof_actions,
    generate_claims_for_mission,
    proof_snapshot,
    recover_existing_evidence,
)
from app.profile_service import confirm_profile
from app.proof_schemas import ClaimProposalPayload
from app.resume_schemas import ResumeExtractionResult


def _extraction(title: str) -> ResumeExtractionResult:
    return ResumeExtractionResult(
        education=[{"institution": "Example University", "degree": "MSc", "evidence_text": "Example University MSc"}],
        skills=[
            {"name": "Revit", "evidence_text": "Revit"},
            {"name": "SuperMap", "evidence_text": "SuperMap"},
            {"name": "AutoCAD", "evidence_text": "AutoCAD"},
        ],
        experiences=[
            {
                "title": title,
                "organization": "Delivery Lab",
                "evidence_text": f"{title} at Delivery Lab — owned evaluation gates and cross-team BIM delivery",
            }
        ],
        certifications=[],
    )


class _FakeClaims:
    def analyze(self, *, target_job, profile_facts):
        experience = next((f for f in profile_facts if f.get("kind") == "experience"), profile_facts[0])
        fact_id = experience["id"]
        return ClaimProposalPayload.model_validate(
            {
                "claims": [
                    {
                        "claim": "Owns evaluation workflow and delivery quality gates for target role",
                        "current_text": str(experience.get("value") or "")[:200],
                        "suggested_text": None,
                        "reason": "Grounded in mission-local project experience",
                        "jd_relevance": "Maps to JD evaluation / delivery capabilities",
                        "matched_capabilities": [
                            {
                                "name": "LLM evaluation",
                                "summary": "Evaluation design",
                                "atomic_requirement_ids": [],
                            }
                        ],
                        "evidence_refs": [str(fact_id)],
                        "readiness_status": "WEAK_EVIDENCE",
                        "confidence": 0.55,
                        "risk_reason": "Needs sharper metrics and artifact",
                        "attack_surface": [
                            {
                                "area": "AI",
                                "risk": "Explain evaluation design choices",
                                "evidence_refs": [str(fact_id)],
                            }
                        ],
                    }
                ]
            }
        )


def _mission_local_confirmed(db_session, persisted_profile, title: str = "Mission-Local-Proof"):
    master_id = persisted_profile.id
    mission = create_mission(
        db_session,
        master_id,
        MissionCreate(
            raw_text=(
                "Baidu AI Product Manager: own evaluation workflows, quality gates, "
                "and cross-functional delivery for AI features."
            )
        ),
    )
    bound = bind_mission_resume_from_extraction(
        db_session,
        mission["id"],
        _extraction(title),
        mode="upload",
        update_master=False,
        filename="local-proof.pdf",
    )
    assert bound["isolation"] == "mission_local"
    bound_id = UUID(str(bound["bound_profile_id"]))
    assert bound_id != master_id

    confirm_resume_source(
        db_session,
        mission["id"],
        ConfirmResumeSource(mode=ResumeSourceMode.upload, update_master=False),
    )
    confirmed = confirm_profile(db_session, bound_id)
    assert confirmed.status == "CONFIRMED"
    return mission["id"], bound_id, master_id


def test_upload_confirm_claims_use_bound_profile_and_proof_buttons_safe(db_session, persisted_profile):
    mission_id, bound_id, master_id = _mission_local_confirmed(db_session, persisted_profile)

    original = proof_service.get_claim_analysis_provider
    proof_service.get_claim_analysis_provider = lambda: _FakeClaims()
    try:
        analysis = generate_claims_for_mission(db_session, mission_id)
    finally:
        proof_service.get_claim_analysis_provider = original

    assert analysis.claims
    assert {c.profile_id for c in analysis.claims} == {bound_id}
    assert master_id not in {c.profile_id for c in analysis.claims}

    target_job_id = db_session.get(models.JobMission, mission_id).target_job_id
    target_job = db_session.get(models.TargetJob, target_job_id)
    assert target_job.profile_id == master_id
    claim = analysis.claims[0]
    loaded = proof_service._claim(db_session, claim.id)
    assert loaded.profile_id == bound_id

    snap = proof_snapshot(db_session, mission_id)
    assert snap["claim"] is not None
    assert UUID(str(snap["claim"]["profile_id"])) == bound_id

    result = create_mission_proof_actions(db_session, mission_id, claim.id)
    # Without interview debrief, API must still seed concrete executable ProofActions.
    if isinstance(result, dict):
        actions = result.get("proof_actions") or []
        blob = f"{result.get('message', '')}{result.get('next_action', '')}"
        assert "Profile" not in blob
        assert "bound" not in blob.lower()
    else:
        actions = result
    assert len(actions) >= 1
    persisted = db_session.query(models.ProofAction).filter_by(claim_id=claim.id).all()
    assert len(persisted) >= 1
    assert all(row.profile_id == bound_id for row in persisted)

    recovered = recover_existing_evidence(
        db_session,
        mission_id,
        RecoverEvidenceCreate(
            claim_id=claim.id,
            confirmed=True,
            evidence_text="已有测评报告与门禁记录可追溯",
            artifact_text="已有测评报告与门禁记录可追溯",
        ),
    )
    assert recovered.get("artifact_id") or recovered.get("next")
    action = db_session.query(models.ProofAction).filter_by(claim_id=claim.id).first()
    assert action is not None
    assert action.profile_id == bound_id
    artifact = db_session.query(models.ProofArtifact).filter_by(claim_id=claim.id).first()
    assert artifact is not None
    assert artifact.profile_id == bound_id


def test_rebind_purges_old_profile_claims(db_session, persisted_profile):
    mission_id, bound_id, master_id = _mission_local_confirmed(db_session, persisted_profile, "First-Local")

    original = proof_service.get_claim_analysis_provider
    proof_service.get_claim_analysis_provider = lambda: _FakeClaims()
    try:
        first = generate_claims_for_mission(db_session, mission_id)
    finally:
        proof_service.get_claim_analysis_provider = original
    assert first.claims

    rebound = bind_mission_resume_from_extraction(
        db_session,
        mission_id,
        _extraction("Second-Local"),
        mode="upload",
        update_master=False,
        filename="local-proof-2.pdf",
    )
    new_bound = UUID(str(rebound["bound_profile_id"]))
    assert new_bound != bound_id
    confirm_profile(db_session, new_bound)

    target_job_id = db_session.get(models.JobMission, mission_id).target_job_id
    remaining = (
        db_session.query(models.ResumeClaim)
        .filter_by(target_job_id=target_job_id, profile_id=bound_id)
        .all()
    )
    assert remaining == []
    master_claims = (
        db_session.query(models.ResumeClaim)
        .filter_by(target_job_id=target_job_id, profile_id=master_id)
        .all()
    )
    assert master_claims == []


def test_soft_claims_prefer_experience_over_skill_tokens():
    from app.claim_provider import OpenAIClaimAnalysisProvider

    payload = OpenAIClaimAnalysisProvider._soft_claims_from_facts(
        [
            {"id": "00000000-0000-4000-8000-000000000001", "kind": "skill", "value": "Revit"},
            {"id": "00000000-0000-4000-8000-000000000002", "kind": "skill", "value": "SuperMap"},
            {"id": "00000000-0000-4000-8000-000000000003", "kind": "skill", "value": "AutoCAD"},
            {
                "id": "00000000-0000-4000-8000-000000000004",
                "kind": "experience",
                "value": "主导园区 BIM 协同与交付质量门禁，覆盖 3 个重点项目",
            },
        ]
    )
    claims = payload["claims"]
    assert claims
    assert all("Revit" not in c["claim"] and "SuperMap" not in c["claim"] and "AutoCAD" not in c["claim"] for c in claims)
    assert any("BIM" in c["claim"] or "门禁" in c["claim"] for c in claims)
