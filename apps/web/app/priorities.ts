import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";

export type PriorityRead = {
  gap_id: string;
  requirement_name: string;
  state: string;
  severity: string;
  proximity: string;
  feasibility: string;
  frequency_ratio: number;
  system_rank: number;
  user_rank: number | null;
  effective_rank: number;
  lane: "NOW" | "NEXT" | "NOT_NOW";
  system_reason: string;
};
export type PriorityListRead = { gap_analysis_id: string; overridden: boolean; items: PriorityRead[] };

export async function getPrioritiesRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<PriorityListRead | null> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/priorities`, { method: "GET" });
  if (response.status === 404 || response.status === 409) return null;
  return readApiPayload<PriorityListRead>(response);
}

export async function savePrioritiesRequest(profileId: string, order: string[], apiUrl: string, request: ProfileRequester = fetch): Promise<PriorityListRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/priorities`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ order }),
  });
  return readApiPayload<PriorityListRead>(response);
}
