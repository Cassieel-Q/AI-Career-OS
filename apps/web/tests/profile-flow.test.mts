import assert from "node:assert/strict";
import test from "node:test";

import {
  getProfileIdFromSearch,
  confirmProfileRequest,
  createEmptyEducation,
  profileHref,
  normalizeProfile,
  readApiPayload,
  saveProfileRequest,
  toUpdatePayload,
  validateProfileForSave,
} from "../app/profile-flow.ts";
import type { Profile, ProfileRequester } from "../app/profile-flow.ts";
import {
  CAREER_PREFERENCE_OPTIONS,
  careerPreferencesDraftFromProfile,
  isCareerPreferencesDraftValid,
  profileCanEditCareerPreferences,
  saveCareerPreferencesRequest,
  toggleCareerPreference,
} from "../app/career-preferences.ts";
import {
  ROLE_EXPLORATION_LEVEL_LABELS,
  ROLE_EXPLORATION_DISCLAIMER,
  profileCanExploreRoles,
  getRoleExplorationRequest,
  createRoleExplorationRequest,
  roleExplorationInputKey,
  roleExplorationInputMatches,
  roleExplorationViewData,
} from "../app/role-exploration.ts";
import type { RoleExplorationRead } from "../app/role-exploration.ts";
import {
  TARGET_ROLE_CODES,
  getTargetRoleRequest,
  selectTargetRoleRequest,
  targetRoleViewData,
} from "../app/target-role.ts";
import type { TargetRoleRead } from "../app/target-role.ts";

const profile: Profile = {
  profile_id: "profile-1",
  status: "DRAFT",
  created_at: "2026-09-04T00:00:00Z",
  updated_at: "2026-09-04T00:00:00Z",
  education: [
    {
      id: "education-1",
      institution: "Example University",
      degree: "MSc",
      field_of_study: null,
      dates: null,
      relevant_courses: [],
      evidence_text: "Example University MSc",
      source_type: "AI_EXTRACTED",
    },
  ],
  skills: [
    {
      id: "skill-1",
      name: "Python",
      proficiency: "PROJECT_READY",
      evidence_text: "Python",
      source_type: "AI_EXTRACTED",
    },
    {
      name: "SQL",
      proficiency: null,
      evidence_text: null,
      source_type: "USER_ENTERED",
    },
  ],
  experiences: [],
  certifications: [],
};

test("PUT payload contains only backend-editable fields", () => {
  assert.deepEqual(toUpdatePayload(profile), {
    education: [
      {
        id: "education-1",
        institution: "Example University",
        degree: "MSc",
        field_of_study: null,
        dates: null,
        relevant_courses: [],
      },
    ],
    skills: [
      { id: "skill-1", name: "Python", proficiency: "PROJECT_READY" },
      { name: "SQL", proficiency: null },
    ],
    experiences: [],
    certifications: [],
  });
});

test("save validation reports the exact required field causing the old 422", () => {
  const invalidProfile = {
    ...profile,
    skills: [{ ...profile.skills[1], name: "" }],
  } as Profile;

  assert.equal(validateProfileForSave(invalidProfile), "Skills item 1: Skill is required.");
});

test("backend validation details become useful client errors", async () => {
  const response = new Response(
    JSON.stringify({
      detail: [{ loc: ["body", "skills", 0, "name"], msg: "Input should be a valid string" }],
    }),
    { status: 422, headers: { "Content-Type": "application/json" } },
  );

  await assert.rejects(readApiPayload(response), /skills\.0\.name: Input should be a valid string/);
});

test("profile identity is read from and written to the URL", () => {
  assert.equal(getProfileIdFromSearch("?profile_id=profile-1"), "profile-1");
  assert.equal(profileHref("/career?tab=profile#top", "profile-1"), "/career?tab=profile&profile_id=profile-1#top");
});

test("legacy education without courses normalizes to an empty list", () => {
  const legacyProfile = {
    ...profile,
    education: [{ ...profile.education[0], relevant_courses: undefined }],
  } as unknown as Profile;

  const normalized = normalizeProfile(legacyProfile);

  assert.deepEqual(normalized.education[0].relevant_courses, []);
  assert.deepEqual(toUpdatePayload(legacyProfile).education[0].relevant_courses, []);
});

