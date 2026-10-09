import assert from "node:assert/strict";
import test from "node:test";

import { groupSkillNames } from "../app/skill-groups.ts";

test("groups extracted skill names without dropping or repeating facts", () => {
  const names = ["需求分析", "PRD 撰写", "LLM", "Prompt Engineering", "Codex", "Python", "六级（504）", "English"];
  const groups = groupSkillNames(names);
  assert.deepEqual(groups.map((group) => group.label), ["产品能力", "AI 产品能力", "技术与工具", "语言能力"]);
  assert.deepEqual(groups.flatMap((group) => group.items), names);
  assert.equal(groups.find((group) => group.label === "语言能力")?.items[0], "六级（504）");
});

test("AI terms take precedence when one skill also mentions product work", () => {
  assert.equal(groupSkillNames(["LLM 需求分析"])[0].label, "AI 产品能力");
});
