import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const routeRoot = join(import.meta.dirname, "..", "app", "workflow", "[profileId]");
const routeSteps = [
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

/** Abandoned multi-step career-planning entry points seal to Mission home. */
const sealedToMissions = new Set(["profile"]);

test("dynamic workflow pages keep render functions inside a client boundary", () => {
  const workflowPage = readFileSync(join(import.meta.dirname, "..", "app", "workflow-page.tsx"), "utf8");
  assert.match(workflowPage, /["']use client["']/);
  assert.match(workflowPage, /renderStep=/);

  for (const step of routeSteps) {
    const source = readFileSync(join(routeRoot, step, "page.tsx"), "utf8");
    assert.match(source, /params.*Promise/);
    assert.doesNotMatch(source, /["']use client["']/);
    if (sealedToMissions.has(step)) {
      assert.match(source, /redirect\(\s*["']\/missions["']\s*\)/);
      assert.doesNotMatch(source, /<WorkflowPage\b/);
      continue;
    }
    assert.match(source, /<WorkflowPage\b/);
    assert.doesNotMatch(source, /renderStep=/);
  }

  const legacyTargetRoleSource = readFileSync(join(routeRoot, "target-role", "page.tsx"), "utf8");
  assert.match(legacyTargetRoleSource, /redirect\(/);
  assert.doesNotMatch(legacyTargetRoleSource, /<WorkflowPage\b/);
});
