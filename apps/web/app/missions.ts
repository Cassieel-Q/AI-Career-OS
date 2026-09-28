import type { Route } from "next";

import { readApiPayload } from "./profile-flow.ts";

// Use the IPv4 loopback by default. On Windows, `localhost` can resolve to
// ::1 while the local API is bound to 127.0.0.1, which surfaces as a vague
// browser "Failed to fetch" error.
export const MISSION_API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";
/** User-facing mission stages. The legacy proof route remains addressable by direct links,
 * but it is deliberately excluded from the main shell so users only see the core job-search flow. */
export const CORE_MISSION_TABS = ["role", "resume", "interview", "outcome"] as const;
export const MISSION_TABS = CORE_MISSION_TABS;
export type CoreMissionTab = (typeof CORE_MISSION_TABS)[number];
export type MissionTab = CoreMissionTab | "proof";

const MISSION_TAB_LABELS: Record<MissionTab, string> = {
  role: "目标岗位",
  resume: "简历优化",
  proof: "补强",
  interview: "模拟面试",
  outcome: "面试记录",
};

export function missionTabLabel(tab: MissionTab): string {
  return MISSION_TAB_LABELS[tab];
}

export function missionHref(missionId: string, tab: MissionTab): Route {
  return `/missions/${encodeURIComponent(missionId)}/${tab}` as Route;
}

export type MissionStatus = "DRAFT" | "RESUME_PREP" | "STRENGTHENING" | "INTERVIEW_PREP" | "APPLIED" | "INTERVIEWING" | "COMPLETED" | "ARCHIVED";
export type WorkflowState =
  | "JD_REQUIRED"
  | "JOB_ANALYZING"
  | "ROLE_UNDERSTOOD"
  | "RESUME_REQUIRED"
  | "RESUME_SELECTED"
  | "EXPERIENCE_SELECTION_REQUIRED"
  | "EXPERIENCES_CONFIRMED"
  | "RESUME_STRATEGY_REQUIRED"
  | "RESUME_STRATEGY_CONFIRMED"
  | "TARGET_RESUME_DRAFT"
  | "TARGET_RESUME_CONFIRMED"
  | "STRESS_TEST_REQUIRED"
  | "STRENGTHENING_REQUIRED"
  | "PROOF_IN_PROGRESS"
  | "CLAIM_REEVALUATION_REQUIRED"
  | "RESUME_UPGRADE_AVAILABLE"
  | "INTERVIEW_PREP_READY"
  | "INTERVIEW_IN_PROGRESS"
  | "INTERVIEW_DEBRIEF_READY"
  | "OUTCOME";

export type MissionResumeSource = {
  mode: "master" | "upload" | "paste";
  bound_at: string;
  isolation?: "mission_local" | "shared_master" | string | null;
  bound_profile_id?: string | null;
  master_profile_id?: string | null;
  filename?: string | null;
  updated_master?: boolean;
};

export type Mission = {
  id: string;
  profile_id: string;
  target_job_id: string;
  display_name: string;
  company: string;
  role: string;
  role_family: string;
  seniority: string;
  location: string | null;
  status: MissionStatus;
  workflow_state?: WorkflowState | string;
  resume_source?: MissionResumeSource | null;
  warnings?: string[];
  parsed_jd: Record<string, unknown>;
  what_matters: Record<string, unknown>;
  resume_strategy: Record<string, unknown>;
  interview_intel: InterviewIntel[];
  created_at: string;
  updated_at: string;
};

export type InterviewIntel = {
  skill_id: string;
  name: string;
  company_relevance: string;
  role_relevance: string;
  competency: string;
  source_count: number;
  recency: string | null;
  confidence: number;
  source_refs: string[];
  observed_label: string;
  body?: string;
  provenance?: string;
};

export type MissionRequester = (input: RequestInfo | URL, init?: RequestInit) => Promise<Response>;

export type TargetResumeBullet = {
  id: string;
  source_experience_id: string | null;
  original_text: string;
  suggested_text: string;
  final_text: string | null;
  reason: string;
  jd_refs: string[];
  evidence_refs: string[];
  resume_skill_refs: string[];
  risk_flags: string[];
  status: "SUGGESTED" | "ACCEPTED" | "EDITED" | "REJECTED";
  fact_confirmed?: boolean;
  grounding_status?: "SUPPORTED" | "NEEDS_CONFIRMATION" | "UNSUPPORTED";
  target_capabilities?: string[];
  sort_order: number;
};

