import assert from "node:assert/strict";
import test from "node:test";

import {
  canNavigateNext,
  stepIndicatorState,
  stepLabel,
  stepNavigation,
} from "../app/workflow-navigation.ts";
import type { WorkflowSnapshot } from "../app/workflow-state.ts";

const profile = {
  profile_id: "profile-1",
  status: "CONFIRMED" as const,
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
  education: [],
  skills: [],
  experiences: [],
  certifications: [],
  preferences: {
    id: "preferences-1",
    profile_id: "profile-1",
    priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"],
    weekly_hours: 12,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
  },
};

const exploration = {
  id: "exploration-1",
  profile_id: "profile-1",
  role_profile_version: "v1",
  result: {
    role_profile_version: "v1",
    items: [{
      role_code: "AI_PRODUCT_MANAGER" as const,
      role_name: "AI Product Manager",
      level: "RECOMMENDED" as const,
      reasons: [],
      concerns: [],
      evidence_refs: [],
      preference_refs: ["CURRENT_FIT" as const],
    }],
  },
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
};

const targetRole = {
  id: "target-1",
  profile_id: "profile-1",
  role_code: "AI_PRODUCT_MANAGER" as const,
  role_name: "AI Product Manager",
  role_profile_version: "v1",
  role_exploration_id: "exploration-1",
  selected_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
};

const records = ["one", "two", "three"].map((id) => ({
  id,
  target_role_id: "target-1",
  raw_text: `JD ${id}`,
  source_url: null,
  created_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
}));

const completeSnapshot: WorkflowSnapshot = {
  profile,
  roleExploration: exploration,
  targetRole,
  jobDescriptions: records,
};

test("step navigation preserves the profile id and stops at JD", () => {
  assert.deepEqual(stepNavigation("profile-1", "profile"), {
    previous: null,
    next: "/workflow/profile-1/preferences",
    nextLabel: "确认并继续",
  });
  assert.deepEqual(stepNavigation("profile-1", "job-descriptions"), {
    previous: "/workflow/profile-1/target-role",
    next: null,
    nextLabel: null,
  });
});

test("step labels are explicit and readable", () => {
  assert.equal(stepLabel("role-exploration"), "Role Exploration");
  assert.equal(stepLabel("job-descriptions"), "Job Descriptions");
});

test("next navigation requires the persisted completion for the current step", () => {
  assert.equal(canNavigateNext({ ...completeSnapshot, profile: { ...profile, status: "DRAFT", preferences: null } }, "profile"), false);
  assert.equal(canNavigateNext(completeSnapshot, "profile"), true);
  assert.equal(canNavigateNext({ ...completeSnapshot, roleExploration: null, targetRole: null, jobDescriptions: [] }, "role-exploration"), false);
  assert.equal(canNavigateNext(completeSnapshot, "target-role"), true);
  assert.equal(canNavigateNext(completeSnapshot, "job-descriptions"), false);
});

test("indicator marks the current step separately from completed server steps", () => {
  const states = stepIndicatorState(completeSnapshot, "target-role");
  assert.deepEqual(states.map((state) => ({ step: state.step, complete: state.complete, current: state.current })), [
    { step: "profile", complete: true, current: false },
    { step: "preferences", complete: true, current: false },
    { step: "role-exploration", complete: true, current: false },
    { step: "target-role", complete: false, current: true },
    { step: "job-descriptions", complete: true, current: false },
  ]);
});
