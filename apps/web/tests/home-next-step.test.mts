import test from "node:test";
import assert from "node:assert/strict";

import { AFTER_APPLY_LINKS, nextStepFor } from "../app/home-next-step.ts";

test("first-time user is asked to import a resume", () => {
  const step = nextStepFor({ hasProfile: false, missionCount: 0, resumeCount: 0, appliedCount: 0 });
  assert.equal(step.key, "IMPORT_RESUME");
  assert.equal(step.href, "/resumes");
});

test("profile without a job is asked to add a job", () => {
  const step = nextStepFor({ hasProfile: true, missionCount: 0, resumeCount: 0, appliedCount: 0 });
  assert.equal(step.key, "ADD_JOB");
  assert.equal(step.href, "/missions/new");
});

test("job without a tailored resume goes to review and export", () => {
  const step = nextStepFor({
    hasProfile: true,
    missionCount: 2,
    resumeCount: 0,
    appliedCount: 0,
    latestMissionId: "m-1",
  });
  assert.equal(step.key, "REVIEW_EXPORT");
  assert.equal(step.href, "/missions/m-1/resume/studio");
});

test("after applying, the main action switches to the applied version", () => {
  const step = nextStepFor({ hasProfile: true, missionCount: 2, resumeCount: 3, appliedCount: 1 });
  assert.equal(step.key, "AFTER_APPLY");
  assert.equal(step.href, "/tracker");
  assert.ok(step.desc.includes("投递"));
});

test("secondary links stay available after apply", () => {
  const labels = AFTER_APPLY_LINKS.map((item) => item.label);
  assert.deepEqual(labels, ["面试准备", "跟进状态", "历史投递版"]);
});

test("mission id is url-encoded in the studio link", () => {
  const step = nextStepFor({
    hasProfile: true,
    missionCount: 1,
    resumeCount: 0,
    appliedCount: 0,
    latestMissionId: "a b/c",
  });
  assert.equal(step.href, "/missions/a%20b%2Fc/resume/studio");
});