export type TargetResume = {
  id: string;
  mission_id: string;
  version: number;
  status: string;
  positioning_statement: string | null;
  recommended_experience_order: string[];
  strategy: Record<string, unknown>;
  bullets: TargetResumeBullet[];
  section_order?: string[];
  skills?: string[];
  excluded_suggestions?: string[];
  created_at: string;
  updated_at: string;
};

export type ExperienceSelection = {
  id: string;
  mission_id: string;
  profile_id: string;
  experience_id: string;
  decision: "KEEP_AND_HIGHLIGHT" | "KEEP" | "DEEMPHASIZE" | "OMIT";
  why: string;
  related_capabilities: string[];
  supporting_evidence_refs: string[];
  confidence: number;
  updated_at: string;
};

export type ProofState = {
  mission_id: string;
  claims: Array<{ id: string; claim: string; readiness_status: string; confidence: number; evidence_refs: string[]; matched_capabilities: Array<Record<string, unknown>>; risk_reason: string }>;
  proof_actions: Array<{ id: string; claim_id: string; title: string; target_capability: string | null; existing_project_reference: string | null; status: string; definition_of_done: string; expected_evidence: string; artifact_type?: string }>;
  proof_artifacts: Array<{ id: string; action_id: string; claim_id: string; artifact_type: string; manually_confirmed: boolean; verified_fields: string[] }>;
};

export type Readiness = {
  mission_id: string;
  status: "READY_TO_APPLY" | "STRENGTHEN_FIRST" | "INSUFFICIENT_EVIDENCE";
  why: string;
  blocks: string[];
  what_would_change: string[];
  advice_only: boolean;
};

export type ProfileExperience = {
  id: string;
  title: string | null;
  organization: string | null;
  dates: string | null;
  description: string | null;
  experience_type: string;
};

export type ProfileEducation = {
  id?: string;
  institution?: string | null;
  school?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  major?: string | null;
  dates?: string | null;
  relevant_courses?: string[] | null;
};

export type ProfileSkill = {
  id?: string;
  name?: string | null;
};

export type ProfileCertification = {
  id?: string;
  name?: string | null;
  issuer?: string | null;
  date?: string | null;
  score?: string | null;
};

/** Profile API 可能返回的联系方式与分节字段；缺失则导出时跳过。 */
export type ProfileSnapshot = {
  profile_id: string;
  experiences: ProfileExperience[];
  status?: string;
  full_name?: string | null;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  display_name?: string | null;
  name?: string | null;
  location?: string | null;
  headline?: string | null;
  summary?: string | null;
  education?: ProfileEducation[];
  skills?: Array<ProfileSkill | string>;
  certifications?: ProfileCertification[];
};

export const EXPERIENCE_DECISION_OPTIONS: Array<{ value: ExperienceSelection["decision"]; label: string; hint: string }> = [
  { value: "KEEP_AND_HIGHLIGHT", label: "重点展示", hint: "写进核心故事" },
  { value: "KEEP", label: "保留", hint: "简要保留" },
  { value: "DEEMPHASIZE", label: "弱化", hint: "少写或不展开" },
  { value: "OMIT", label: "暂不放入", hint: "本份岗位简历不展示这段经历（不会删除原简历）" },
];


// alignedExperienceWhy lives in ./experience-utils.ts (avoid circular / stale Temp-FE desync with this client API module)

