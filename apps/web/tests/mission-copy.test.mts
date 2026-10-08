import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";

import { MISSION_STAGE_LABELS } from "../app/mission-copy.ts";
import { targetResumeBulletStatusLabel } from "../app/mission-state.ts";

test("shared product stages and bullet statuses use approved labels", () => {
  assert.deepEqual(MISSION_STAGE_LABELS, ["岗位", "简历", "模拟面试", "面试记录"]);
  assert.equal(targetResumeBulletStatusLabel("REJECTED"), "未采用");
});

test("active pages have no discarded brochure copy", () => {
  for (const file of ["mission-create.tsx", "missions-home.tsx", "mission-page.tsx", "mission-state.ts", "profile-step.tsx", "proof-route.tsx", "proof-steps.tsx", "proof-shell.tsx", "proof-state.ts"]) {
    const source = readFileSync(new URL(`../app/${file}`, import.meta.url), "utf8");
    assert.doesNotMatch(source, /你想|只需要|AI 会|让 AI|面试拷问|准备链|主张核对|证明行动|可提交证明/, file);
  }
});
