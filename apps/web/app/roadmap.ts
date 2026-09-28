import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";
import { roadmapErrorMessage, type RoadmapErrorCategory } from "./roadmap-ui.ts";

export type RoadmapTaskStatus = "TODO" | "IN_PROGRESS" | "DONE" | "SKIPPED";
export type RoadmapTaskRead = {
  id: string;
  gap_id: string | null;
  title: string;
  objective: string;
  estimated_minutes: number;
  completion_criteria: string;
  status: RoadmapTaskStatus;
  sort_order: number;
  completed_at: string | null;
};
export type RoadmapWeekRead = {
  id: string;
  week_number: number;
  objective: string;
  focus_gap_ids: string[];
  measurable_outcome: string;
  tasks: RoadmapTaskRead[];
};
export type RoadmapRead = {
  id: string;
  profile_id: string;
  revision: number;
  weekly_hours: number;
  status: string;
  progress_ratio: number;
  weeks: RoadmapWeekRead[];
};

export class RoadmapRequestError extends Error {
  readonly category: RoadmapErrorCategory;

  constructor(category: RoadmapErrorCategory) {
    super(roadmapErrorMessage(category));
    this.name = "RoadmapRequestError";
    this.category = category;
  }
}

function categoryForStatus(status: number): RoadmapErrorCategory {
  if (status === 504) return "TIMEOUT";
  if (status === 502) return "INVALID_RESPONSE";
  if (status === 503) return "UNAVAILABLE";
  return "NETWORK";
}

async function readRoadmapMutation<T>(response: Response): Promise<T> {
  try {
    return await readApiPayload<T>(response);
  } catch {
    throw new RoadmapRequestError(categoryForStatus(response.status));
  }
}

export async function getRoadmapRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<RoadmapRead | null> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/roadmap`, { method: "GET" });
  if (response.status === 404 || response.status === 409) return null;
  return readApiPayload<RoadmapRead>(response);
}
export async function createRoadmapRequest(profileId: string, apiUrl: string, request: ProfileRequester = fetch): Promise<RoadmapRead> {
  let response: Response;
  try {
    response = await request(`${apiUrl}/api/v1/profiles/${profileId}/roadmap`, { method: "POST" });
  } catch {
    throw new RoadmapRequestError("NETWORK");
  }
  return readRoadmapMutation<RoadmapRead>(response);
}
export async function updateRoadmapTaskRequest(taskId: string, status: RoadmapTaskStatus, apiUrl: string, request: ProfileRequester = fetch): Promise<RoadmapTaskRead> {
  const response = await request(`${apiUrl}/api/v1/roadmap-tasks/${taskId}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ status }),
  });
  return readApiPayload<RoadmapTaskRead>(response);
}
export async function replanRoadmapRequest(profileId: string, remainingWeeks: number, apiUrl: string, request: ProfileRequester = fetch): Promise<RoadmapRead> {
  let response: Response;
  try {
    response = await request(`${apiUrl}/api/v1/profiles/${profileId}/roadmap/replan`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ remaining_weeks: remainingWeeks }),
    });
  } catch {
    throw new RoadmapRequestError("NETWORK");
  }
  return readRoadmapMutation<RoadmapRead>(response);
}
