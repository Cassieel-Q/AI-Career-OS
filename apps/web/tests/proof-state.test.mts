import assert from "node:assert/strict";
import test from "node:test";

import { canEnterProofStep, latestValidProofStep, proofHref, shouldKeepMissionInterviewRoute, freshInterviewEntry } from "../app/proof-state.ts";

const empty = { targetJobs: [], targetJob: null, analysis: null, claim: null, sessions: [], session: null, actions: [] };

test("proof guard starts at target job and advances only from persisted state", () => {
  assert.equal(latestValidProofStep(empty), "target-job");
  assert.equal(canEnterProofStep(empty, "target-job"), true);
  assert.equal(canEnterProofStep(empty, "resume-suggestions"), false);
  assert.equal(proofHref("profile 1", "target-job"), "/proof/profile%201/target-job");
});

test("completed interview and proof action unlock the final re-evaluation step", () => {
  const snapshot = {
    ...empty,
    targetJob: { id: "job", profile_id: "profile", raw_text: "JD", source_url: null, content_hash: "h", status: "READY", created_at: "", updated_at: "" },
    analysis: { target_job_id: "job", profile_id: "profile", fingerprint: "f", claims: [{ id: "claim", target_job_id: "job", profile_id: "profile", claim: "Claim", current_text: null, suggested_text: "Claim", reason: "reason", jd_relevance: "relevance", matched_capabilities: [], evidence_refs: [], readiness_status: "WEAK_EVIDENCE", confidence: 0.5, risk_reason: "risk", attack_surface: [], fingerprint: "f", created_at: "", updated_at: "" }] },
    claim: { id: "claim", target_job_id: "job", profile_id: "profile", claim: "Claim", current_text: null, suggested_text: "Claim", reason: "reason", jd_relevance: "relevance", matched_capabilities: [], evidence_refs: [], readiness_status: "WEAK_EVIDENCE", confidence: 0.5, risk_reason: "risk", attack_surface: [], fingerprint: "f", created_at: "", updated_at: "" },
    session: { id: "session", profile_id: "profile", target_job_id: "job", claim_id: "claim", status: "COMPLETED", round_count: 3, next_question: null, next_skill_id: null, strong_points: [], weak_points: [], gap_type: "EVIDENCE_GAP", gap_why: "proof", gap_evidence: [], recommended_next_action: "ship", turns: [], created_at: "", updated_at: "" },
    actions: [{ id: "action", claim_id: "claim", profile_id: "profile", title: "Ship proof", why_now: "now", target_claim: "Claim", target_gap: "EVIDENCE_GAP", estimated_hours: 2, artifact_type: "REPORT", definition_of_done: "done", expected_evidence: "url", status: "COMPLETED", completed_at: "", updated_at: "" }],
  } as any;
  assert.equal(canEnterProofStep(snapshot, "re-evaluate"), true);
  assert.equal(latestValidProofStep(snapshot), "re-evaluate");
});

test("mission mock interview deep-link enters interview when claim exists without analysis envelope", () => {
  const snapshot = {
    ...empty,
    targetJob: { id: "job", profile_id: "profile", raw_text: "JD", source_url: null, content_hash: "h", status: "READY", created_at: "", updated_at: "" },
    analysis: null,
    claim: { id: "claim", target_job_id: "job", profile_id: "profile", claim: "Claim", current_text: null, suggested_text: "Claim", reason: "reason", jd_relevance: "relevance", matched_capabilities: [], evidence_refs: [], readiness_status: "WEAK_EVIDENCE", confidence: 0.5, risk_reason: "risk", attack_surface: [], fingerprint: "f", created_at: "", updated_at: "" },
  } as any;
  assert.equal(canEnterProofStep(snapshot, "interview"), true);
  assert.equal(latestValidProofStep(snapshot), "interview");
  assert.equal(proofHref("p1", "interview", "m1"), "/proof/p1/interview?mission_id=m1");
  // Mission CTA appends &fresh=1 so ProofStepView starts a new session instead of resuming mid-flow.
  assert.equal(
    `/proof/p1/interview?mission_id=m1&fresh=1`,
    "/proof/p1/interview?mission_id=m1&fresh=1",
  );
});

test("mission interview stays on the interview route while claims are being prepared", () => {
  const snapshot = {
    ...empty,
    targetJob: { id: "job", profile_id: "profile", raw_text: "JD", source_url: null, content_hash: "h", status: "READY", created_at: "", updated_at: "" },
  } as any;
  assert.equal(shouldKeepMissionInterviewRoute(snapshot, "mission-1", "interview"), true);
  assert.equal(shouldKeepMissionInterviewRoute(snapshot, undefined, "interview"), false);
});

test("fresh interview entry is consumed by an existing first question and never restarts after an answer", () => {
  const opening = freshInterviewEntry(true, false, { status: "ACTIVE", round_count: 0, turns: [{ answer: null }] } as any);
  assert.deepEqual(opening, { startNew: false, consumeFresh: true });
  const afterAnswer = freshInterviewEntry(true, opening.consumeFresh, { status: "ACTIVE", round_count: 1, turns: [{ answer: "done" }] } as any);
  assert.deepEqual(afterAnswer, { startNew: false, consumeFresh: false });
  assert.deepEqual(freshInterviewEntry(true, false, { status: "ACTIVE", round_count: 2, turns: [{ answer: "old" }] } as any), { startNew: true, consumeFresh: true });
});