test("null education courses normalize to an empty list", () => {
  const legacyProfile = {
    ...profile,
    education: [{ ...profile.education[0], relevant_courses: null }],
  } as unknown as Profile;

  assert.deepEqual(normalizeProfile(legacyProfile).education[0].relevant_courses, []);
});

test("confirmed legacy profiles remain render-safe", () => {
  const legacyProfile = {
    ...profile,
    status: "CONFIRMED" as const,
    education: [{ ...profile.education[0], relevant_courses: null }],
  } as unknown as Profile;

  assert.deepEqual(normalizeProfile(legacyProfile).education[0].relevant_courses, []);
  assert.equal(normalizeProfile(legacyProfile).status, "CONFIRMED");
});

test("new education items initialize relevant courses", () => {
  assert.deepEqual(createEmptyEducation().relevant_courses, []);
});

test("save response normalizes legacy courses before returning to state", async () => {
  const legacyProfile = {
    ...profile,
    education: [{ ...profile.education[0], relevant_courses: null }],
  } as unknown as Profile;
  const request: ProfileRequester = async () => jsonResponse(legacyProfile);

  const saved = await saveProfileRequest(profile, "http://api.test", request);

  assert.deepEqual(saved.education[0].relevant_courses, []);
});

test("confirm response normalizes legacy courses before rendering", async () => {
  const legacyProfile = {
    ...profile,
    status: "CONFIRMED" as const,
    education: [{ ...profile.education[0], relevant_courses: null }],
  } as unknown as Profile;
  const request: ProfileRequester = async () => jsonResponse(legacyProfile);

  const confirmed = await confirmProfileRequest(profile, false, "http://api.test", request);

  assert.deepEqual(confirmed.education[0].relevant_courses, []);
  assert.equal(confirmed.status, "CONFIRMED");
});

test("dirty confirmation saves the latest draft before confirming it", async () => {
  const latestDraft = {
    ...profile,
    skills: [{ ...profile.skills[0], name: "Latest Python" }],
  } as Profile;
  const confirmedProfile = { ...latestDraft, status: "CONFIRMED" as const };
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const request: ProfileRequester = async (input, init) => {
    calls.push({ input, init });
    return calls.length === 1
      ? jsonResponse(latestDraft)
      : jsonResponse(confirmedProfile);
  };

  const result = await confirmProfileRequest(latestDraft, true, "http://api.test", request);

  assert.deepEqual(calls.map(({ init }) => init?.method), ["PUT", "POST"]);
  assert.equal(JSON.parse(String(calls[0].init?.body)).skills[0].name, "Latest Python");
  assert.equal(result.status, "CONFIRMED");
  assert.equal(result.skills[0].name, "Latest Python");
});

test("failed save-before-confirm blocks confirmation", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const request: ProfileRequester = async (input, init) => {
    calls.push({ input, init });
    return jsonResponse(
      { detail: [{ loc: ["body", "skills", 0, "name"], msg: "Input should be a valid string" }] },
      422,
    );
  };

  await assert.rejects(confirmProfileRequest(profile, true, "http://api.test", request), /skills\.0\.name/);
  assert.deepEqual(calls.map(({ init }) => init?.method), ["PUT"]);
});

test("clean confirmation does not issue an unnecessary PUT", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const request: ProfileRequester = async (input, init) => {
    calls.push({ input, init });
    return jsonResponse({ ...profile, status: "CONFIRMED" as const });
  };

  const result = await confirmProfileRequest(profile, false, "http://api.test", request);

  assert.deepEqual(calls.map(({ init }) => init?.method), ["POST"]);
  assert.equal(result.status, "CONFIRMED");
});

test("the five frozen priority options have Chinese labels", () => {
  assert.equal(CAREER_PREFERENCE_OPTIONS.length, 5);
  assert.deepEqual(CAREER_PREFERENCE_OPTIONS.map((option) => option.label), [
    "薪资优先",
    "少写代码",
    "尽快就业",
    "当前匹配度",
    "长期成长",
  ]);
});

