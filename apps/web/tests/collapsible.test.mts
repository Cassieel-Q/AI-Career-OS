import assert from "node:assert/strict";
import { test } from "node:test";
import { initialSectionState, isSectionOpen, toggleSectionState } from "../app/collapsible.ts";

const KEYS = ["education", "skills", "experiences", "certifications"];

test("profile sections default to expanded", () => {
  const state = initialSectionState(KEYS);
  assert.deepEqual(state, { education: true, skills: true, experiences: true, certifications: true });
  assert.equal(isSectionOpen(state, "education"), true);
  assert.equal(isSectionOpen({}, "skills"), true); // 未记录也默认展开
});

test("clicking a section header collapses only that section", () => {
  const state = initialSectionState(KEYS);
  const collapsed = toggleSectionState(state, "experiences");
  assert.equal(isSectionOpen(collapsed, "experiences"), false);
  assert.equal(isSectionOpen(collapsed, "education"), true);
  assert.equal(isSectionOpen(state, "experiences"), true); // 纯函数不修改原对象
});

test("toggling twice restores the expanded state", () => {
  const state = initialSectionState(KEYS);
  const restored = toggleSectionState(toggleSectionState(state, "skills"), "skills");
  assert.equal(isSectionOpen(restored, "skills"), true);
});
