import type { Profile, ProfileRequester } from "./profile-flow.ts";
import { readApiPayload } from "./profile-flow.ts";

export type CareerPreferencePriority =
  | "COMPENSATION"
  | "LESS_CODING"
  | "FAST_EMPLOYMENT"
  | "CURRENT_FIT"
  | "LONG_TERM_GROWTH";

export type CareerPreferences = {
  id: string;
  profile_id: string;
  priority_order: [CareerPreferencePriority, CareerPreferencePriority];
  weekly_hours: number;
  created_at: string;
  updated_at: string;
};

export type CareerPreferencesDraft = {
  priority_order: CareerPreferencePriority[];
  weekly_hours: string;
};

export const CAREER_PREFERENCE_OPTIONS = [
  { value: "COMPENSATION", label: "薪资优先" },
  { value: "LESS_CODING", label: "少写代码" },
  { value: "FAST_EMPLOYMENT", label: "尽快就业" },
  { value: "CURRENT_FIT", label: "当前匹配度" },
  { value: "LONG_TERM_GROWTH", label: "长期成长" },
] as const satisfies ReadonlyArray<{ value: CareerPreferencePriority; label: string }>;

export function toggleCareerPreference(
  selected: CareerPreferencePriority[],
  value: CareerPreferencePriority,
): CareerPreferencePriority[] {
  if (selected.includes(value)) return selected.filter((item) => item !== value);
  return selected.length >= 2 ? selected : [...selected, value];
}

export function isCareerPreferencesDraftValid(
  priorityOrder: CareerPreferencePriority[],
  weeklyHours: string,
): boolean {
  if (priorityOrder.length !== 2 || new Set(priorityOrder).size !== 2) return false;
  if (!/^\d+$/.test(weeklyHours)) return false;
  const hours = Number(weeklyHours);
  return Number.isInteger(hours) && hours >= 1 && hours <= 60;
}

export function careerPreferencesDraftFromProfile(profile: Profile): CareerPreferencesDraft {
  return {
    priority_order: profile.preferences?.priority_order
      ? [...profile.preferences.priority_order]
      : [],
    weekly_hours: profile.preferences ? String(profile.preferences.weekly_hours) : "",
  };
}

export function profileCanEditCareerPreferences(profile: Profile | null): boolean {
  return profile?.status === "CONFIRMED";
}

export async function saveCareerPreferencesRequest(
  profileId: string,
  draft: CareerPreferencesDraft,
  apiUrl: string,
  request: ProfileRequester = fetch,
): Promise<CareerPreferences> {
  const response = await request(`${apiUrl}/api/v1/profiles/${profileId}/preferences`, {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      priority_order: draft.priority_order,
      weekly_hours: Number(draft.weekly_hours),
    }),
  });
  return readApiPayload<CareerPreferences>(response);
}