test("selection order appends, caps at two, and removes the clicked item", () => {
  const first = toggleCareerPreference([], "FAST_EMPLOYMENT");
  const second = toggleCareerPreference(first, "CURRENT_FIT");
  assert.deepEqual(toggleCareerPreference(second, "COMPENSATION"), second);
  assert.deepEqual(toggleCareerPreference(second, "FAST_EMPLOYMENT"), ["CURRENT_FIT"]);
});

test("draft validity requires two priorities and integer hours from one to sixty", () => {
  assert.equal(isCareerPreferencesDraftValid([], "20"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT"], "20"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "0"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "20.5"), false);
  assert.equal(isCareerPreferencesDraftValid(["FAST_EMPLOYMENT", "CURRENT_FIT"], "20"), true);
});

test("career preferences edit only becomes available after confirmation", () => {
  assert.equal(profileCanEditCareerPreferences(profile), false);
  assert.equal(profileCanEditCareerPreferences({ ...profile, status: "CONFIRMED" }), true);
  assert.equal(profileCanEditCareerPreferences(null), false);
});

test("profile normalization keeps missing or null preferences compatible", () => {
  const missing = normalizeProfile({ ...profile } as Profile);
  const explicitlyNull = normalizeProfile({ ...profile, preferences: null });

  assert.equal(missing.preferences, null);
  assert.equal(explicitlyNull.preferences, null);
  assert.deepEqual(careerPreferencesDraftFromProfile(missing), { priority_order: [], weekly_hours: "" });
  assert.deepEqual(careerPreferencesDraftFromProfile(explicitlyNull), { priority_order: [], weekly_hours: "" });
});

test("stored preferences rehydrate into an editable draft", () => {
  const stored = {
    id: "preference-1",
    profile_id: profile.profile_id,
    priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"],
    weekly_hours: 12,
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T00:00:00Z",
  };

  assert.deepEqual(
    careerPreferencesDraftFromProfile({ ...profile, status: "CONFIRMED", preferences: stored }),
    { priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"], weekly_hours: "12" },
  );
});

test("career preferences PUT sends the exact endpoint and JSON payload", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const response = {
    id: "preference-1",
    profile_id: profile.profile_id,
    priority_order: ["FAST_EMPLOYMENT", "CURRENT_FIT"],
    weekly_hours: 20,
    created_at: "2026-09-04T00:00:00Z",
    updated_at: "2026-09-04T00:00:00Z",
  };
  const request: ProfileRequester = async (input, init) => {
    calls.push({ input, init });
    return jsonResponse(response);
  };

  const saved = await saveCareerPreferencesRequest(
    profile.profile_id,
    { priority_order: ["FAST_EMPLOYMENT", "CURRENT_FIT"], weekly_hours: "20" },
    "http://api.test",
    request,
  );

  assert.equal(calls[0].input, "http://api.test/api/v1/profiles/profile-1/preferences");
  assert.equal(calls[0].init?.method, "PUT");
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), {
    priority_order: ["FAST_EMPLOYMENT", "CURRENT_FIT"],
    weekly_hours: 20,
  });
  assert.deepEqual(saved, response);
});

test("career preferences PUT reports safe API errors", async () => {
  const request: ProfileRequester = async () => jsonResponse({ detail: [{ msg: "invalid preference" }] }, 422);

  await assert.rejects(
    saveCareerPreferencesRequest(
      profile.profile_id,
      { priority_order: ["FAST_EMPLOYMENT", "CURRENT_FIT"], weekly_hours: "20" },
      "http://api.test",
      request,
    ),
    /invalid preference/,
  );
});

test("career preference save eligibility requires a confirmed profile, two priorities, and valid hours", () => {
  const draft = { priority_order: ["FAST_EMPLOYMENT", "CURRENT_FIT"] as const, weekly_hours: "20" };
  assert.equal(
    profileCanEditCareerPreferences(profile) && isCareerPreferencesDraftValid([...draft.priority_order], draft.weekly_hours),
    false,
  );
  assert.equal(
    profileCanEditCareerPreferences({ ...profile, status: "CONFIRMED" }) &&
      isCareerPreferencesDraftValid([...draft.priority_order], draft.weekly_hours),
    true,
  );
  assert.equal(
    profileCanEditCareerPreferences({ ...profile, status: "CONFIRMED" }) &&
      isCareerPreferencesDraftValid(["FAST_EMPLOYMENT"], draft.weekly_hours),
    false,
  );
});

