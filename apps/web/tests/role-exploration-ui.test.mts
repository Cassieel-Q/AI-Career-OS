import assert from "node:assert/strict";
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
