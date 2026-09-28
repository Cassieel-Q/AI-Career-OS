import assert from "node:assert/strict";
import test from "node:test";

import { canEnterStep, latestValidStep, workflowCompletion } from "../app/workflow-state.ts";
import { stepNavigation, stepNumber } from "../app/workflow-navigation.ts";
import { gapSeverityLabel, priorityDecisionReason, priorityLaneLabel, priorityLevelLabel, priorityMarketSummary, priorityStateLabel } from "../app/priority-ui.ts";
import { roadmapErrorMessage, roadmapUiState, taskStatusLabel } from "../app/roadmap-ui.ts";
import { createRoadmapRequest } from "../app/roadmap.ts";
import type { WorkflowSnapshot } from "../app/workflow-state.ts";

const base = {
  profile: {
    profile_id: "profile-1", status: "CONFIRMED" as const, created_at: "2026-09-19", updated_at: "2026-09-19",
    education: [], skills: [], experiences: [], certifications: [],
    preferences: { id: "pref-1", profile_id: "profile-1", priority_order: ["CURRENT_FIT", "LONG_TERM_GROWTH"] as ["CURRENT_FIT", "LONG_TERM_GROWTH"], weekly_hours: 10, created_at: "2026-09-19", updated_at: "2026-09-19" },
  },
  roleExploration: { id: "explore-1", profile_id: "profile-1", role_profile_version: "v1", result: { role_profile_version: "v1", items: [{ role_code: "AI_PRODUCT_MANAGER" as const, role_name: "AI Product Manager", level: "RECOMMENDED" as const, reasons: ["reason"], concerns: [], evidence_refs: [], preference_refs: [] }] }, created_at: "2026-09-19", updated_at: "2026-09-19" },
  targetRole: { id: "target-1", profile_id: "profile-1", role_code: "AI_PRODUCT_MANAGER" as const, role_name: "AI Product Manager", role_profile_version: "v1", role_exploration_id: "explore-1", selected_at: "2026-09-19", updated_at: "2026-09-19" },
  jobDescriptions: ["one", "two", "three"].map((id) => ({ id, target_role_id: "target-1", raw_text: `JD ${id}`, source_url: null, created_at: "2026-09-19", updated_at: "2026-09-19" })),
  marketProfile: { id: "market-1", target_role_id: "target-1", sample_count: 3, sample_fingerprint: "f", status: "VALID" as const, generated_at: "2026-09-19", updated_at: "2026-09-19", requirements: [], capabilities: [] },
  gapAnalysis: { id: "gap-1", profile_id: "profile-1", market_profile_id: "market-1", profile_fingerprint: "p", status: "VALID" as const, generated_at: "2026-09-19", updated_at: "2026-09-19", gaps: [] },
  priorities: { gap_analysis_id: "gap-1", overridden: false, items: [{ gap_id: "gap-item", requirement_name: "Python", state: "MISSING", severity: "HIGH", proximity: "HIGH", feasibility: "MEDIUM", frequency_ratio: 1, system_rank: 1, user_rank: null, effective_rank: 1, lane: "NOW" as const, system_reason: "frequent" }] },
  roadmap: { id: "roadmap-1", profile_id: "profile-1", revision: 1, weekly_hours: 10, status: "VALID", progress_ratio: 0, weeks: [1, 2, 3, 4].map((week) => ({ id: `week-${week}`, week_number: week, objective: "objective", focus_gap_ids: [], measurable_outcome: "outcome", tasks: [] })) },
  dashboard: null,
} satisfies WorkflowSnapshot;

test("downstream workflow guards require valid derived records in order", () => {
  assert.equal(latestValidStep(base), "dashboard");
  assert.equal(canEnterStep(base, "market-profile"), true);
  assert.equal(canEnterStep({ ...base, gapAnalysis: null }, "priorities"), false);
  assert.equal(canEnterStep({ ...base, roadmap: null }, "progress"), false);
  assert.equal(workflowCompletion(base).dashboard, true);
});