export async function readProfileExperiences(profileId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<ProfileExperience[]> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}`);
  const profile = await readApiPayload<{ experiences?: ProfileExperience[] }>(response);
  return profile.experiences ?? [];
}

export function buildMissionJdText(input: { company: string; role: string; seniority?: string; jdExtra?: string }): string {
  const company = input.company.trim() || "UNKNOWN";
  const role = input.role.trim() || "UNKNOWN";
  const seniority = (input.seniority || "").trim() || "UNKNOWN";
  const extra = (input.jdExtra || "").trim();
  const parts = [
    `公司：${company}`,
    `岗位：${role}`,
    `级别：${seniority}`,
    "",
    "岗位职责：",
    `- 面向 ${company} 的 ${role} 岗位准备简历与面试`,
    "- 需要结合 AI / 产品 / 数据分析相关能力进行岗位匹配",
    "",
    "任职要求：",
    "- 有相关项目或实习经历，能讲清自己的贡献与结果",
    "- 熟悉目标公司业务与常见面试考察点",
  ];
  if (extra) {
    parts.push("", "补充 JD / 岗位说明：", extra);
  }
  return parts.join("\n");
}


export const PROFILE_STORAGE_KEY = "ai-career-os-dogfood-profile-id";
export const DEBUG_QUERY = "debug";

export function resumeBindingKey(missionId: string): string {
  return `ai-career-os-mission-resume-bound:${missionId}`;
}

export function targetConfirmedKey(missionId: string): string {
  return `ai-career-os-mission-target-confirmed:${missionId}`;
}

export function readResumeBound(missionId: string): boolean {
  if (typeof window === "undefined") return false;
  return Boolean(window.localStorage.getItem(resumeBindingKey(missionId)));
}

export function writeResumeBound(missionId: string, mode: "master" | "upload" | "paste"): void {
  window.localStorage.setItem(resumeBindingKey(missionId), JSON.stringify({ mode, boundAt: new Date().toISOString() }));
}

export function readTargetConfirmed(missionId: string): boolean {
  if (typeof window === "undefined") return false;
  return window.localStorage.getItem(targetConfirmedKey(missionId)) === "1";
}

export function writeTargetConfirmed(missionId: string, value: boolean): void {
  if (value) window.localStorage.setItem(targetConfirmedKey(missionId), "1");
  else window.localStorage.removeItem(targetConfirmedKey(missionId));
}

export function isDebugMode(): boolean {
  if (typeof window === "undefined") return false;
  return new URLSearchParams(window.location.search).get(DEBUG_QUERY) === "1";
}

export async function createDraftProfile(apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<{ profile_id: string; experiences?: unknown[] }> {
  const response = await request(`${apiUrl}/api/v1/profiles/draft`, { method: "POST" });
  const profile = await readApiPayload<{ profile_id?: string; id?: string; experiences?: unknown[] }>(response);
  const profileId = String(profile.profile_id ?? profile.id ?? "");
  if (!profileId) throw new Error("创建档案失败");
  return { profile_id: profileId, experiences: profile.experiences };
}

export async function ingestResumePdf(profileId: string, file: File, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<{ profile_id: string; experiences: unknown[] }> {
  const body = new FormData();
  body.append("file", file);
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/resumes`, { method: "POST", body });
  const profile = await readApiPayload<{ profile_id?: string; id?: string; experiences?: unknown[] }>(response);
  return { profile_id: String(profile.profile_id ?? profile.id ?? profileId), experiences: profile.experiences ?? [] };
}

export async function ingestResumeText(profileId: string, rawText: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<{ profile_id: string; experiences: unknown[] }> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/resumes/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  });
  const profile = await readApiPayload<{ profile_id?: string; id?: string; experiences?: unknown[] }>(response);
  return { profile_id: String(profile.profile_id ?? profile.id ?? profileId), experiences: profile.experiences ?? [] };
}


export type MissionResumeBindResult = {
  mission: Mission;
  profile_id: string;
  bound_profile_id: string;
  isolation: string;
  updated_master: boolean;
  experiences: unknown[];
  affected_missions?: Array<{
    id: string;
    display_name?: string;
    company?: string;
    role?: string;
    affected_by_master_update?: boolean;
  }>;
};

/** Mission-scoped PDF bind (copy-on-write). Does not overwrite Master unless updateMaster=true. */
export async function bindMissionResumePdf(
  missionId: string,
  file: File,
  options: { updateMaster?: boolean } = {},
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<MissionResumeBindResult> {
  const body = new FormData();
  body.append("file", file);
  body.append("update_master", options.updateMaster ? "true" : "false");
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/resumes`, {
    method: "POST",
    body,
  });
  return readApiPayload<MissionResumeBindResult>(response);
}

/** Mission-scoped paste bind (copy-on-write). Does not overwrite Master unless updateMaster=true. */
export async function bindMissionResumeText(
  missionId: string,
  rawText: string,
  options: { updateMaster?: boolean } = {},
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<MissionResumeBindResult> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/resumes/text`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText, update_master: Boolean(options.updateMaster) }),
  });
  return readApiPayload<MissionResumeBindResult>(response);
}

