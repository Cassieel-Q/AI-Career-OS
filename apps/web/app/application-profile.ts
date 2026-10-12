/**
 * 网申资料（ApplicationProfile）客户端（目标四）。
 *
 * 边界：ResumeProfile = 简历可用内容；ApplicationProfile = 身份证号 / 家庭 / 健康 /
 * 档案 / 紧急联系人 / 到岗时间等**网申填表**字段。简历生成只读 ResumeProfile；
 * 网申填表读两者。助手默认**不能**读敏感 ApplicationProfile 字段。
 */
import { MISSION_API_BASE_URL } from "./missions.ts";

export const APPLICATION_PROFILE_FIELDS = [
  { key: "id_number", label: "身份证号", sensitive: true },
  { key: "family_info", label: "家庭情况", sensitive: true },
  { key: "health_status", label: "健康状况", sensitive: true },
  { key: "archive_location", label: "档案所在地", sensitive: true },
  { key: "emergency_contact", label: "紧急联系人", sensitive: true },
  { key: "emergency_phone", label: "紧急联系电话", sensitive: true },
  { key: "availability", label: "到岗时间", sensitive: false },
] as const;

export type ApplicationProfileFieldKey = (typeof APPLICATION_PROFILE_FIELDS)[number]["key"];

export type ApplicationProfile = Partial<Record<ApplicationProfileFieldKey, string | null>>;

export type ResumeFacts = {
  profile_id: string;
  [key: string]: unknown;
};

export class ApplicationProfileApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message || "网申资料请求失败。");
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new ApplicationProfileApiError(response.status, body.detail ?? body);
  }
  return response.json() as Promise<T>;
}

const base = (profileId: string) => `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}`;

export const readApplicationProfile = (profileId: string) =>
  request<ApplicationProfile>(`${base(profileId)}/application-profile`);

export const saveApplicationProfile = (profileId: string, payload: ApplicationProfile) =>
  request<ApplicationProfile>(`${base(profileId)}/application-profile`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });

/** 简历生成可读的事实（不含网申敏感字段）。 */
export const readResumeFacts = (profileId: string) => request<ResumeFacts>(`${base(profileId)}/resume-facts`);

/** 网申填表可读：ResumeProfile + ApplicationProfile。 */
export const readApplicationFillFacts = (profileId: string) =>
  request<Record<string, unknown>>(`${base(profileId)}/application-fill-facts`);

/** 只保留非空字段提交，避免把空白写成 null 覆盖已有内容。 */
export function compactApplicationProfile(payload: ApplicationProfile): ApplicationProfile {
  const result: ApplicationProfile = {};
  for (const { key } of APPLICATION_PROFILE_FIELDS) {
    const value = payload[key];
    if (value !== undefined && value !== null && String(value).trim() !== "") {
      result[key] = String(value).trim();
    }
  }
  return result;
}