test("downstream navigation preserves profile identity and ends at dashboard", () => {
  assert.equal(stepNavigation("profile-1", "job-descriptions").next, "/workflow/profile-1/market-profile");
  assert.equal(stepNavigation("profile-1", "progress").next, "/workflow/profile-1/dashboard");
  assert.equal(stepNavigation("profile-1", "dashboard").next, null);
  assert.equal(stepNumber("dashboard"), 10);
});

test("priority presentation localizes stage and gap state without debug enums", () => {
  const item = base.priorities.items[0];
  assert.equal(priorityLaneLabel("NOW"), "现在优先");
  assert.equal(priorityLaneLabel("NEXT"), "下一阶段");
  assert.equal(priorityLaneLabel("NOT_NOW"), "暂不优先");
  assert.equal(priorityStateLabel("MISSING"), "明显缺口");
  assert.equal(priorityStateLabel("PARTIAL"), "部分具备");
  assert.equal(priorityStateLabel("MATCHED"), "已匹配");
  assert.equal(priorityStateLabel("UNCERTAIN"), "证据不足");
  assert.equal(priorityStateLabel("UNEXPECTED"), "证据不足");
  assert.equal(gapSeverityLabel("HIGH"), "高影响");
  assert.equal(gapSeverityLabel("UNEXPECTED"), "影响待确认");
  assert.equal(priorityLevelLabel("HIGH"), "高");
  assert.equal(priorityLevelLabel("MEDIUM"), "中");
  assert.equal(priorityLevelLabel("LOW"), "低");
  assert.doesNotMatch(priorityDecisionReason(item), /state=|severity=|MISSING|HIGH/);
  assert.doesNotMatch(priorityMarketSummary(item), /state=|severity=|MISSING|HIGH/);
});

test("roadmap presentation has one mutually-exclusive state and localized errors", () => {
  assert.equal(roadmapUiState(null, false, ""), "READY");
  assert.equal(roadmapUiState(null, true, ""), "GENERATING");
  assert.equal(roadmapUiState(null, false, "生成失败"), "ERROR");
  assert.equal(roadmapUiState(base.roadmap, false, ""), "SUCCESS");
  assert.equal(roadmapUiState(base.roadmap, true, ""), "GENERATING");
  assert.equal(roadmapErrorMessage("TIMEOUT"), "生成计划耗时较长，本次请求已超时。已有差距和优先级不会丢失，可以重新生成。");
  assert.equal(roadmapErrorMessage("INVALID_RESPONSE"), "计划返回内容暂时无法使用。已有差距和优先级不会丢失，请重试。");
  assert.equal(taskStatusLabel("TODO"), "待开始");
  assert.equal(taskStatusLabel("IN_PROGRESS"), "进行中");
  assert.equal(taskStatusLabel("DONE"), "已完成");
  assert.equal(taskStatusLabel("SKIPPED"), "已跳过");
});

test("roadmap requests classify timeout and invalid-response failures without backend debug detail", async () => {
  await assert.rejects(
    () => createRoadmapRequest("profile-1", "http://api.test", async () => new Response(JSON.stringify({ detail: "schema_validation" }), { status: 502 })),
    (error: unknown) => {
      assert.equal((error as { category?: string }).category, "INVALID_RESPONSE");
      assert.equal((error as Error).message, roadmapErrorMessage("INVALID_RESPONSE"));
      assert.doesNotMatch((error as Error).message, /schema_validation/);
      return true;
    },
  );
  await assert.rejects(
    () => createRoadmapRequest("profile-1", "http://api.test", async () => new Response(JSON.stringify({ detail: "timeout" }), { status: 504 })),
    (error: unknown) => {
      assert.equal((error as { category?: string }).category, "TIMEOUT");
      assert.equal((error as Error).message, roadmapErrorMessage("TIMEOUT"));
      assert.doesNotMatch((error as Error).message, /timeout/);
      return true;
    },
  );
});