test("removing the first selected preference promotes the remaining item to priority one", () => {
  const selected = toggleCareerPreference(toggleCareerPreference([], "COMPENSATION"), "LONG_TERM_GROWTH");
  assert.deepEqual(toggleCareerPreference(selected, "COMPENSATION"), ["LONG_TERM_GROWTH"]);
});

test("role exploration readiness requires confirmed profile and persisted valid preferences", () => {
  const confirmed = {
    ...profile,
    status: "CONFIRMED" as const,
    preferences: {
      id: "pref-1", profile_id: profile.profile_id,
      priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"],
      weekly_hours: 12, created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z",
    },
  };
  assert.equal(profileCanExploreRoles(profile), false);
  assert.equal(profileCanExploreRoles({ ...confirmed, preferences: null }), false);
  assert.equal(profileCanExploreRoles(confirmed), true);
});

test("role exploration requests use exact GET and POST contracts", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const snapshot = { id: "explore-1", profile_id: "profile-1", role_profile_version: "v1", result: { role_profile_version: "v1", items: [] }, created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z" } as unknown as RoleExplorationRead;
  const request: ProfileRequester = async (input, init) => { calls.push({ input, init }); return jsonResponse(snapshot); };
  await getRoleExplorationRequest("profile-1", "http://api.test", request);
  await createRoleExplorationRequest("profile-1", "http://api.test", request);
  assert.equal(calls[0].input, "http://api.test/api/v1/profiles/profile-1/role-exploration");
  assert.equal(calls[0].init?.method, "GET");
  assert.equal(calls[1].input, "http://api.test/api/v1/role-explorations");
  assert.equal(calls[1].init?.method, "POST");
  assert.deepEqual(JSON.parse(String(calls[1].init?.body)), { profile_id: "profile-1" });
});

test("not-generated exploration GET returns null while other errors remain safe", async () => {
  const notGenerated: ProfileRequester = async () => jsonResponse({ detail: "Role exploration has not been generated" }, 404);
  assert.equal(await getRoleExplorationRequest("profile-1", "http://api.test", notGenerated), null);
  const missingProfile: ProfileRequester = async () => jsonResponse({ detail: "Profile not found" }, 404);
  await assert.rejects(getRoleExplorationRequest("missing-profile", "http://api.test", missingProfile), /Profile not found/);
  const failed: ProfileRequester = async () => jsonResponse({ detail: [{ msg: "backend unavailable" }] }, 503);
  await assert.rejects(getRoleExplorationRequest("profile-1", "http://api.test", failed), /backend unavailable/);
});

test("role exploration input identity accepts unchanged input and rejects changed profile or preferences", () => {
  const confirmed = {
    ...profile,
    status: "CONFIRMED" as const,
    preferences: {
      id: "pref-1",
      profile_id: profile.profile_id,
      priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"],
      weekly_hours: 12,
      created_at: "2026-09-04T00:00:00Z",
      updated_at: "2026-09-04T00:00:00Z",
    },
  };
  const unchangedDraft = {
    priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"],
    weekly_hours: "12",
  };
  const captured = roleExplorationInputKey(confirmed, unchangedDraft);

  assert.equal(roleExplorationInputMatches(captured, confirmed, unchangedDraft), true);
  assert.equal(
    roleExplorationInputMatches(captured, confirmed, { ...unchangedDraft, priority_order: ["LONG_TERM_GROWTH", "CURRENT_FIT"] }),
    false,
  );
  assert.equal(roleExplorationInputMatches(captured, confirmed, { ...unchangedDraft, weekly_hours: "20" }), false);
  assert.equal(roleExplorationInputMatches(captured, { ...confirmed, profile_id: "profile-2" }, unchangedDraft), false);
  assert.equal(
    roleExplorationInputMatches(
      captured,
      { ...confirmed, preferences: { ...confirmed.preferences, weekly_hours: 20 } },
      unchangedDraft,
    ),
    false,
  );
});

