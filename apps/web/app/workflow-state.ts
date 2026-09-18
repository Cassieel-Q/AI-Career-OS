import type { CareerPreferences } from "./career-preferences.ts";
import type { Route } from "next";
import {
  getJobDescriptionsStateRequest,
  MINIMUM_JOB_DESCRIPTIONS,
} from "./job-descriptions.ts";
import type { JobDescriptionRead } from "./job-descriptions.ts";
import {
  normalizeProfile,
  readApiPayload,
} from "./profile-flow.ts";
import type { Profile, ProfileRequester } from "./profile-flow.ts";
import {
  getRoleExplorationRequest,
  profileCanExploreRoles,
} from "./role-exploration.ts";
import type { RoleExplorationRead } from "./role-exploration.ts";
import { getTargetRoleRequest, targetRoleMatchesExploration } from "./target-role.ts";
import type { TargetRoleRead } from "./target-role.ts";

export type WorkflowStep =
  | "profile"
  | "preferences"
  | "role-exploration"
  | "target-role"
  | "job-descriptions";

export type WorkflowSnapshot = {
  profile: Profile | null;
  roleExploration: RoleExplorationRead | null;
  targetRole: TargetRoleRead | null;
  jobDescriptions: JobDescriptionRead[];
};

export class WorkflowProfileNotFoundError extends Error {
  constructor() {
    super("Profile not found");
    this.name = "WorkflowProfileNotFoundError";
  }
}

export const WORKFLOW_STEPS: readonly WorkflowStep[] = [
  "profile",
  "preferences",
  "role-exploration",
  "target-role",
  "job-descriptions",
];

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://localhost:8000";

export function workflowHref(profileId: string, step: WorkflowStep): Route {
  return `/workflow/${encodeURIComponent(profileId)}/${step}` as Route;
}

function hasValidPreferences(profile: Profile | null): profile is Profile & { preferences: CareerPreferences } {
  return profileCanExploreRoles(profile);
}

function hasCurrentExploration(snapshot: WorkflowSnapshot): boolean {
  return Boolean(
    snapshot.profile &&
      hasValidPreferences(snapshot.profile) &&
      snapshot.roleExploration &&
      snapshot.roleExploration.profile_id === snapshot.profile.profile_id,
  );
}

function hasCurrentTargetRole(snapshot: WorkflowSnapshot): boolean {
  return Boolean(
    hasCurrentExploration(snapshot) &&
      snapshot.targetRole &&
      snapshot.targetRole.profile_id === snapshot.profile?.profile_id &&
      targetRoleMatchesExploration(snapshot.targetRole, snapshot.roleExploration),
  );
}

function currentJobDescriptions(snapshot: WorkflowSnapshot): JobDescriptionRead[] {
  if (!hasCurrentTargetRole(snapshot) || !snapshot.targetRole) return [];
  return snapshot.jobDescriptions.filter((record) => record.target_role_id === snapshot.targetRole?.id);
}

export function workflowCompletion(snapshot: WorkflowSnapshot): Record<WorkflowStep, boolean> {
  const profileComplete = snapshot.profile?.status === "CONFIRMED";
  const preferencesComplete = profileComplete && hasValidPreferences(snapshot.profile);
  const explorationComplete = preferencesComplete && hasCurrentExploration(snapshot);
  const targetRoleComplete = explorationComplete && hasCurrentTargetRole(snapshot);
  const jobDescriptionsComplete = targetRoleComplete && currentJobDescriptions(snapshot).length >= MINIMUM_JOB_DESCRIPTIONS;

  return {
    profile: profileComplete,
    preferences: preferencesComplete,
    "role-exploration": explorationComplete,
    "target-role": targetRoleComplete,
    "job-descriptions": jobDescriptionsComplete,
  };
}

export function canEnterStep(snapshot: WorkflowSnapshot, step: WorkflowStep): boolean {
  if (!snapshot.profile) return false;
  if (step === "profile") return true;
  if (snapshot.profile.status !== "CONFIRMED") return false;
  if (step === "preferences") return true;
  if (!hasValidPreferences(snapshot.profile)) return false;
  if (step === "role-exploration") return true;
  if (!hasCurrentExploration(snapshot)) return false;
  if (step === "target-role") return true;
  return hasCurrentTargetRole(snapshot);
}

export function latestValidStep(snapshot: WorkflowSnapshot): WorkflowStep | "start" {
  if (!snapshot.profile) return "start";
  if (snapshot.profile.status !== "CONFIRMED") return "profile";
  if (!hasValidPreferences(snapshot.profile)) return "preferences";
  if (!hasCurrentExploration(snapshot)) return "role-exploration";
  if (!hasCurrentTargetRole(snapshot)) return "target-role";
  return "job-descriptions";
}

export async function readWorkflowSnapshot(
  profileId: string,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<WorkflowSnapshot> {
  const profileResponse = await request(`${apiUrl}/api/v1/profiles/${encodeURIComponent(profileId)}`, { method: "GET" });
  if (profileResponse.status === 404) throw new WorkflowProfileNotFoundError();
  const profile = normalizeProfile(await readApiPayload<Profile>(profileResponse));
  let roleExploration: RoleExplorationRead | null = null;
  let targetRole: TargetRoleRead | null = null;
  let jobDescriptions: JobDescriptionRead[] = [];

  if (profileCanExploreRoles(profile)) {
    roleExploration = await getRoleExplorationRequest(profile.profile_id, apiUrl, request);
    if (roleExploration && roleExploration.profile_id === profile.profile_id) {
      targetRole = await getTargetRoleRequest(profile.profile_id, apiUrl, request);
      if (targetRole && targetRoleMatchesExploration(targetRole, roleExploration)) {
        const jobDescriptionState = await getJobDescriptionsStateRequest(targetRole.id, apiUrl, request);
        jobDescriptions = jobDescriptionState.records;
        if (jobDescriptionState.targetMissing) targetRole = null;
      }
    }
  }

  return { profile, roleExploration, targetRole, jobDescriptions };
}
