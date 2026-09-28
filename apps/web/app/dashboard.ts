import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";
import type { GapRead } from "./gap-analysis.ts";
import type { PriorityRead } from "./priorities.ts";
import type { RoadmapTaskRead } from "./roadmap.ts";

export type DashboardRead = {
  target_role: { id: string; role_code: string; role_name: string } | null;
  jd_sample_count: number;
  market_ready: boolean;
  top_requirements: Array<{ name: string; category: string; occurrence_count: number; frequency_ratio: number }>;
  top_gaps: GapRead[];
  confirmed_priorities: PriorityRead[];
  current_week: number | null;
  upcoming_tasks: RoadmapTaskRead[];
  progress_ratio: number;
  roadmap_id: string | null;
  replan_available: boolean;
};

export async function getDashboardRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<DashboardRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/dashboard`, { method: "GET" });
  return readApiPayload<DashboardRead>(response);
}
