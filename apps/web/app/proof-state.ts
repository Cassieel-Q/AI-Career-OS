import { readApiPayload } from "./profile-flow.ts";
import type { Route } from "next";
import { listTargetJobs, readClaimAnalysis, readProofActions } from "./proof-flow.ts";
import type { ClaimAnalysis, InterviewSession, ProofAction, TargetJob } from "./proof-flow.ts";

export type ProofStep = "target-job" | "resume-suggestions" | "claim-check" | "interview" | "debrief" | "proof-actions" | "re-evaluate";

export type ProofSnapshot = {
  targetJobs: TargetJob[];
  targetJob: TargetJob | null;
  analysis: ClaimAnalysis | null;
  claim: ClaimAnalysis["claims"][number] | null;
  sessions: InterviewSession[];
  session: InterviewSession | null;
  actions: ProofAction[];
};

export function freshInterviewEntry(
  freshStart: boolean,
  freshHandled: boolean,
  session: { status?: string; round_count?: number; turns?: Array<{ answer?: string | null }> } | null,
): { startNew: boolean; consumeFresh: boolean } {
  if (!freshStart || freshHandled || !session) return { startNew: false, consumeFresh: false };
  const hasAnswered = (session.turns ?? []).some((turn) => turn.answer != null) || Number(session.round_count ?? 0) > 0;
  if (!hasAnswered) return { startNew: false, consumeFresh: true };
  return { startNew: session.status === "ACTIVE" || session.status === "COMPLETED", consumeFresh: true };
}

export const PROOF_STEPS: readonly ProofStep[] = [
  "target-job",
  "resume-suggestions",
  "claim-check",
  "interview",
  "debrief",
  "proof-actions",
  "re-evaluate",
];

export const PROOF_STEP_LABELS: Record<ProofStep, string> = {
  "target-job": "目标岗位",
  "resume-suggestions": "简历建议",
  "claim-check": "主张核对",
  interview: "模拟面试",
  debrief: "复盘",
  "proof-actions": "证明行动",
  "re-evaluate": "再评估",
};

export const PROOF_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

export function proofHref(profileId: string, step: ProofStep, missionId?: string): Route {
  const base = `/proof/${encodeURIComponent(profileId)}/${step}`;
  if (missionId) {
    return `${base}?mission_id=${encodeURIComponent(missionId)}` as Route;
  }
  return base as Route;
}

export function proofStepIndex(step: ProofStep): number {
  return PROOF_STEPS.indexOf(step);
}

export function canEnterProofStep(snapshot: ProofSnapshot, step: ProofStep): boolean {
  if (step === "target-job") return true;
  if (!snapshot.targetJob) return false;
  if (step === "resume-suggestions") return true;
  // Mission「开始模拟面试」deep-link: claim alone is enough to enter interview (auto-starts session).
  // Do not bounce to 简历建议 just because claim-analysis envelope is missing/stale.
  if (step === "interview" && snapshot.claim) return true;
  if (!snapshot.analysis?.claims.length || !snapshot.claim) return false;
  if (step === "claim-check") return true;
  if (step === "interview") return true;
  if (!snapshot.session) return false;
  if (step === "debrief") return snapshot.session.status === "COMPLETED";
  if (step === "proof-actions") return snapshot.session.status === "COMPLETED";
  return snapshot.actions.length > 0;
}

/**
 * A mission-scoped interview link is an intentional entry point from the
 * confirmed resume. Claims are generated lazily, so the first snapshot can
 * briefly have a target job but no claim yet. Keep that route in place while
 * the claim/session is being prepared instead of bouncing the user back to
 * the legacy "简历建议" step.
 */
export function shouldKeepMissionInterviewRoute(snapshot: ProofSnapshot, missionId: string | undefined, step: ProofStep): boolean {
  return Boolean(missionId && step === "interview" && snapshot.targetJob);
}

export function latestValidProofStep(snapshot: ProofSnapshot): ProofStep {
  if (!snapshot.targetJob) return "target-job";
  // Prefer claim presence (mission proof-snapshot may expose claim without analysis envelope).
  if (!snapshot.claim && !snapshot.analysis?.claims.length) return "resume-suggestions";
  if (!snapshot.session) return snapshot.claim ? "interview" : "claim-check";
  if (snapshot.session.status !== "COMPLETED") return "interview";
  if (!snapshot.actions.length) return "proof-actions";
  return "re-evaluate";
}

export async function readProofSnapshot(profileId: string, apiUrl = PROOF_API_BASE_URL, request: typeof fetch = fetch, missionId?: string): Promise<ProofSnapshot> {
  if (missionId) {
    const scoped = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/proof-snapshot`);
    return readApiPayload<ProofSnapshot>(scoped);
  }
  const targetJobs = await listTargetJobs(profileId, apiUrl, request);
  const targetJob = targetJobs[targetJobs.length - 1] ?? null;
  if (!targetJob) return { targetJobs, targetJob, analysis: null, claim: null, sessions: [], session: null, actions: [] };

  let analysis: ClaimAnalysis | null = null;
  try {
    analysis = await readClaimAnalysis(targetJob.id, apiUrl, request);
  } catch (error) {
    const message = error instanceof Error ? error.message : "";
    const missing =
      message.includes("HTTP 404") ||
      /Claim analysis has not been generated/i.test(message) ||
      message.includes("尚未生成主张分析");
    if (!missing) throw error;
  }
  const claim = analysis?.claims[0] ?? null;
  if (!claim) return { targetJobs, targetJob, analysis, claim, sessions: [], session: null, actions: [] };

  let sessions: InterviewSession[] = [];
  const sessionsResponse = await request(`${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claim.id)}/interview-sessions`);
  if (sessionsResponse.ok) sessions = await readApiPayload<InterviewSession[]>(sessionsResponse);
  const session = [...sessions].sort((a, b) => {
    const byCreated = String(b.created_at).localeCompare(String(a.created_at));
    return byCreated || String(b.updated_at).localeCompare(String(a.updated_at)) || String(b.id).localeCompare(String(a.id));
  })[0] ?? null;
  const actions = session?.status === "COMPLETED" ? await readProofActions(claim.id, apiUrl, request) : [];
  return { targetJobs, targetJob, analysis, claim, sessions, session, actions };
}
