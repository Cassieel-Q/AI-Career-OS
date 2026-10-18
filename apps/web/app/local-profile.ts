import { MISSION_API_BASE_URL, type MissionRequester } from "./missions.ts";

/** 本机档案恢复与「无模型建档」接口封装。 */

const CLIENT_HEADER_NAME = "X-AI-Career-Client";
const CLIENT_HEADER_VALUE = "ai-career-web";

export type LocalProfileSummary = {
  profile_id: string;
  label: string;
  status: string;
  experience_count: number;
  created_at: string | null;
  updated_at: string | null;
};

export type LocalIngestResult = {
  profile_id: string;
  parse_source: string;
  parsed_counts: {
    education: number;
    skills: number;
    experiences: number;
    certifications: number;
  };
  [key: string]: unknown;
};

async function request<T>(url: string, init: RequestInit = {}, send: MissionRequester = fetch): Promise<T> {
  const response = await send(url, {
    ...init,
    headers: { [CLIENT_HEADER_NAME]: CLIENT_HEADER_VALUE, ...(init.headers ?? {}) },
  });
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `本地档案接口请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

/** 本机已有档案的轻量列表（不含简历正文），用于清了浏览器存储后恢复。 */
export const readLocalProfiles = (send: MissionRequester = fetch) =>
  request<{ profiles: LocalProfileSummary[]; total: number; truncated: boolean }>(
    `${MISSION_API_BASE_URL}/api/v1/local/profiles`,
    {},
    send,
  );

/** 不调用模型的建档：只按规则切分原文，每条都带原文证据。 */
export const ingestResumeLocally = (
  profileId: string,
  rawText: string,
  send: MissionRequester = fetch,
) =>
  request<LocalIngestResult>(
    `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/resumes/local`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ raw_text: rawText }),
    },
    send,
  );