test("role exploration labels, six-card data, references, and disclaimer are display-safe", () => {
  assert.deepEqual(ROLE_EXPLORATION_LEVEL_LABELS, { RECOMMENDED: "推荐", POSSIBLE: "可探索", LOW_PRIORITY: "暂不优先" });
  const snapshot = {
    id: "explore-1", profile_id: "profile-1", role_profile_version: "v1",
    result: { role_profile_version: "v1", items: Array.from({ length: 6 }, (_, index) => ({
      role_code: `ROLE_${index}`, role_name: `Role ${index}`, level: "POSSIBLE", reasons: ["reason"], concerns: ["concern"], evidence_refs: [`evidence-${index}`], preference_refs: ["CURRENT_FIT"],
    })) }, created_at: "2026-09-04T00:00:00Z", updated_at: "2026-09-04T00:00:00Z",
  } as unknown as RoleExplorationRead;
  const cards = roleExplorationViewData(snapshot);
  assert.equal(cards.length, 6);
  assert.deepEqual(cards[0].evidence_refs, ["evidence-0"]);
  assert.deepEqual(cards[0].preference_refs, ["CURRENT_FIT"]);
  assert.match(ROLE_EXPLORATION_DISCLAIMER, /confirmed Profile/);
  assert.match(ROLE_EXPLORATION_DISCLAIMER, /no real JD/i);
});

test("target role GET treats only an unselected target as the empty state", async () => {
  const selected: TargetRoleRead = {
    id: "target-1",
    profile_id: "profile-1",
    role_code: "AI_PRODUCT_MANAGER",
    role_name: "AI Product Manager",
    role_profile_version: "v1",
    role_exploration_id: "explore-1",
    selected_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  };
  const request: ProfileRequester = async () => jsonResponse(selected);
  assert.deepEqual(await getTargetRoleRequest("profile-1", "http://api.test", request), selected);

  const emptyRequest: ProfileRequester = async () => jsonResponse({ detail: "Target role has not been selected" }, 404);
  assert.equal(await getTargetRoleRequest("profile-1", "http://api.test", emptyRequest), null);

  const missingProfile: ProfileRequester = async () => jsonResponse({ detail: "Profile not found" }, 404);
  await assert.rejects(getTargetRoleRequest("profile-1", "http://api.test", missingProfile), /Profile not found/);
});

test("target role PUT sends only the canonical role code for every supported role", async () => {
  const calls: Array<{ input: RequestInfo | URL; init?: RequestInit }> = [];
  const selected = {
    id: "target-1",
    profile_id: "profile-1",
    role_code: "AI_APPLICATION_ENGINEER",
    role_name: "AI Application Engineer",
    role_profile_version: "v1",
    role_exploration_id: "explore-1",
    selected_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  } satisfies TargetRoleRead;
  const request: ProfileRequester = async (input, init) => {
    calls.push({ input, init });
    return jsonResponse(selected);
  };

  for (const roleCode of TARGET_ROLE_CODES) {
    await selectTargetRoleRequest("profile-1", roleCode, "http://api.test", request);
  }

  assert.equal(calls.length, TARGET_ROLE_CODES.length);
  assert.equal(calls[0].input, "http://api.test/api/v1/profiles/profile-1/target-role");
  assert.equal(calls[0].init?.method, "PUT");
  assert.deepEqual(JSON.parse(String(calls[0].init?.body)), { role_code: TARGET_ROLE_CODES[0] });
  assert.equal(Object.keys(JSON.parse(String(calls[0].init?.body))).length, 1);
});

test("target role view data preserves selected state and supports all six roles", () => {
  assert.equal(TARGET_ROLE_CODES.length, 6);
  const selected: TargetRoleRead = {
    id: "target-1",
    profile_id: "profile-1",
    role_code: "AI_DATA_ANALYST",
    role_name: "AI Data Analyst",
    role_profile_version: "v1",
    role_exploration_id: "explore-1",
    selected_at: "2026-09-14T00:00:00Z",
    updated_at: "2026-09-14T00:00:00Z",
  };
  assert.deepEqual(targetRoleViewData(selected), {
    role_code: "AI_DATA_ANALYST",
    role_name: "AI Data Analyst",
    role_profile_version: "v1",
    role_exploration_id: "explore-1",
  });
  assert.equal(targetRoleViewData(null), null);
});

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
