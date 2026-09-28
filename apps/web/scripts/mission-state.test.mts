import test from "node:test";
import assert from "node:assert/strict";

import {
  canAccessTab,
  countHighRiskFindings,
  deriveResumeSubstep,
  deriveTab,
  humanizeMissionError,
  missionStatusLabel,
  nextRoute,
  primaryCta,
  targetResumeConfirmed,
  workflowStateLabel,
} from "../app/mission-state.ts";
import { MISSION_TABS, missionTabLabel } from "../app/missions.ts";

test("mission tabs are the five user-facing stages in Chinese", () => {
  assert.deepEqual(MISSION_TABS, ["role", "resume", "proof", "interview", "outcome"]);
  assert.equal(missionTabLabel("role"), "岗位理解");
  assert.equal(missionTabLabel("resume"), "简历");
  assert.equal(missionTabLabel("proof"), "补强");
  assert.equal(missionTabLabel("interview"), "面试");
  assert.equal(missionTabLabel("outcome"), "结果");
});

test("state → tab / route / resume substep", () => {
  assert.equal(deriveTab("ROLE_UNDERSTOOD"), "role");
  assert.equal(deriveTab("EXPERIENCE_SELECTION_REQUIRED"), "resume");
  assert.equal(deriveTab("STRENGTHENING_REQUIRED"), "proof");
  assert.equal(deriveTab("INTERVIEW_PREP_READY"), "interview");
  assert.equal(deriveTab("OUTCOME"), "outcome");

  assert.equal(deriveResumeSubstep("RESUME_REQUIRED"), "source");
  assert.equal(deriveResumeSubstep("EXPERIENCE_SELECTION_REQUIRED"), "selection");
  assert.equal(deriveResumeSubstep("RESUME_STRATEGY_REQUIRED"), "strategy");
  assert.equal(deriveResumeSubstep("TARGET_RESUME_DRAFT"), "target");
  assert.equal(deriveResumeSubstep("STRESS_TEST_REQUIRED"), "stress");

  assert.equal(nextRoute("ROLE_UNDERSTOOD", "m1"), "/missions/m1/role");
  assert.equal(nextRoute("TARGET_RESUME_DRAFT", "m1"), "/missions/m1/resume");
  assert.equal(nextRoute("INTERVIEW_PREP_READY", "m1"), "/missions/m1/interview");
});

test("Primary CTAs match PRD labels", () => {
  assert.equal(primaryCta("ROLE_UNDERSTOOD"), "下一步：选择简历");
  assert.equal(primaryCta("RESUME_REQUIRED"), "用这份简历继续");
  assert.equal(primaryCta("EXPERIENCE_SELECTION_REQUIRED", { hasSelection: true }), "下一步：制定简历策略");
  assert.equal(primaryCta("RESUME_STRATEGY_REQUIRED", { hasStrategy: false }), "生成本岗位简历策略");
  assert.equal(primaryCta("RESUME_STRATEGY_REQUIRED", { hasStrategy: true }), "下一步：生成目标简历");
  assert.equal(primaryCta("TARGET_RESUME_DRAFT", { company: "百度", bulletsDecided: true }), "保存 百度 Resume v1");
  assert.equal(primaryCta("TARGET_RESUME_CONFIRMED"), "下一步：检查简历风险");
  assert.equal(primaryCta("STRESS_TEST_REQUIRED", { highRiskCount: 2 }), "先补最危险的一项");
  assert.equal(primaryCta("INTERVIEW_PREP_READY", { hasInterviewPack: true }), "开始模拟面试");
});

test("tab gating: stress alone does not unlock interview", () => {
  assert.equal(canAccessTab("ROLE_UNDERSTOOD", "role"), true);
  assert.equal(canAccessTab("ROLE_UNDERSTOOD", "resume"), true);
  assert.equal(canAccessTab("STRESS_TEST_REQUIRED", "interview"), false);
  assert.equal(canAccessTab("INTERVIEW_PREP_READY", "interview"), true);
  assert.equal(canAccessTab("STRENGTHENING_REQUIRED", "proof"), true);
});

test("provider errors are humanized for users", () => {
  assert.match(
    humanizeMissionError("Mission intelligence returned an unusable response; please retry", "company_intel"),
    /公司面试情报/,
  );
  assert.doesNotMatch(
    humanizeMissionError("Mission intelligence returned an unusable response", "company_intel"),
    /Mission intelligence|provider|schema/i,
  );
  assert.match(humanizeMissionError("schema_validation provider", "jd_analysis"), /岗位分析/);
  assert.match(humanizeMissionError("resume_source required"), /选择.*简历/);
});

test("helpers", () => {
  assert.equal(targetResumeConfirmed([{ status: "SUGGESTED" }]), false);
  assert.equal(targetResumeConfirmed([{ status: "ACCEPTED" }, { status: "EDITED" }]), true);
  assert.equal(countHighRiskFindings([{ risk_level: "HIGH" }, { risk_level: "MEDIUM" }]), 1);
  assert.equal(missionStatusLabel("RESUME_PREP"), "准备中");
  assert.equal(workflowStateLabel("ROLE_UNDERSTOOD"), "岗位已理解");
});
