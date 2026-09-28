import { readApiPayload } from "./profile-flow.ts";

export type TargetJob = {
  id: string;
  profile_id: string;
  raw_text: string;
  source_url: string | null;
  content_hash: string;
  status: string;
  created_at: string;
  updated_at: string;
};

export type TargetJobCapability = {
  name: string;
  summary: string;
  atomic_requirement_ids: string[];
};

export type AttackSurfaceItem = {
  area: "PRODUCT" | "AI" | "ENGINEERING" | "METRICS" | "BUSINESS_IMPACT";
  risk: string;
  evidence_refs: string[];
};

export type ReadinessStatus = "SUPPORTED" | "DEFENDABLE" | "WEAK_EVIDENCE" | "UNSUPPORTED";
export type Claim = {
  id: string;
  target_job_id: string;
  profile_id: string;
  claim: string;
  current_text: string | null;
  suggested_text: string | null;
  reason: string;
  jd_relevance: string;
  matched_capabilities: TargetJobCapability[];
  evidence_refs: string[];
  readiness_status: ReadinessStatus;
  confidence: number;
  risk_reason: string;
  attack_surface: AttackSurfaceItem[];
  fingerprint: string;
  created_at: string;
  updated_at: string;
};

export type ClaimAnalysis = {
  target_job_id: string;
  profile_id: string;
  fingerprint: string;
  claims: Claim[];
};

export type InterviewSession = {
  id: string;
  profile_id: string;
  target_job_id: string;
  claim_id: string;
  mission_id: string | null;
  status: "ACTIVE" | "COMPLETED" | "INVALIDATED";
  round_count: number;
  next_question: string | null;
  next_skill_id: string | null;
  strong_points: string[];
  weak_points: string[];
  gap_type: "KNOWLEDGE_GAP" | "PROJECT_GAP" | "EVIDENCE_GAP" | "ARTICULATION_GAP" | null;
  gap_why: string | null;
  gap_evidence: string[];
  recommended_next_action: string | null;
  turns: Array<{ id: string; round_number: number; skill_id: string; question: string; answer: string | null; followup_dimensions: string[]; evaluation: { score?: number | null; reference_answer?: string | null; strong_points?: string[]; weak_points?: string[]; why?: string | null; recommended_next_action?: string | null; [key: string]: unknown }; created_at: string }>;
  created_at: string;
  updated_at: string;
};

export type ProofAction = {
  id: string;
  claim_id: string;
  profile_id: string;
  title: string;
  why_now: string;
  target_claim: string;
  target_gap: InterviewSession["gap_type"];
  estimated_hours: number;
  artifact_type: string;
  definition_of_done: string;
  expected_evidence: string;
  status: "PROPOSED" | "IN_PROGRESS" | "COMPLETED" | "SKIPPED";
  completed_at: string | null;
  updated_at: string;
};

export type ProofArtifact = {
  id: string;
  action_id: string;
  claim_id: string;
  profile_id: string;
  artifact_type: string;
  artifact_url: string | null;
  artifact_text: string | null;
  manually_confirmed: boolean;
  verified_fields: string[];
  created_at: string;
};

export type ReevaluateResult = {
  claim_id: string;
  before_readiness: ReadinessStatus;
  after_readiness: ReadinessStatus;
  before_confidence: number;
  after_confidence: number;
  new_evidence_refs: string[];
  reason: string;
  artifacts: ProofArtifact[];
};

export type ProofGuidance = {
  claim_id: string;
  action_type: "FACT_QA_NOTES" | "PROJECT_WRITEUP";
  title: string;
  summary: string;
  questions: string[];
  steps: string[];
  learning: string[];
  expected_outputs: string[];
  generated_by: string;
};

export type ProofRequester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

const INTERVIEW_REQUEST_TIMEOUT_MS = 20_000;

async function interviewRequest(request: ProofRequester, input: RequestInfo | URL, init: RequestInit): Promise<Response> {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), INTERVIEW_REQUEST_TIMEOUT_MS);
  try {
    return await request(input, { ...init, signal: controller.signal });
  } catch (error) {
    if (error instanceof DOMException && error.name === "AbortError") {
      throw new Error("题目生成超过 20 秒仍未完成，请点击重试。", { cause: error });
    }
    throw error;
  } finally {
    clearTimeout(timer);
  }
}

