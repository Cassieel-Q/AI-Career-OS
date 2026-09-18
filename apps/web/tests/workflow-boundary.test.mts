import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { join } from "node:path";
import test from "node:test";

const routeRoot = join(import.meta.dirname, "..", "app", "workflow", "[profileId]");
const routeSteps = ["profile", "preferences", "role-exploration", "target-role", "job-descriptions"];

test("dynamic workflow pages keep render functions inside a client boundary", () => {
  const workflowPage = readFileSync(join(import.meta.dirname, "..", "app", "workflow-page.tsx"), "utf8");
  assert.match(workflowPage, /["']use client["']/);
  assert.match(workflowPage, /renderStep=/);

  for (const step of routeSteps) {
    const source = readFileSync(join(routeRoot, step, "page.tsx"), "utf8");
    assert.match(source, /<WorkflowPage\b/);
    assert.doesNotMatch(source, /renderStep=/);
  }
});
