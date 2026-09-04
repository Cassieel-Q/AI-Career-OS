import assert from "node:assert/strict";
import test from "node:test";

import {
  getProfileIdFromSearch,
  confirmProfileRequest,
  profileHref,
  readApiPayload,
  toUpdatePayload,
  validateProfileForSave,
} from "../app/profile-flow.ts";
import type { Profile, ProfileRequester } from "../app/profile-flow.ts";

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

function jsonResponse(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
