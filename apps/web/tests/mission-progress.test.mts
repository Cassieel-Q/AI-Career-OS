import test from "node:test";
import assert from "node:assert/strict";

import { deriveMissionProgress } from "../app/mission-progress.ts";

const base = {
  missionId: "mission 1",
  workflowState: "ROLE_UNDERSTOOD",
  currentTab: "role" as const,
  resumeBound: false,
  targetConfirmed: false,
  sessionStatus: null,
};

test("fresh persisted mission exposes only the role and explains later locks", () => {
  const steps = deriveMissionProgress(base);
  assert.deepEqual(steps.map((step) => step.label), ["岗位", "简历", "模拟面试", "面试记录"]);
  assert.deepEqual(steps.map((step) => step.status), ["current", "available", "locked", "locked"]);
  assert.match(steps[2].reason ?? "", /确认.*简历/);
  assert.match(steps[3].reason ?? "", /完成.*模拟面试/);
});

test("completed server stages remain navigable after reload", () => {
  const input = { ...base, currentTab: "interview" as const, resumeBound: true, targetConfirmed: true, sessionStatus: "ACTIVE" as const };
  const first = deriveMissionProgress(input);
  const reloaded = deriveMissionProgress({ ...input });
  assert.deepEqual(reloaded, first);
  assert.deepEqual(first.map((step) => step.status), ["complete", "complete", "current", "locked"]);
  assert.equal(first[1].href, "/missions/mission%201/resume");
});

test("completed interview opens records while previous stages stay available", () => {
  const steps = deriveMissionProgress({ ...base, currentTab: "outcome", resumeBound: true, targetConfirmed: true, sessionStatus: "COMPLETED" });
  assert.deepEqual(steps.map((step) => step.status), ["complete", "complete", "complete", "current"]);
});

test("temporary client state cannot complete a stage", () => {
  const steps = deriveMissionProgress({ ...base, currentTab: "resume", resumeBound: true, targetConfirmed: false, sessionStatus: null });
  assert.equal(steps[1].status, "current");
  assert.equal(steps[2].status, "locked");
});
