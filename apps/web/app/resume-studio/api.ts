import { MISSION_API_BASE_URL } from "../missions.ts";
import type { StudioOperation, StudioPreview, StudioSourceDiff, StudioState, StudioTemplate } from "./types.ts";

export class StudioApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message || "简历工作台请求失败。");
    this.status = status;
    this.detail = detail;
  }
}

const root = (missionId: string) => `${MISSION_API_BASE_URL}/api/v1/job-missions/${encodeURIComponent(missionId)}/resume-studio`;

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new StudioApiError(response.status, body.detail ?? body);
  }
  return response.json() as Promise<T>;
}

export const readStudio = (missionId: string) => request<StudioState>(root(missionId));
export const readStudioSourceDiff = (missionId: string) => request<StudioSourceDiff>(`${root(missionId)}/source-diff`);
export const reimportStudio = (missionId: string, revision: number) =>
  request<StudioState>(`${root(missionId)}/reimport`, { method: "POST", headers: { "If-Match": String(revision) } });
export const readStudioTemplates = () => request<StudioTemplate[]>(`${MISSION_API_BASE_URL}/api/v1/resume-studio/templates`);
export const applyStudioOperation = (missionId: string, revision: number, operation: StudioOperation) =>
  request<StudioState>(root(missionId), {
    method: "PATCH", headers: { "Content-Type": "application/json", "If-Match": String(revision) },
    body: JSON.stringify(operation),
  });
export const renderStudio = (missionId: string, revision: number) =>
  request<StudioPreview>(`${root(missionId)}/preview`, {
    method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ revision }),
  });
export const confirmStudio = (missionId: string, revision: number) =>
  request<StudioState>(`${root(missionId)}/confirm`, { method: "POST", headers: { "If-Match": String(revision) } });
/**
 * 从响应头里取服务端给的文件名。
 * 优先 ``X-Resume-Filename``（服务端已转义），其次 ``Content-Disposition`` 的 filename*。
 */
export function filenameFromHeaders(headers: Headers, fallback: string): string {
  const direct = headers.get("X-Resume-Filename");
  if (direct) return decodeURIComponent(direct);
  const disposition = headers.get("Content-Disposition") || "";
  const encoded = disposition.match(/filename\*=UTF-8''([^;]+)/i)?.[1];
  return encoded ? decodeURIComponent(encoded) : fallback;
}

/** 下载 PDF。draft=true 导出草稿（文件名带 _DRAFT、正文盖草稿标记、可跳过未完成检查）。 */
export async function downloadStudioPdf(
  missionId: string,
  draft = false,
): Promise<{ blob: Blob; filename: string; draft: boolean }> {
  const suffix = draft ? "?draft=1" : "";
  const response = await fetch(`${root(missionId)}/pdf${suffix}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new StudioApiError(response.status, body.detail ?? body);
  }
  const filename = filenameFromHeaders(response.headers, draft ? "resume_DRAFT.pdf" : "resume.pdf");
  return { blob: await response.blob(), filename, draft };
}

export type StudioExportFormat = "markdown" | "txt" | "json";

/** 下载 Markdown / 纯文本 / JSON 导出（draft=true 允许导出草稿自检）。 */
export async function downloadStudioExport(missionId: string, format: StudioExportFormat, draft = false): Promise<{ blob: Blob; filename: string }> {
  const suffix = draft ? "&draft=1" : "";
  const response = await fetch(`${root(missionId)}/export?format=${format}${suffix}`);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new StudioApiError(response.status, body.detail ?? body);
  }
  const ext = format === "markdown" ? "md" : format;
  const filename = filenameFromHeaders(response.headers, `resume.${ext}`);
  return { blob: await response.blob(), filename };
}
