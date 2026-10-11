import { readApiPayload } from "./profile-flow.ts";
import { MISSION_API_BASE_URL, PROFILE_STORAGE_KEY, type MissionRequester } from "./missions.ts";

export function readCurrentProfileId(): string {
  if (typeof window === "undefined") return "";
  return (window.localStorage.getItem(PROFILE_STORAGE_KEY) || "").trim();
}

export const STAGE_LABEL: Record<TrackerItem["stage"], string> = {
  PREPARING: "准备中",
  APPLIED: "已投递",
  INTERVIEW: "面试中",
  COMPLETED: "已结束",
  ARCHIVED: "已归档",
};

export function stageBadgeClass(stage: TrackerItem["stage"]): string {
  if (stage === "APPLIED" || stage === "INTERVIEW") return "filled";
  if (stage === "COMPLETED") return "attention";
  return "muted";
}

export type TrackerItem = {
  mission_id: string;
  company: string;
  role: string;
  location: string | null;
  seniority: string;
  stage: "PREPARING" | "APPLIED" | "INTERVIEW" | "COMPLETED" | "ARCHIVED";
  outcome_status: string | null;
  resume_ready: boolean;
  outcome_count: number;
  updated_at: string | null;
};

export type TrackerRead = {
  profile_id: string;
  total: number;
  preparing: number;
  applied: number;
  interviewing: number;
  completed: number;
  applications: TrackerItem[];
};

export type ClaimRead = {
  id: string;
  mission_id: string | null;
  company: string;
  role: string;
  claim: string;
  current_text: string | null;
  suggested_text: string | null;
  readiness_status: string;
  confidence: number;
  risk_reason: string;
  evidence_refs: string[];
  matched_capabilities: string[];
};

export type ClaimsRead = {
  profile_id: string;
  total: number;
  confirmed: number;
  needs_confirmation: number;
  claims: ClaimRead[];
};

export type ResumeOverviewItem = {
  mission_id: string;
  resume_id: string;
  company: string;
  role: string;
  version: number;
  status: string;
  bullet_count: number;
  confirmed: boolean;
  updated_at: string | null;
};

export type ResumesOverviewRead = {
  profile_id: string;
  total: number;
  resumes: ResumeOverviewItem[];
};

export async function fetchTracker(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<TrackerRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/tracker`);
  return readApiPayload<TrackerRead>(response);
}

export async function fetchClaims(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ClaimsRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/claims`);
  return readApiPayload<ClaimsRead>(response);
}

export async function fetchResumesOverview(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ResumesOverviewRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/resumes`);
  return readApiPayload<ResumesOverviewRead>(response);
}
