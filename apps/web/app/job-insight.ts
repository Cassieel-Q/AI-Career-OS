/**
 * 岗位洞察前端接口：岗位关键词分析、简历×岗位匹配度、简历原文读写。
 *
 * 对应后端 `app/job_insight_routes.py`。列表页只读缓存（`/api/v1/plaza` 已带摘要字段），
 * 抽屉与岗位页按需拉取明细，点「重新分析」才 POST 触发模型。
 */
import { readApiPayload } from "./profile-flow.ts";
import { MISSION_API_BASE_URL, type MissionRequester } from "./missions.ts";

export type JobKeywordAnalysis = {
  keywords: string[];
  summary: string;
  source: string;
  generated_at?: string;
};

export type JobMatchVerdict = "strong" | "maybe" | "weak";

export type JobMatchAnalysis = {
  score: number;
  verdict: JobMatchVerdict | string;
  verdict_label?: string;
  reasons: string[];
  gaps: string[];
  advice: string;
  source: string;
  /** EDITED_TEXT = 用简历工作台里的原文；PROFILE_FACTS = 用已确认事实拼的；MISSING = 没有简历 */
  resume_source?: string;
  resume_chars?: number;
  generated_at?: string;
};

export type ResumeTextRead = {
  profile_id: string;
  raw_text: string;
  source: "EDITED_TEXT" | "PROFILE_FACTS" | "MISSING" | string;
};

/** 结论 → 徽章配色：值得投递 / 先补齐再投 / 暂不建议投递。 */
export function verdictTone(verdict: string | null | undefined): "good" | "warn" | "bad" | "muted" {
  if (verdict === "strong") return "good";
  if (verdict === "maybe") return "warn";
  if (verdict === "weak") return "bad";
  return "muted";
}

export function verdictLabel(verdict: string | null | undefined, fallback = "待评估"): string {
  if (verdict === "strong") return "值得投递";
  if (verdict === "maybe") return "先补齐再投";
  if (verdict === "weak") return "暂不建议投递";
  return fallback;
}

/** 来源标注：模型分析 / 本地规则估算。 */
export function sourceLabel(source: string | null | undefined): string {
  if (source === "LLM") return "模型分析";
  if (source === "LOCAL_RULE") return "本地规则估算";
  return "尚未分析";
}

export async function fetchJobKeywords(
  missionId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<JobKeywordAnalysis> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/job-analysis`);
  return readApiPayload<JobKeywordAnalysis>(response);
}

export async function refreshJobKeywords(
  missionId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<JobKeywordAnalysis> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/job-analysis`, {
    method: "POST",
  });
  return readApiPayload<JobKeywordAnalysis>(response);
}

export async function fetchJobMatch(
  missionId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<JobMatchAnalysis> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/match-analysis`);
  return readApiPayload<JobMatchAnalysis>(response);
}

export async function refreshJobMatch(
  missionId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<JobMatchAnalysis> {
  const response = await request(`${apiUrl}/api/v1/job-missions/${encodeURIComponent(missionId)}/match-analysis`, {
    method: "POST",
  });
  return readApiPayload<JobMatchAnalysis>(response);
}

export async function fetchResumeText(
  profileId: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ResumeTextRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/resume-text`);
  return readApiPayload<ResumeTextRead>(response);
}

export async function saveResumeText(
  profileId: string,
  rawText: string,
  apiUrl = MISSION_API_BASE_URL,
  request: MissionRequester = fetch,
): Promise<ResumeTextRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}/resume-text`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ raw_text: rawText }),
  });
  return readApiPayload<ResumeTextRead>(response);
}
