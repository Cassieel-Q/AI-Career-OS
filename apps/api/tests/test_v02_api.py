from __future__ import annotations

from uuid import UUID

from app.claim_provider import set_claim_analysis_provider
from app.proof_schemas import ClaimProposalPayload


class StubClaimProvider:
    def analyze(self, *, target_job: dict[str, object], profile_facts: list[dict[str, object]]) -> ClaimProposalPayload:
        return ClaimProposalPayload.model_validate({
            "claims": [{
                "claim": "Built an AI workflow",
                "current_text": "Worked on AI",
                "suggested_text": "Built an AI workflow",
                "reason": "The confirmed Profile contains a related experience.",
                "jd_relevance": "Matches the JD workflow responsibility.",
                "matched_capabilities": [{"name": "AI product", "summary": "Workflow design", "atomic_requirement_ids": []}],
                "evidence_refs": [str(profile_facts[0]["id"])],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.6,
                "risk_reason": "The artifact is not recorded yet.",
                "attack_surface": [{"area": "AI", "risk": "Explain the workflow", "evidence_refs": [str(profile_facts[0]["id"])]}],
            }]
        })


def test_target_job_and_claim_analysis_api_are_profile_scoped(client, db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    set_claim_analysis_provider(StubClaimProvider())
    try:
        created = client.post(
            f"/api/v1/profiles/{persisted_profile.id}/target-jobs",
            json={"raw_text": "Build an AI workflow for users."},
        )
        assert created.status_code == 201
        target_job_id = UUID(created.json()["id"])

        listed = client.get(f"/api/v1/profiles/{persisted_profile.id}/target-jobs")
        assert listed.status_code == 200
        assert len(listed.json()) == 1

        analysis = client.post(f"/api/v1/target-jobs/{target_job_id}/claim-analysis")
        assert analysis.status_code == 200
        assert analysis.json()["claims"][0]["readiness_status"] == "WEAK_EVIDENCE"

        read = client.get(f"/api/v1/target-jobs/{target_job_id}/claim-analysis")
        assert read.status_code == 200
    finally:
        set_claim_analysis_provider(None)
