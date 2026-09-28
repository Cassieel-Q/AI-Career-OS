import test from "node:test";
import assert from "node:assert/strict";

import { alignedExperienceWhy, isKnownExperienceId, missingExperienceLabel } from "../app/experience-utils.ts";

test("alignedExperienceWhy KEEP_AND_HIGHLIGHT fills empty why", () => {
  const why = alignedExperienceWhy("KEEP_AND_HIGHLIGHT", "", "核心项目");
  assert.match(why, /重点展示/);
  assert.match(why, /核心项目/);
});

test("alignedExperienceWhy KEEP fills empty why", () => {
  const why = alignedExperienceWhy("KEEP", null, "运营助理");
  assert.match(why, /建议保留/);
  assert.match(why, /运营助理/);
  assert.doesNotMatch(why, /暂不放入/);
});

test("alignedExperienceWhy DEEMPHASIZE rewrites keep-tone why", () => {
  const why = alignedExperienceWhy("DEEMPHASIZE", "建议保留并突出这段经历", "社团经历");
  assert.match(why, /弱化/);
  assert.match(why, /社团经历/);
});

test("alignedExperienceWhy OMIT rewrites keep-tone why", () => {
  const why = alignedExperienceWhy(
    "OMIT",
    "与百度·AI产品经理相关，建议保留并突出「班级学习委员」中可验证的成果与职责。",
    "班级学习委员",
  );
  assert.match(why, /暂不放入/);
  assert.doesNotMatch(why, /建议保留/);
});

test("alignedExperienceWhy keeps non-conflicting why text", () => {
  const keep = alignedExperienceWhy("KEEP", "与目标岗位能力匹配，建议保留这段经历。", "运营助理");
  assert.match(keep, /建议保留/);
  const omit = alignedExperienceWhy("OMIT", "与岗位关联较弱，建议暂不放入。", "兼职");
  assert.match(omit, /暂不放入|关联较弱/);
});

test("alignedExperienceWhy empty why uses default experience label", () => {
  const why = alignedExperienceWhy("KEEP", "   ");
  assert.match(why, /这段经历/);
});

test("alignedExperienceWhy missing experience label falls back", () => {
  const why = alignedExperienceWhy("KEEP_AND_HIGHLIGHT", "", "");
  assert.match(why, /这段经历/);
});

test("missingExperienceLabel has no UUID", () => {
  const label = missingExperienceLabel();
  assert.match(label, /未知经历/);
  assert.doesNotMatch(label, /[0-9a-f]{8}-[0-9a-f]{4}/i);
});

test("isKnownExperienceId validates against current profile ids", () => {
  const known = new Set(["exp-a", "exp-b"]);
  assert.equal(isKnownExperienceId("exp-a", known), true);
  assert.equal(isKnownExperienceId("exp-z", known), false);
  assert.equal(isKnownExperienceId(null, known), false);
  assert.equal(isKnownExperienceId("", known), false);
});
