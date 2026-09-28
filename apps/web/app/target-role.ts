import type { ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";
import type { RoleCode } from "./role-exploration.ts";
import type { RoleExplorationRead } from "./role-exploration.ts";

export type TargetRoleCode = RoleCode;

export const TARGET_ROLE_CODES = [
  "AI_PRODUCT_MANAGER",
  "AI_APPLICATION_ENGINEER",
  "AI_SOLUTION_CONSULTANT",
  "LLM_ALGORITHM_ENGINEER",
  "AI_DATA_ANALYST",
  "AI_PRODUCT_OPERATIONS",
] as const satisfies readonly TargetRoleCode[];

export type TargetRoleRead = {
  id: string;
  profile_id: string;
  role_code: TargetRoleCode;
  role_name: string;
  role_profile_version: string;
  role_exploration_id: string;
  selected_at: string;
  updated_at: string;
};

export function targetRoleMatchesExploration(
  targetRole: TargetRoleRead | null,
  exploration: RoleExplorationRead | null,
): targetRole is TargetRoleRead {
  return Boolean(
    targetRole &&
      exploration &&
      targetRole.profile_id === exploration.profile_id &&
      targetRole.role_exploration_id === exploration.id &&
      exploration.result.items.some((item) => item.role_code === targetRole.role_code),
  );
}

/** Read the current user selection. A missing selection is an expected empty state. */
export async function getTargetRoleRequest(
  profileId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<TargetRoleRead | null> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/target-role`, { method: "GET" });
  if (response.status === 404 || response.status === 409) {
    const payload = await response.clone().json().catch(() => null) as { detail?: unknown } | null;
    if (
      payload?.detail === "Target role has not been selected" ||
      payload?.detail === "Target role requires a confirmed profile" ||
      payload?.detail === "Career preferences are required before target role selection" ||
      payload?.detail === "Role exploration is required before target role selection"
    ) return null;
  }
  return readApiPayload<TargetRoleRead>(response);
}

/** Save or replace the single current selection. */
export async function selectTargetRoleRequest(
  profileId: string,
  roleCode: TargetRoleCode,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<TargetRoleRead> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/target-role`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ role_code: roleCode }),
  });
  return readApiPayload<TargetRoleRead>(response);
}

/** Pure view projection used by the page and tests. */
export function targetRoleViewData(targetRole: TargetRoleRead | null) {
  if (!targetRole) return null;
  return {
    role_code: targetRole.role_code,
    role_name: targetRole.role_name,
    role_profile_version: targetRole.role_profile_version,
    role_exploration_id: targetRole.role_exploration_id,
  };
}
