import assert from "node:assert/strict";
import { readFile } from "node:fs/promises";
import test from "node:test";

import { roleExplorationGenerationView } from "../app/role-exploration.ts";

test("role exploration generation exposes visible loading and disables repeat clicks", () => {
  assert.deepEqual(roleExplorationGenerationView(true, ""), {
    buttonLabel: "正在生成…",
    disabled: true,
    showLoading: true,
    showRetry: false,
    error: null,
  });
});

test("role exploration provider failure exposes a recoverable retry state", () => {
  assert.deepEqual(roleExplorationGenerationView(false, "岗位探索暂时生成失败，请重试。"), {
    buttonLabel: "重试岗位探索",
    disabled: false,
    showLoading: false,
    showRetry: true,
    error: "岗位探索暂时生成失败，请重试。",
  });
});

test("Role Selection combines AI exploration with explicit user target choice", async () => {
  const source = await readFile(new URL("../app/role-exploration-step.tsx", import.meta.url), "utf8");
  assert.match(source, /selectTargetRoleRequest/);
  assert.match(source, /roleExplorationViewData\(exploration\)/);
  assert.match(source, /选择为目标岗位/);
  assert.match(source, /由你选择/);
  assert.match(source, /任何方向都可以选择/);
});
