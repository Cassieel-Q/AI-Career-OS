import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";

export type GapState = "MATCHED" | "PARTIAL" | "MISSING" | "UNCERTAIN";
export type GapRead = {
  id: string;
  requirement_id: string;
  capability_id: string;
  requirement_name: string;
  capability_name: string;
  capability_summary: string;
  category: string;
  occurrence_count: number;
  frequency_ratio: number;
  source_jd_ids: string[];
  atomic_requirement_ids: string[];
  atomic_requirement_names: string[];
  market_evidence: Array<{ id: string; job_description_id: string; source_url: string | null; evidence_text: string }>;
  state: GapState;
  severity: string;
  proximity: string;
  feasibility: string;
  rationale: string;
  evidence_refs: string[];
  sort_order: number;
};
export type GapAnalysisRead = {
  id: string;
  profile_id: string;
  market_profile_id: string;
  profile_fingerprint: string;
  status: "VALID" | "INVALIDATED";
  generated_at: string;
  updated_at: string;
  gaps: GapRead[];
};

export async function getGapAnalysisRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<GapAnalysisRead | null> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/gap-analysis`, { method: "GET" });
  if (response.status === 404 || response.status === 409) {
    const payload = await response.clone().json().catch(() => null) as { detail?: unknown } | null;
    if (typeof payload?.detail === "string" && (payload.detail.includes("尚未生成") || payload.detail.includes("已过期") || payload.detail.includes("请先生成") || payload.detail.includes("按能力维度重新生成"))) return null;
  }
  return readApiPayload<GapAnalysisRead>(response);
}

export async function createGapAnalysisRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<GapAnalysisRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/gap-analysis`, { method: "POST" });
  return readApiPayload<GapAnalysisRead>(response);
}
