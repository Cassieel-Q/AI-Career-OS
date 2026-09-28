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
import { getMarketProfileRequest } from "./market-profile.ts";
import type { MarketProfileRead } from "./market-profile.ts";
import { getGapAnalysisRequest } from "./gap-analysis.ts";
import type { GapAnalysisRead } from "./gap-analysis.ts";
import { getPrioritiesRequest } from "./priorities.ts";
import type { PriorityListRead } from "./priorities.ts";
import { getRoadmapRequest } from "./roadmap.ts";
import type { RoadmapRead } from "./roadmap.ts";
import { getDashboardRequest } from "./dashboard.ts";
import type { DashboardRead } from "./dashboard.ts";

export type WorkflowStep =
  | "profile"
  | "preferences"
  | "role-exploration"
  | "job-descriptions"
  | "market-profile"
  | "gap-analysis"
  | "priorities"
  | "roadmap"
  | "progress"
  | "dashboard";

export type WorkflowSnapshot = {
  profile: Profile | null;
  roleExploration: RoleExplorationRead | null;
  targetRole: TargetRoleRead | null;
  jobDescriptions: JobDescriptionRead[];
  marketProfile: MarketProfileRead | null;
  gapAnalysis: GapAnalysisRead | null;
  priorities: PriorityListRead | null;
  roadmap: RoadmapRead | null;
  dashboard: DashboardRead | null;
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
  "job-descriptions",
  "market-profile",
  "gap-analysis",
  "priorities",
  "roadmap",
  "progress",
  "dashboard",
];

export const API_BASE_URL = process.env.NEXT_PUBLIC_API_BASE_URL ?? "http://127.0.0.1:8000";

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

function hasMarketProfile(snapshot: WorkflowSnapshot): boolean {
  return Boolean(snapshot.marketProfile?.status === "VALID" && snapshot.marketProfile.target_role_id === snapshot.targetRole?.id);
}

function hasGapAnalysis(snapshot: WorkflowSnapshot): boolean {
  return Boolean(hasMarketProfile(snapshot) && snapshot.gapAnalysis?.status === "VALID" && snapshot.gapAnalysis.market_profile_id === snapshot.marketProfile?.id);
}

function hasPriorities(snapshot: WorkflowSnapshot): boolean {
  const priorities = snapshot.priorities;
  return Boolean(hasGapAnalysis(snapshot) && priorities && priorities.gap_analysis_id === snapshot.gapAnalysis?.id && priorities.items.length > 0);
}

function hasRoadmap(snapshot: WorkflowSnapshot): boolean {
  return Boolean(hasPriorities(snapshot) && snapshot.roadmap?.status === "VALID" && snapshot.roadmap.weeks.length === 4);
}

export function workflowCompletion(snapshot: WorkflowSnapshot): Record<WorkflowStep, boolean> {
  const profileComplete = snapshot.profile?.status === "CONFIRMED";
  const preferencesComplete = profileComplete && hasValidPreferences(snapshot.profile);
  const explorationComplete = preferencesComplete && hasCurrentExploration(snapshot);
  const targetRoleComplete = explorationComplete && hasCurrentTargetRole(snapshot);
  const jobDescriptionsComplete = targetRoleComplete && currentJobDescriptions(snapshot).length >= MINIMUM_JOB_DESCRIPTIONS;
  const marketProfileComplete = jobDescriptionsComplete && hasMarketProfile(snapshot);
  const gapAnalysisComplete = marketProfileComplete && hasGapAnalysis(snapshot);
  const prioritiesComplete = gapAnalysisComplete && hasPriorities(snapshot);
  const roadmapComplete = prioritiesComplete && hasRoadmap(snapshot);

  return {
    profile: profileComplete,
    preferences: preferencesComplete,
    // The canonical Role Selection page owns both AI exploration and the
    // user's persisted target choice. Backend records remain separate.
    "role-exploration": targetRoleComplete,
    "job-descriptions": jobDescriptionsComplete,
    "market-profile": marketProfileComplete,
    "gap-analysis": gapAnalysisComplete,
    priorities: prioritiesComplete,
    roadmap: roadmapComplete,
    progress: roadmapComplete,
    dashboard: roadmapComplete,
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
  if (step === "job-descriptions") return hasCurrentTargetRole(snapshot);
  if (!hasCurrentTargetRole(snapshot) || currentJobDescriptions(snapshot).length < MINIMUM_JOB_DESCRIPTIONS) return false;
  if (step === "market-profile") return true;
  if (!hasMarketProfile(snapshot)) return false;
  if (step === "gap-analysis") return true;
  if (!hasGapAnalysis(snapshot)) return false;
  if (step === "priorities") return true;
  if (!hasPriorities(snapshot)) return false;
  if (step === "roadmap") return true;
  if (!hasRoadmap(snapshot)) return false;
  return step === "progress" || step === "dashboard";
}

export function latestValidStep(snapshot: WorkflowSnapshot): WorkflowStep | "start" {
  if (!snapshot.profile) return "start";
  if (snapshot.profile.status !== "CONFIRMED") return "profile";
  if (!hasValidPreferences(snapshot.profile)) return "preferences";
  if (!hasCurrentExploration(snapshot) || !hasCurrentTargetRole(snapshot)) return "role-exploration";
  if (currentJobDescriptions(snapshot).length < MINIMUM_JOB_DESCRIPTIONS) return "job-descriptions";
  if (!hasMarketProfile(snapshot)) return "market-profile";
  if (!hasGapAnalysis(snapshot)) return "gap-analysis";
  if (!hasPriorities(snapshot)) return "priorities";
  if (!hasRoadmap(snapshot)) return "roadmap";
  return "dashboard";
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
  let marketProfile: MarketProfileRead | null = null;
  let gapAnalysis: GapAnalysisRead | null = null;
  let priorities: PriorityListRead | null = null;
  let roadmap: RoadmapRead | null = null;
  let dashboard: DashboardRead | null = null;

  if (profileCanExploreRoles(profile)) {
    roleExploration = await getRoleExplorationRequest(profile.profile_id, apiUrl, request);
    if (roleExploration && roleExploration.profile_id === profile.profile_id) {
      targetRole = await getTargetRoleRequest(profile.profile_id, apiUrl, request);
      if (targetRole && targetRoleMatchesExploration(targetRole, roleExploration)) {
        const jobDescriptionState = await getJobDescriptionsStateRequest(targetRole.id, apiUrl, request);
        jobDescriptions = jobDescriptionState.records;
        if (jobDescriptionState.targetMissing) targetRole = null;
        if (targetRole && jobDescriptions.length >= MINIMUM_JOB_DESCRIPTIONS) {
          marketProfile = await getMarketProfileRequest(targetRole.id, apiUrl, request);
          if (marketProfile) {
            gapAnalysis = await getGapAnalysisRequest(profile.profile_id, apiUrl, request);
            if (gapAnalysis) {
              priorities = await getPrioritiesRequest(profile.profile_id, apiUrl, request);
              if (priorities) {
                roadmap = await getRoadmapRequest(profile.profile_id, apiUrl, request);
                if (roadmap) dashboard = await getDashboardRequest(profile.profile_id, apiUrl, request);
              }
            }
          }
        }
      }
    }
  }

  return { profile, roleExploration, targetRole, jobDescriptions, marketProfile, gapAnalysis, priorities, roadmap, dashboard };
}
