import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";

export type RequirementCategory = "SKILL" | "RESPONSIBILITY" | "EXPERIENCE" | "EDUCATION" | "DOMAIN" | "COLLABORATION" | "OTHER";

export type MarketRequirementEvidence = {
  id: string;
  job_description_id: string;
  source_url: string | null;
  evidence_text: string;
};

export type MarketRequirement = {
  id: string;
  name: string;
  category: RequirementCategory;
  occurrence_count: number;
  frequency_ratio: number;
  source_jd_ids: string[];
  evidence: MarketRequirementEvidence[];
};

export type MarketCapability = {
  id: string;
  name: string;
  summary: string;
  occurrence_count: number;
  frequency_ratio: number;
  source_jd_ids: string[];
  atomic_requirement_ids: string[];
  atomic_requirements: MarketRequirement[];
  evidence: MarketRequirementEvidence[];
};

export type MarketProfileRead = {
  id: string;
  target_role_id: string;
  sample_count: number;
  sample_fingerprint: string;
  status: "VALID" | "INVALIDATED";
  generated_at: string;
  updated_at: string;
  requirements: MarketRequirement[];
  capabilities: MarketCapability[];
};

export async function getMarketProfileRequest(targetRoleId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<MarketProfileRead | null> {
  const response = await request(`${apiUrl}/api/v1/target-roles/${targetRoleId}/market-profile`, { method: "GET" });
  if (response.status === 404 || response.status === 409) {
    const payload = await response.clone().json().catch(() => null) as { detail?: unknown } | null;
    if (payload?.detail === "市场画像尚未生成" || payload?.detail === "市场画像已过期，请重新分析" || payload?.detail === "至少需要 3 条 JD 才能生成市场画像") return null;
  }
  return readApiPayload<MarketProfileRead>(response);
}

export async function createMarketProfileRequest(targetRoleId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<MarketProfileRead> {
  const response = await request(`${apiUrl}/api/v1/target-roles/${targetRoleId}/market-profile`, { method: "POST" });
  return readApiPayload<MarketProfileRead>(response);
}

export async function getRequirementEvidenceRequest(requirementId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<MarketRequirementEvidence[]> {
  const response = await request(`${apiUrl}/api/v1/market-requirements/${requirementId}/evidence`, { method: "GET" });
  return readApiPayload<MarketRequirementEvidence[]>(response);
}

export function marketRequirementFrequency(requirement: MarketRequirement): string {
  return `${requirement.occurrence_count} / ${Math.max(requirement.source_jd_ids.length, requirement.occurrence_count)} JDs (${Math.round(requirement.frequency_ratio * 100)}%)`;
}
