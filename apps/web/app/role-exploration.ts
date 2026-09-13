import type { CareerPreferencePriority, CareerPreferencesDraft } from "./career-preferences.ts";
import { isCareerPreferencesDraftValid } from "./career-preferences.ts";
import type { Profile, ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";

export type RoleCode =
  | "AI_PRODUCT_MANAGER"
  | "AI_APPLICATION_ENGINEER"
  | "AI_SOLUTION_CONSULTANT"
  | "LLM_ALGORITHM_ENGINEER"
  | "AI_DATA_ANALYST"
  | "AI_PRODUCT_OPERATIONS";

export type RoleExplorationLevel = "RECOMMENDED" | "POSSIBLE" | "LOW_PRIORITY";

export type RoleExplorationItem = {
  role_code: RoleCode;
  role_name: string;
  level: RoleExplorationLevel;
  reasons: string[];
  concerns: string[];
  evidence_refs: string[];
  preference_refs: CareerPreferencePriority[];
};

export type RoleExplorationResult = {
  role_profile_version: string;
  items: RoleExplorationItem[];
};

export type RoleExplorationRead = {
  id: string;
  profile_id: string;
  role_profile_version: string;
  result: RoleExplorationResult;
  created_at: string;
  updated_at: string;
};

export const ROLE_EXPLORATION_LEVEL_LABELS: Record<RoleExplorationLevel, string> = {
  RECOMMENDED: "推荐",
  POSSIBLE: "可探索",
  LOW_PRIORITY: "暂不优先",
};

export const ROLE_EXPLORATION_DISCLAIMER =
  "本探索基于已确认的 Profile、已保存的职业偏好与内置岗位知识（confirmed Profile + saved preferences + built-in role knowledge）；未使用真实 JD (no real JD)。";

/** A result may only be requested once the profile and its preferences are persisted. */
export function profileCanExploreRoles(profile: Profile | null): boolean {
  const preferences = profile?.preferences;
  if (profile?.status !== "CONFIRMED" || !preferences) return false;
  return isCareerPreferencesDraftValid(
    [...preferences.priority_order],
    String(preferences.weekly_hours),
  );
}

export type RoleExplorationInputKey = string;

/** Identifies the persisted inputs a request uses, but only while the draft still matches them. */
export function roleExplorationInputKey(
  profile: Profile | null,
  draft: CareerPreferencesDraft,
): RoleExplorationInputKey | null {
  if (!profileCanExploreRoles(profile) || !profile?.preferences) return null;
  const preferences = profile.preferences;
  const draftMatchesPersisted =
    preferences.priority_order.length === draft.priority_order.length &&
    preferences.priority_order.every((value, index) => value === draft.priority_order[index]) &&
    String(preferences.weekly_hours) === draft.weekly_hours;
  if (!draftMatchesPersisted) return null;
  return JSON.stringify([
    profile.profile_id,
    preferences.priority_order,
    preferences.weekly_hours,
  ]);
}

/** A response is current only if the live profile and preference draft retain its request identity. */
export function roleExplorationInputMatches(
  captured: RoleExplorationInputKey | null,
  profile: Profile | null,
  draft: CareerPreferencesDraft,
): boolean {
  return captured !== null && captured === roleExplorationInputKey(profile, draft);
}

/** Read the latest persisted snapshot. A missing snapshot is an expected empty state. */
export async function getRoleExplorationRequest(
  profileId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<RoleExplorationRead | null> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/role-exploration`, { method: "GET" });
  if (response.status === 404) {
    const payload = await response.clone().json().catch(() => null) as { detail?: unknown } | null;
    if (payload?.detail === "Role exploration has not been generated") return null;
  }
  return readApiPayload<RoleExplorationRead>(response);
}

/** Create (or refresh) the latest snapshot for a profile. */
export async function createRoleExplorationRequest(
  profileId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<RoleExplorationRead> {
  const response = await request(`${apiUrl}/api/v1/role-explorations`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ profile_id: profileId }),
  });
  return readApiPayload<RoleExplorationRead>(response);
}

export type RoleExplorationCardData = RoleExplorationItem & { level_label: string };

/** Pure mapping used by the UI, retaining references for transparent grounding. */
export function roleExplorationViewData(snapshot: RoleExplorationRead | null): RoleExplorationCardData[] {
  if (!snapshot) return [];
  return snapshot.result.items.map((item) => ({
    ...item,
    reasons: [...item.reasons],
    concerns: [...item.concerns],
    evidence_refs: [...item.evidence_refs],
    preference_refs: [...item.preference_refs],
    level_label: ROLE_EXPLORATION_LEVEL_LABELS[item.level],
  }));
}

export const isRoleExplorationReady = profileCanExploreRoles;
export const explorationLevelLabel = (level: RoleExplorationLevel): string => ROLE_EXPLORATION_LEVEL_LABELS[level];