export async function readMasterResumeImpact(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<{ profile_id: string; missions: Array<{ id: string; display_name?: string; company?: string; role?: string; affected_by_master_update?: boolean }> }> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/master-resume-impact`);
  return readApiPayload(response);
}

export async function readProfile(profileId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<ProfileSnapshot> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}`);
  const profile = await readApiPayload<{
    profile_id?: string;
    id?: string;
    experiences?: ProfileExperience[];
    status?: string;
    full_name?: string | null;
    display_name?: string | null;
    name?: string | null;
    email?: string | null;
    phone?: string | null;
    location?: string | null;
    headline?: string | null;
    summary?: string | null;
    education?: ProfileEducation[];
    skills?: Array<ProfileSkill | string>;
    certifications?: ProfileCertification[];
  }>(response);
  return {
    profile_id: String(profile.profile_id ?? profile.id ?? profileId),
    experiences: profile.experiences ?? [],
    status: profile.status,
    full_name: profile.full_name ?? null,
    display_name: profile.display_name ?? null,
    name: profile.name ?? null,
    email: profile.email ?? null,
    phone: profile.phone ?? null,
    location: profile.location ?? null,
    headline: profile.headline ?? null,
    summary: profile.summary ?? null,
    education: profile.education ?? [],
    skills: profile.skills ?? [],
    certifications: profile.certifications ?? [],
  };
}

export async function listMissions(profileId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission[]> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/job-missions`);
  return readApiPayload<Mission[]>(response);
}

export async function createMission(profileId: string, rawText: string, sourceUrl: string | null, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/job-missions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText, ...(sourceUrl ? { source_url: sourceUrl } : {}) }),
  });
  return readApiPayload<Mission>(response);
}

export async function readMission(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}`);
  return readApiPayload<Mission>(response);
}

export async function archiveMission(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/archive`, { method: "POST" });
  return readApiPayload<Mission>(response);
}

/** Hard-delete a job mission. Prefer archiveMission for soft-remove from the home list. */
export async function deleteMission(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<{ deleted: boolean; id: string }> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}`, { method: "DELETE" });
  return readApiPayload<{ deleted: boolean; id: string }>(response);
}


export async function reanalyzeMission(missionId: string, rawText: string, sourceUrl: string | null = null, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/reanalyze`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText, ...(sourceUrl ? { source_url: sourceUrl } : {}) }),
  });
  return readApiPayload<Mission>(response);
}

export async function updateMissionIdentity(missionId: string, payload: { company: string; role: string; role_family: string; seniority: string; location?: string | null }, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/identity`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return readApiPayload<Mission>(response);
}

export async function generateMissionStep<T>(missionId: string, step: "experience-selection/generate" | "resume-strategy" | "target-resumes" | "red-team" | "interview-pack" | "claim-analysis", apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<T> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/${step}`, { method: "POST" });
  return readApiPayload<T>(response);
}

export async function readTargetResumes(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<TargetResume[]> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/target-resumes`);
  return readApiPayload<TargetResume[]>(response);
}

export async function readExperienceSelection(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<ExperienceSelection[]> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/experience-selection`);
  const payload = await readApiPayload<{ selections: ExperienceSelection[] }>(response);
  return payload.selections ?? [];
}

export async function saveExperienceSelection(missionId: string, selections: ExperienceSelection[], apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch, confirm = false): Promise<ExperienceSelection[]> {
  const qs = confirm ? "?confirm=true" : "";
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/experience-selection${qs}`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ selections: selections.map(({ experience_id, decision, why, related_capabilities, supporting_evidence_refs, confidence }) => ({ experience_id, decision, why, related_capabilities, supporting_evidence_refs, confidence })) }),
  });
  const payload = await readApiPayload<{ selections: ExperienceSelection[] }>(response);
  return payload.selections ?? [];
}

export async function regenerateResumeOptimization(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<ExperienceSelection[]> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/resume-optimization/regenerate`, { method: "POST" });
  const payload = await readApiPayload<{ selections: ExperienceSelection[] }>(response);
  return payload.selections ?? [];
}

export async function updateResumeBullet(bulletId: string, payload: { status?: TargetResumeBullet["status"]; final_text?: string; fact_confirmed?: boolean }, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<TargetResumeBullet> {
  const response = await request(`${apiUrl}/api/v1/target-resume-bullets/${encodeURIComponent(bulletId)}`, { method: "PATCH", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return readApiPayload<TargetResumeBullet>(response);
}

export type MissionProofSnapshot = {
  targetJob?: Record<string, unknown> | null;
  claim?: Record<string, unknown> | null;
  session?: {
    id?: string;
    status?: string;
    mission_id?: string | null;
    round_count?: number;
    strong_points?: string[];
    weak_points?: string[];
    gap_type?: string | null;
    gap_why?: string | null;
    recommended_next_action?: string | null;
    updated_at?: string | null;
  } | null;
  latest_completed_session?: MissionProofSnapshot["session"];
  sessions?: Array<Record<string, unknown>>;
};

/** Mission-scoped proof snapshot (includes latest interview session for result reflow). */
export async function readMissionProofSnapshot(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<MissionProofSnapshot> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/proof-snapshot`);
  return readApiPayload<MissionProofSnapshot>(response);
}