export async function createTargetJob(profileId: string, rawText: string, sourceUrl: string | null, apiUrl: string, request: ProofRequester = fetch): Promise<TargetJob> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/target-jobs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText, ...(sourceUrl ? { source_url: sourceUrl } : {}) }),
  });
  return readApiPayload<TargetJob>(response);
}

export async function listTargetJobs(profileId: string, apiUrl: string, request: ProofRequester = fetch): Promise<TargetJob[]> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/target-jobs`);
  return readApiPayload<TargetJob[]>(response);
}

export async function readClaimAnalysis(targetJobId: string, apiUrl: string, request: ProofRequester = fetch): Promise<ClaimAnalysis> {
  const response = await request(`${apiUrl}/api/v1/target-jobs/${encodeURIComponent(targetJobId)}/claim-analysis`);
  return readApiPayload<ClaimAnalysis>(response);
}

export async function generateClaimAnalysis(targetJobId: string, apiUrl: string, request: ProofRequester = fetch): Promise<ClaimAnalysis> {
  const response = await request(`${apiUrl}/api/v1/target-jobs/${encodeURIComponent(targetJobId)}/claim-analysis`, { method: "POST" });
  return readApiPayload<ClaimAnalysis>(response);
}

export async function startInterview(claimId: string, apiUrl: string, request: ProofRequester = fetch): Promise<InterviewSession> {
  const response = await interviewRequest(request, `${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claimId)}/interview-sessions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ claim_id: claimId }),
  });
  return readApiPayload<InterviewSession>(response);
}

export async function readInterview(sessionId: string, apiUrl: string, request: ProofRequester = fetch): Promise<InterviewSession> {
  const response = await request(`${apiUrl}/api/v1/interview-sessions/${encodeURIComponent(sessionId)}`);
  return readApiPayload<InterviewSession>(response);
}

export async function submitInterviewAnswer(sessionId: string, answer: string, apiUrl: string, request: ProofRequester = fetch): Promise<InterviewSession> {
  const response = await interviewRequest(request, `${apiUrl}/api/v1/interview-sessions/${encodeURIComponent(sessionId)}/turns`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ answer }),
  });
  return readApiPayload<InterviewSession>(response);
}

export async function readProofActions(claimId: string, apiUrl: string, request: ProofRequester = fetch): Promise<ProofAction[]> {
  const response = await request(`${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claimId)}/proof-actions`);
  return readApiPayload<ProofAction[]>(response);
}

export async function generateProofActions(claimId: string, apiUrl: string, request: ProofRequester = fetch): Promise<ProofAction[]> {
  const response = await request(`${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claimId)}/proof-actions`, { method: "POST" });
  return readApiPayload<ProofAction[]>(response);
}

export async function submitProofArtifact(actionId: string, payload: { action_id: string; artifact_type: string; artifact_url?: string; artifact_text?: string; manually_confirmed?: boolean; verified_fields?: string[] }, apiUrl: string, request: ProofRequester = fetch): Promise<ProofArtifact> {
  const response = await request(`${apiUrl}/api/v1/proof-actions/${encodeURIComponent(actionId)}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiPayload<ProofArtifact>(response);
}

export async function reevaluateClaim(claimId: string, apiUrl: string, request: ProofRequester = fetch): Promise<ReevaluateResult> {
  const response = await request(`${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claimId)}/re-evaluate`, { method: "POST" });
  return readApiPayload<ReevaluateResult>(response);
}

export async function generateProofGuidance(claimId: string, actionType: string, apiUrl: string, request: ProofRequester = fetch): Promise<ProofGuidance> {
  const params = new URLSearchParams({ action_type: actionType });
  const response = await interviewRequest(request, `${apiUrl}/api/v1/resume-claims/${encodeURIComponent(claimId)}/proof-guidance?${params.toString()}`, { method: "POST" });
  return readApiPayload<ProofGuidance>(response);
}
