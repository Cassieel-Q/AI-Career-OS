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

// ---------------------------------------------------------------------------
// 求职工作台总览（全局口径）
// ---------------------------------------------------------------------------

export type OverviewTotals = {
  missions: number;
  resumes: number;
  applications: number;
  applied: number;
  interviewing: number;
};

export type OverviewMission = {
  mission_id: string;
  company: string;
  role: string;
  location: string | null;
  stage: TrackerItem["stage"];
};

export type OverviewRead = {
  totals: OverviewTotals;
  recent_missions: OverviewMission[];
};

/**
 * 总览统计统一走全局口径。
 *
 * 岗位 / 简历 / 投递各自页面都是跨档案展示的，总览若按「当前档案」查就会对不上
 * （典型症状：总览 0 已投递，投递页却有一堆记录）。
 */
export async function fetchOverview(
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<OverviewRead> {
  const response = await request(`${apiUrl}/api/v1/overview`);
  return readApiPayload<OverviewRead>(response);
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

// ---------------------------------------------------------------------------
// 岗位广场 + 投递记录
// ---------------------------------------------------------------------------

export type ApplicationStatus = "PENDING" | "APPLIED" | "SCREENING" | "ASSESSMENT" | "INTERVIEW" | "OFFER" | "CLOSED";

export const APPLICATION_STATUS_LABEL: Record<ApplicationStatus, string> = {
  PENDING: "待投递",
  APPLIED: "已投递",
  SCREENING: "筛选中",
  ASSESSMENT: "测评/笔试",
  INTERVIEW: "面试",
  OFFER: "Offer",
  CLOSED: "已结束",
};

export const APPLICATION_STATUS_ORDER: ApplicationStatus[] = [
  "PENDING", "APPLIED", "SCREENING", "ASSESSMENT", "INTERVIEW", "OFFER", "CLOSED",
];

export const APPLICATION_CHANNELS = ["官网", "招聘网站", "内推", "邮箱", "校园招聘", "其他"] as const;

export type ApplicationRead = {
  id: string;
  profile_id: string;
  mission_id: string | null;
  company: string;
  role: string;
  location: string | null;
  channel: string;
  status: ApplicationStatus;
  stage: string;
  applied_at: string | null;
  next_action: string | null;
  notes: string | null;
  created_at: string | null;
  updated_at: string | null;
};

export type ApplicationsRead = {
  total: number;
  pending: number;
  applied: number;
  interviewing: number;
  offer: number;
  applications: ApplicationRead[];
};

export type PlazaItem = {
  mission_id: string;
  profile_id: string;
  company: string;
  role: string;
  location: string | null;
  seniority: string;
  workflow_state: string;
  prep_score: number;
  resume_ready: boolean;
  target_resume_confirmed: boolean;
  application_id: string | null;
  application_status: string | null;
  updated_at: string | null;
};

export type PlazaRead = {
  total: number;
  applied: number;
  ready: number;
  items: PlazaItem[];
};

export async function fetchPlaza(
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<PlazaRead> {
  const response = await request(`${apiUrl}/api/v1/plaza`);
  return readApiPayload<PlazaRead>(response);
}

export async function fetchApplications(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ApplicationsRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/applications`);
  return readApiPayload<ApplicationsRead>(response);
}

/** 全局投递记录（跨档案）——避免岗位属于其它档案时投递页看不到。 */
export async function fetchAllApplications(
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ApplicationsRead> {
  const response = await request(`${apiUrl}/api/v1/applications`);
  return readApiPayload<ApplicationsRead>(response);
}

export type ApplicationInput = {
  mission_id?: string | null;
  company: string;
  role: string;
  location?: string | null;
  channel?: string;
  status?: ApplicationStatus;
  applied_at?: string | null;
  next_action?: string | null;
  notes?: string | null;
};

export async function createApplication(
  profileId: string,
  input: ApplicationInput,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ApplicationRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/applications`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(input),
  });
  return readApiPayload<ApplicationRead>(response);
}

export async function updateApplication(
  applicationId: string,
  patch: Partial<ApplicationInput>,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ApplicationRead> {
  const response = await request(`${apiUrl}/api/v1/applications/${encodeURIComponent(applicationId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readApiPayload<ApplicationRead>(response);
}

export async function deleteApplication(
  applicationId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<void> {
  await request(`${apiUrl}/api/v1/applications/${encodeURIComponent(applicationId)}`, { method: "DELETE" });
}

// ---------------------------------------------------------------------------
// 候选岗位暂存区（目标一）：生成草稿 → 逐条确认/拒绝 → 幂等导入
// ---------------------------------------------------------------------------

export type CandidateJob = {
  id: string;
  profile_id: string;
  source_kind: string;
  recognition_source: string;
  source_excerpt: string;
  company: string | null;
  role: string | null;
  location: string | null;
  status: "DRAFT" | "CONFIRMED" | "IMPORTED" | "REJECTED";
  imported_mission_id: string | null;
  warnings: string[];
  title: string;
  created_at: string | null;
  updated_at: string | null;
};

export type CandidateImportResult = {
  candidate_id: string;
  mission_id: string;
  company: string;
  role: string;
  status: string;
  reused: boolean;
};

export async function parseCandidateJobs(
  profileId: string,
  sourceText: string,
  sourceKind = "PASTE",
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateJob[]> {
  const response = await request(
    `${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/candidate-jobs/parse`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ source_text: sourceText, source_kind: sourceKind }),
    },
  );
  return readApiPayload<CandidateJob[]>(response);
}

export async function fetchCandidateJobs(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateJob[]> {
  const response = await request(
    `${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/candidate-jobs`,
  );
  return readApiPayload<CandidateJob[]>(response);
}

export async function updateCandidateJob(
  candidateId: string,
  patch: { company?: string | null; role?: string | null; location?: string | null },
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateJob> {
  const response = await request(`${apiUrl}/api/v1/candidate-jobs/${encodeURIComponent(candidateId)}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(patch),
  });
  return readApiPayload<CandidateJob>(response);
}

export async function confirmCandidateJob(
  candidateId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateJob> {
  const response = await request(`${apiUrl}/api/v1/candidate-jobs/${encodeURIComponent(candidateId)}/confirm`, {
    method: "POST",
  });
  return readApiPayload<CandidateJob>(response);
}

export async function rejectCandidateJob(
  candidateId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateJob> {
  const response = await request(`${apiUrl}/api/v1/candidate-jobs/${encodeURIComponent(candidateId)}/reject`, {
    method: "POST",
  });
  return readApiPayload<CandidateJob>(response);
}

export async function importCandidateJob(
  candidateId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<CandidateImportResult> {
  const response = await request(`${apiUrl}/api/v1/candidate-jobs/${encodeURIComponent(candidateId)}/import`, {
    method: "POST",
  });
  return readApiPayload<CandidateImportResult>(response);
}
