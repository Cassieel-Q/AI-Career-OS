from __future__ import annotations

from app.claim_provider import set_claim_analysis_provider
from app.interview_provider import set_interview_provider
from app.proof_action_provider import set_proof_action_provider
from app.proof_schemas import ClaimProposalPayload, InterviewResponsePayload, ProofActionCreate


class ApiClaimProvider:
    def analyze(self, *, target_job, profile_facts):
        return ClaimProposalPayload.model_validate({
            "claims": [{
                "claim": "Designed an evaluation workflow",
                "current_text": "Worked on evaluation",
                "suggested_text": "Designed an evaluation workflow",
                "reason": "The Profile evidence supports a clearer claim.",
                "jd_relevance": "Matches evaluation responsibilities.",
                "matched_capabilities": [],
                "evidence_refs": [str(profile_facts[0]["id"])],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.6,
                "risk_reason": "No artifact is recorded yet.",
                "attack_surface": [],
            }]
        })


class ApiInterviewProvider:
    def ask(self, *, target_job, claim, evidence, skills, turns, answer):
        answered = sum(1 for turn in turns if turn.get("answer"))
        if answered < 2:
            return InterviewResponsePayload.model_validate({
                "question": f"What did you decide in round {answered + 1}?",
                "skill_id": "PROJECT_DEEP_DIVE",
                "followup_dimensions": ["decision", "result"],
                "evaluation": {"strong_points": [], "weak_points": [], "evidence_refs": []},
            })
        return InterviewResponsePayload.model_validate({
            "question": None,
            "skill_id": None,
            "followup_dimensions": [],
            "evaluation": {
                "strong_points": ["Specific decision"],
                "weak_points": ["Artifact is not yet linked"],
                "gap_type": "EVIDENCE_GAP",
                "why": "The answer is plausible but lacks a reviewable artifact.",
                "evidence_refs": [],
                "recommended_next_action": "Publish a small evaluation report.",
            },
        })


class ApiActionProvider:
    def plan(self, *, claim, debrief, evidence):
        return ProofActionCreate.model_validate({
            "actions": [{
                "title": "Publish an evaluation report",
                "why_now": "The claim needs a reviewable artifact.",
                "target_claim": claim["claim"],
                "target_gap": "EVIDENCE_GAP",
                "estimated_hours": 2,
                "artifact_type": "REPORT",
                "definition_of_done": "A report with methodology and findings is available.",
                "expected_evidence": "A versioned report URL.",
            }]
        })


def test_proof_api_vertical_slice(client, db_session, persisted_profile):
    persisted_profile.status = "CONFIRMED"
    db_session.commit()
    set_claim_analysis_provider(ApiClaimProvider())
    set_interview_provider(ApiInterviewProvider())
    set_proof_action_provider(ApiActionProvider())
    try:
        job = client.post(f"/api/v1/profiles/{persisted_profile.id}/target-jobs", json={"raw_text": "Build an evaluation workflow."})
        assert job.status_code == 201
        job_id = job.json()["id"]
        analysis = client.post(f"/api/v1/target-jobs/{job_id}/claim-analysis")
        assert analysis.status_code == 200
        claim_id = analysis.json()["claims"][0]["id"]

        session_response = client.post(f"/api/v1/resume-claims/{claim_id}/interview-sessions", json={"claim_id": claim_id})
        assert session_response.status_code == 201
        session_id = session_response.json()["id"]
        for answer in ("I chose a rubric.", "I ran a small set.", "I recorded the findings."):
            turn = client.post(f"/api/v1/interview-sessions/{session_id}/turns", json={"answer": answer})
            assert turn.status_code == 200
        assert turn.json()["status"] == "COMPLETED"

        actions = client.post(f"/api/v1/resume-claims/{claim_id}/proof-actions")
        assert actions.status_code == 200
        action_id = actions.json()[0]["id"]
        artifact = client.post(f"/api/v1/proof-actions/{action_id}/artifacts", json={"action_id": action_id, "artifact_type": "REPORT", "artifact_url": "https://example.com/report", "manually_confirmed": True})
        assert artifact.status_code == 201
        reevaluated = client.post(f"/api/v1/resume-claims/{claim_id}/re-evaluate")
        assert reevaluated.status_code == 200
        assert reevaluated.json()["after_readiness"] == "DEFENDABLE"
    finally:
        set_claim_analysis_provider(None)
        set_interview_provider(None)
        set_proof_action_provider(None)