export async function readProofState(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<ProofState> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/proof`);
  return readApiPayload<ProofState>(response);
}

export async function readReadiness(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Readiness> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/readiness`);
  return readApiPayload<Readiness>(response);
}

export type RedTeamReport = {
  id?: string;
  mission_id?: string;
  target_resume_id?: string;
  findings: Array<Record<string, unknown>>;
  created_at?: string;
};

export async function readRedTeam(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<RedTeamReport> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/red-team`);
  const payload = await readApiPayload<RedTeamReport & { report_id?: string; report?: RedTeamReport }>(response);
  const nested = payload?.report && typeof payload.report === "object" ? payload.report : null;
  const id = payload?.id ?? payload?.report_id ?? nested?.id;
  const created_at = payload?.created_at ?? nested?.created_at;
  const findings = Array.isArray(payload?.findings)
    ? payload.findings
    : Array.isArray(nested?.findings)
      ? nested!.findings!
      : [];
  return {
    ...payload,
    id: id != null && String(id).trim() ? String(id) : undefined,
    created_at: created_at != null && String(created_at).trim() ? String(created_at) : undefined,
    findings,
  };
}

export async function readInterviewPack(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<{ topics: Array<Record<string, unknown>> }> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/interview-pack`);
  return readApiPayload<{ topics: Array<Record<string, unknown>> }>(response);
}

export async function recoverEvidence(missionId: string, payload: Record<string, unknown>, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Record<string, unknown>> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/recover-evidence`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return readApiPayload<Record<string, unknown>>(response);
}

export async function generateProofActionsForMission(missionId: string, claimId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Array<Record<string, unknown>>> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/proof-actions?claim_id=${encodeURIComponent(claimId)}`, { method: "POST" });
  const payload = await readApiPayload<unknown>(response);
  if (Array.isArray(payload)) return payload as Array<Record<string, unknown>>;
  if (payload && typeof payload === "object") {
    const rec = payload as Record<string, unknown>;
    const actions = rec.proof_actions;
    if (Array.isArray(actions) && actions.length > 0) return actions as Array<Record<string, unknown>>;
    const message = String(rec.message || rec.next_action || "").trim();
    if (message) throw new Error(message);
  }
  throw new Error("当前无法生成可执行补强动作。请先确认档案，或重新生成当前岗位的主张分析。");
}

export async function submitMissionProofArtifact(
  actionId: string,
  payload: { action_id: string; artifact_type: string; artifact_url?: string; artifact_text?: string; manually_confirmed?: boolean },
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<Record<string, unknown>> {
  const response = await request(`${apiUrl}/api/v1/proof-actions/${encodeURIComponent(actionId)}/artifacts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
  return readApiPayload<Record<string, unknown>>(response);
}

export async function submitMissionOutcome(missionId: string, payload: Record<string, unknown>, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Record<string, unknown>> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/outcomes`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
  return readApiPayload<Record<string, unknown>>(response);
}


export async function confirmResumeSource(
  missionId: string,
  mode: "master" | "upload" | "paste",
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
  options?: { updateMaster?: boolean },
): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/confirm-resume-source`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ mode, update_master: Boolean(options?.updateMaster) }),
  });
  return readApiPayload<Mission>(response);
}

export async function confirmStrategy(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/confirm-strategy`, { method: "POST" });
  return readApiPayload<Mission>(response);
}

export async function confirmTargetResume(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/confirm-target-resume`, { method: "POST" });
  return readApiPayload<Mission>(response);
}

export async function advanceMission(missionId: string, event: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/advance`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ event, user_confirmed: true }),
  });
  return readApiPayload<Mission>(response);
}

export async function retryCompanyIntel(missionId: string, apiUrl = MISSION_API_BASE_URL, request: MissionRequester = fetch): Promise<Mission> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/retry-company-intel`, { method: "POST" });
  return readApiPayload<Mission>(response);
}
