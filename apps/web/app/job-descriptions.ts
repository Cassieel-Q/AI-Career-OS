import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";
import type { TargetRoleRead } from "./target-role.ts";


export const MINIMUM_JOB_DESCRIPTIONS = 3;
export const MAXIMUM_JOB_DESCRIPTIONS = 10;

export type JobDescriptionRead = {
  id: string;
  target_role_id: string;
  raw_text: string;
  source_url: string | null;
  created_at: string;
  updated_at: string;
};

export type JobDescriptionCreate = {
  raw_text: string;
  source_url?: string | null;
};

export type JobDescriptionPatch = {
  raw_text?: string;
  source_url?: string | null;
};

export function normalizeJobDescriptionSourceUrl(value: string | null | undefined): string | null | undefined {
  if (value === undefined || value === null) return value;
  const trimmed = value.trim();
  return trimmed || null;
}

export function jobDescriptionReadiness(count: number) {
  return {
    ready: count >= MINIMUM_JOB_DESCRIPTIONS,
    remaining: Math.max(0, MINIMUM_JOB_DESCRIPTIONS - count),
  };
}

export function canAddJobDescription(count: number): boolean {
  return count < MAXIMUM_JOB_DESCRIPTIONS;
}

export function jobDescriptionWorkflowState(
  targetRole: TargetRoleRead | null,
  records: JobDescriptionRead[],
) {
  if (!targetRole) {
    return { available: false, targetRoleId: null, targetRoleName: null, records: [] };
  }
  return {
    available: true,
    targetRoleId: targetRole.id,
    targetRoleName: targetRole.role_name,
    records: records.filter((record) => record.target_role_id === targetRole.id),
  };
}

export async function getJobDescriptionsRequest(
  targetRoleId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<JobDescriptionRead[]> {
  const response = await request(`${apiUrl}/api/v1/target-roles/${targetRoleId}/job-descriptions`, {
    method: "GET",
  });
  return readApiPayload<JobDescriptionRead[]>(response);
}

export async function createJobDescriptionRequest(
  targetRoleId: string,
  payload: JobDescriptionCreate,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<JobDescriptionRead> {
  const normalizedPayload: JobDescriptionCreate = { raw_text: payload.raw_text };
  if ("source_url" in payload) normalizedPayload.source_url = normalizeJobDescriptionSourceUrl(payload.source_url);
  const response = await request(`${apiUrl}/api/v1/target-roles/${targetRoleId}/job-descriptions`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(normalizedPayload),
  });
  return readApiPayload<JobDescriptionRead>(response);
}

export async function updateJobDescriptionRequest(
  jdId: string,
  payload: JobDescriptionPatch,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<JobDescriptionRead> {
  const normalizedPayload: JobDescriptionPatch = {};
  if ("raw_text" in payload) normalizedPayload.raw_text = payload.raw_text;
  if ("source_url" in payload) normalizedPayload.source_url = normalizeJobDescriptionSourceUrl(payload.source_url);
  const response = await request(`${apiUrl}/api/v1/job-descriptions/${jdId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(normalizedPayload),
  });
  return readApiPayload<JobDescriptionRead>(response);
}

export async function deleteJobDescriptionRequest(
  jdId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<void> {
  const response = await request(`${apiUrl}/api/v1/job-descriptions/${jdId}`, { method: "DELETE" });
  if (!response.ok) await readApiPayload<unknown>(response);
}

export function addJobDescriptionToCollection(
  records: JobDescriptionRead[],
  created: JobDescriptionRead,
): JobDescriptionRead[] {
  return [...records, created];
}

export function updateJobDescriptionInCollection(
  records: JobDescriptionRead[],
  updated: JobDescriptionRead,
): JobDescriptionRead[] {
  return records.map((record) => record.id === updated.id ? updated : record);
}

export function removeJobDescriptionFromCollection(
  records: JobDescriptionRead[],
  jdId: string,
): JobDescriptionRead[] {
  return records.filter((record) => record.id !== jdId);
}
