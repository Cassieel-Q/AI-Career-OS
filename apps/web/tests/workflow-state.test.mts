import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import {
  canEnterStep,
  latestValidStep,
  readWorkflowSnapshot,
  workflowCompletion,
  workflowHref,
} from "../app/workflow-state.ts";
import type { WorkflowSnapshot } from "../app/workflow-state.ts";
import type { Profile } from "../app/profile-flow.ts";
import type { RoleExplorationRead } from "../app/role-exploration.ts";
import type { TargetRoleRead } from "../app/target-role.ts";
import type { JobDescriptionRead } from "../app/job-descriptions.ts";

const confirmedProfile: Profile = {
  profile_id: "profile-1",
  status: "CONFIRMED",
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
  education: [],
  skills: [],
  experiences: [],
  certifications: [],
  preferences: {
    id: "preferences-1",
    profile_id: "profile-1",
    priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"],
    weekly_hours: 12,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
  },
};

const exploration: RoleExplorationRead = {
  id: "exploration-1",
  profile_id: "profile-1",
  role_profile_version: "v1",
  result: { role_profile_version: "v1", items: [] },
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
};

const targetRole: TargetRoleRead = {
  id: "target-1",
  profile_id: "profile-1",
  role_code: "AI_PRODUCT_MANAGER",
  role_name: "AI Product Manager",
  role_profile_version: "v1",
  role_exploration_id: exploration.id,
  selected_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
};

function jd(id: string, targetRoleId = targetRole.id): JobDescriptionRead {
  return {
    id,
    target_role_id: targetRoleId,
    raw_text: `JD ${id}`,
    source_url: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
  };
}

function snapshot(overrides: Partial<WorkflowSnapshot> = {}): WorkflowSnapshot {
  return {
    profile: confirmedProfile,
    roleExploration: exploration,
    targetRole,
    jobDescriptions: [jd("jd-1"), jd("jd-2"), jd("jd-3")],
    ...overrides,
  };
}

test("draft profiles stop at Profile and cannot enter Preferences", () => {
  const result = snapshot({
    profile: { ...confirmedProfile, status: "DRAFT", preferences: null },
    roleExploration: null,
    targetRole: null,
    jobDescriptions: [],
  });

  assert.equal(latestValidStep(result), "profile");
  assert.equal(canEnterStep(result, "profile"), true);
  assert.equal(canEnterStep(result, "preferences"), false);
  assert.equal(canEnterStep(result, "role-exploration"), false);
});

test("preference state without downstream server records does not complete downstream steps", () => {
  const result = snapshot({ roleExploration: null, targetRole: null, jobDescriptions: [] });

  assert.deepEqual(workflowCompletion(result), {
    profile: true,
    preferences: true,
    "role-exploration": false,
    "target-role": false,
    "job-descriptions": false,
  });
  assert.equal(latestValidStep(result), "role-exploration");
  assert.equal(canEnterStep(result, "role-exploration"), true);
  assert.equal(canEnterStep(result, "target-role"), false);
});

test("stale target and JD records bound to another exploration are ignored", () => {
  const result = snapshot({
    targetRole: { ...targetRole, role_exploration_id: "old-exploration" },
    jobDescriptions: [jd("old-jd")],
  });

  assert.equal(workflowCompletion(result)["target-role"], false);
  assert.equal(workflowCompletion(result)["job-descriptions"], false);
  assert.equal(latestValidStep(result), "target-role");
  assert.equal(canEnterStep(result, "job-descriptions"), false);
});

test("job-description step completes only at the three-record readiness threshold", () => {
  assert.equal(workflowCompletion(snapshot({ jobDescriptions: [jd("one"), jd("two")] }))["job-descriptions"], false);
  assert.equal(workflowCompletion(snapshot({ jobDescriptions: [jd("one"), jd("two"), jd("three")] }))["job-descriptions"], true);
});

test("workflowHref carries profile identity in every dynamic route", () => {
  assert.equal(workflowHref("profile-1", "job-descriptions"), "/workflow/profile-1/job-descriptions");
});

test("server snapshot rehydrates the persisted profile, exploration, target, and JD collection", async () => {
  const calls: string[] = [];
  const request = async (input: RequestInfo | URL) => {
    const url = String(input);
    calls.push(url);
    if (url.endsWith("/api/v1/profiles/profile-1")) return jsonResponse(confirmedProfile);
    if (url.endsWith("/api/v1/profiles/profile-1/role-exploration")) return jsonResponse(exploration);
    if (url.endsWith("/api/v1/profiles/profile-1/target-role")) return jsonResponse(targetRole);
    if (url.endsWith(`/api/v1/target-roles/${targetRole.id}/job-descriptions`)) return jsonResponse([jd("jd-1")]);
    throw new Error(`Unexpected request: ${url}`);
  };

  const result = await readWorkflowSnapshot("profile-1", "http://api.test", request);

  assert.equal(result.profile?.profile_id, "profile-1");
  assert.equal(result.roleExploration?.id, exploration.id);
  assert.equal(result.targetRole?.id, targetRole.id);
  assert.deepEqual(result.jobDescriptions.map((record) => record.id), ["jd-1"]);
  assert.equal(calls.length, 4);
});

test("home page delegates to the canonical workflow start route", async () => {
  const source = await readFile(new URL("../app/page.tsx", import.meta.url), "utf8");
  assert.match(source, /redirect\(["']\/workflow\/start["']\)/);
  assert.doesNotMatch(source, /<section className="career-preferences"/);
});

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}
