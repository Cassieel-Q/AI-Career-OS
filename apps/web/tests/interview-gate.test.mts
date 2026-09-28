import test from "node:test";
import assert from "node:assert/strict";

import {
  buildInterviewTabCompactHints,
  canAdvanceStrengthenEvent,
  canStartInterview,
  canStartFullMissionMock,
  canStartClaimMock,
  deriveResumeSubstep,
  strengthenPrimaryLabel,
  hasVisitedProofWorkflow,
  claimStrengthenProgressLabel,
  proofActionStatusLabel,
  hasCompletedNoExperienceAction,
  isRedTeamExecuted,
  redTeamResultCopy,
  normalizeRedTeamReport,
  isUnknownIdentity,
  parseEvidenceGapCount,
  isInterviewableClaim,
  hasInterviewableClaim,
  resolveInterviewTabCta,
  mockInterviewHref,
  mockInterviewProfileId,
  mockDebriefHref,
  summarizeMockDebrief,
  resolveLastMockDebrief,
  saveLastMockDebrief,
  loadLastMockDebrief,
} from "../app/mission-state.ts";

test("INTERVIEW_PREP_READY + STRENGTHEN_FIRST blocks mock interview", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 15,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(gate.canStartInterview, false);
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "STRENGTHEN_FIRST",
      highRiskCount: 0,
      hasInterviewPack: true,
      evidenceGapCount: 15,
      workflowState: "INTERVIEW_PREP_READY",
    }),
    false,
  );
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.primaryLabel, "下一步：进入补强");
  assert.match(gate.statusMessage, /15/);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.canGeneratePack, false);
  assert.equal(gate.canStartInterview, false);
});

test("no red-team → 开始压力测试; never mock", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: false,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(gate.canStartInterview, false);
  assert.equal(gate.primaryKind, "red_team");
  assert.equal(gate.primaryLabel, "开始压力测试");
  assert.doesNotMatch(gate.primaryLabel, /模拟面试/);
  assert.equal(isRedTeamExecuted({ findings: [] }), false);
  assert.equal(isRedTeamExecuted({ id: "rt-1", findings: [] }), true);
  assert.equal(isRedTeamExecuted({ created_at: "2026-09-24T12:00:00+08:00", findings: [] }), true);
});

test("red-team loading hides empty report and start CTA", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: false,
    redTeamLoading: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(gate.primaryKind, "syncing");
  assert.equal(gate.statusMessage, "正在同步压力测试结果…");
  assert.doesNotMatch(gate.statusMessage, /还没有压力测试报告/);
  assert.doesNotMatch(gate.primaryLabel, /开始压力测试/);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.canStartInterview, false);
  const hints = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "master",
    targetConfirmed: true,
    redTeamExecuted: false,
    redTeamLoading: true,
    highRiskCount: 0,
  });
  assert.ok(hints.some((h) => h === "正在同步压力测试结果…"));
  assert.ok(!hints.some((h) => h.includes("没有压力测试")));
  assert.equal(redTeamResultCopy({ executed: false, findingsCount: 0, loading: true }), "正在同步压力测试结果…");
});

test("READY_TO_APPLY + confirmed + red-team + pack allows mock", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(gate.canStartInterview, true);
  assert.equal(gate.primaryKind, "mock");
  assert.equal(gate.primaryLabel, "开始完整模拟面试");
});

test("compactHints consistent: resume_source binding, not experiences.length", () => {
  const bound = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "master",
    targetConfirmed: false,
    redTeamExecuted: false,
    highRiskCount: 0,
    readinessStatus: "STRENGTHEN_FIRST",
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.ok(bound.includes("简历已选择"));
  assert.ok(!bound.includes("尚未选择简历"));
  assert.ok(bound.includes("尚无压力测试") || bound.some((h) => h.includes("压力")));

  const unbound = buildInterviewTabCompactHints({
    company: "UNKNOWN",
    resumeSourceMode: null,
    targetConfirmed: false,
    redTeamExecuted: true,
    highRiskCount: 2,
    readinessStatus: null,
    workflowState: "RESUME_REQUIRED",
  });
  assert.ok(unbound.includes("尚未选择简历"));
  assert.ok(unbound.includes("JD 待确认"));
  assert.ok(unbound.includes("2 个高风险点"));
});

test("UNKNOWN not treated as confirmed identity", () => {
  assert.equal(isUnknownIdentity("UNKNOWN"), true);
  assert.equal(isUnknownIdentity("N/A"), true);
  assert.equal(isUnknownIdentity("百度"), false);
});

test("parseEvidenceGapCount reads strengthen N from blocks", () => {
  assert.equal(
    parseEvidenceGapCount({
      status: "STRENGTHEN_FIRST",
      blocks: ["Strengthen 15 claim(s) before relying on them in an interview"],
    }),
    15,
  );
});

test("STRENGTHEN_FIRST CTA is 下一步：进入补强 (first visit) and never unlocks generate/mock", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: false,
    evidenceGapCount: 3,
    workflowState: "STRENGTHENING_REQUIRED",
  });
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.primaryLabel, "下一步：进入补强");
  assert.equal(gate.canGeneratePack, false);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.canStartInterview, false);
  assert.doesNotMatch(gate.primaryLabel, /生成面试准备包/);
  assert.doesNotMatch(gate.primaryLabel, /模拟面试/);
});

test("empty red-team report with id still counts as executed", () => {
  assert.equal(isRedTeamExecuted({ findings: [] }), false);
  assert.equal(isRedTeamExecuted({ id: "rt-empty", findings: [] }), true);
  assert.equal(isRedTeamExecuted({ created_at: "2026-09-24T04:55:51.693051+00:00", findings: [] }), true);
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: false,
    evidenceGapCount: 3,
    workflowState: "STRENGTHENING_REQUIRED",
  });
  assert.equal(gate.primaryKind, "strengthen");
  assert.notEqual(gate.primaryKind, "red_team");
});

test("canStartInterview false never allows mock even with INTERVIEW_PREP_READY", () => {
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "INTERVIEW_PREP_READY" as never,
      highRiskCount: 0,
      hasInterviewPack: true,
      workflowState: "INTERVIEW_PREP_READY",
    }),
    false,
  );
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "READY_TO_APPLY",
      highRiskCount: 0,
      hasInterviewPack: false,
    }),
    false,
  );
});

test("canAdvanceStrengthenEvent only for API-valid transitions", () => {
  assert.equal(canAdvanceStrengthenEvent("STRESS_TEST_REQUIRED"), true);
  assert.equal(canAdvanceStrengthenEvent("CLAIM_REEVALUATION_REQUIRED"), true);
  assert.equal(canAdvanceStrengthenEvent("STRENGTHENING_REQUIRED"), false);
  assert.equal(canAdvanceStrengthenEvent("PROOF_IN_PROGRESS"), false);
  assert.equal(canAdvanceStrengthenEvent("INTERVIEW_PREP_READY"), false);
});

test("STRENGTHENING_REQUIRED resume substep is strengthen not ready", () => {
  assert.equal(deriveResumeSubstep("STRENGTHENING_REQUIRED"), "strengthen");
  assert.equal(deriveResumeSubstep("PROOF_IN_PROGRESS"), "strengthen");
  assert.equal(deriveResumeSubstep("INTERVIEW_PREP_READY"), "ready");
});



test("empty_report_interview_never_says_no_pressure", () => {
  const report = { id: "rt-empty-findings", created_at: "2026-09-24T10:16:43+00:00", findings: [] as Array<Record<string, unknown>> };
  const normalized = normalizeRedTeamReport(report);
  assert.equal(isRedTeamExecuted(normalized), true);
  assert.equal(isRedTeamExecuted(report), true);
  const executed = isRedTeamExecuted(report);
  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: executed,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: false,
    evidenceGapCount: 1,
    workflowState: "STRENGTHENING_REQUIRED",
  });
  assert.notEqual(cta.primaryKind, "red_team");
  assert.doesNotMatch(cta.statusMessage, /没有压力测试|还没有压力测试/);
  const hints = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "master",
    targetConfirmed: true,
    redTeamExecuted: executed,
    highRiskCount: 0,
    readinessStatus: "STRENGTHEN_FIRST",
    workflowState: "STRENGTHENING_REQUIRED",
  });
  assert.ok(!hints.some((h) => h.includes("没有压力测试") || h.includes("还没有压力测试")));
  assert.equal(isRedTeamExecuted({ report_id: "nested-id", findings: [] }), true);
  assert.equal(isRedTeamExecuted({ report: { id: "nested", findings: [] }, findings: [] }), true);
});


test("mock CTA visible when canStartInterview true", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 0,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(canStartInterview({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
  }), true);
  assert.equal(gate.canStartInterview, true);
  assert.equal(gate.hideMock, false);
  assert.equal(gate.primaryKind, "mock");
  assert.equal(gate.primaryLabel, "开始完整模拟面试");
});

test("mock CTA hidden when canStartInterview false (strengthen / no pack / no red-team)", () => {
  const strengthen = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 8,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(strengthen.canStartInterview, false);
  assert.equal(strengthen.hideMock, true);
  assert.equal(strengthen.primaryLabel, "下一步：进入补强");
  assert.match(strengthen.statusMessage, /补强|证据/);

  const noPack = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: false,
  });
  assert.equal(noPack.canStartInterview, false);
  assert.equal(noPack.hideMock, true);
  assert.equal(noPack.primaryKind, "generate_pack");

  const noRt = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: false,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
  });
  assert.equal(noRt.canStartInterview, false);
  assert.equal(noRt.hideMock, true);
  assert.equal(noRt.primaryKind, "red_team");
});

test("mockInterviewHref prefers bound_profile_id and includes fresh=1", () => {
  const href = mockInterviewHref({
    id: "mission-1",
    profile_id: "master-profile",
    resume_source: { bound_profile_id: "local-profile" },
  });
  assert.ok(href);
  assert.match(href!, /\/proof\/local-profile\/interview/);
  assert.match(href!, /mission_id=mission-1/);
  assert.match(href!, /fresh=1/);
  assert.equal(
    mockInterviewProfileId({ profile_id: "master-profile", resume_source: { bound_profile_id: "local-profile" } }),
    "local-profile",
  );
  assert.equal(mockInterviewProfileId({ profile_id: "master-profile", resume_source: null }), "master-profile");
  const debrief = mockDebriefHref({
    id: "mission-1",
    profile_id: "master-profile",
    resume_source: { bound_profile_id: "local-profile" },
  });
  assert.match(debrief!, /\/proof\/local-profile\/debrief/);
});

test("summarizeMockDebrief only for COMPLETED; memory helpers safe", () => {
  assert.equal(summarizeMockDebrief({ id: "s1", status: "ACTIVE", weak_points: ["x"] }), null);
  const done = summarizeMockDebrief({
    id: "s2",
    status: "COMPLETED",
    weak_points: ["表达偏散", "缺证据"],
    strong_points: ["结构清晰"],
    gap_type: "EVIDENCE_GAP",
    gap_why: "缺少上线数据",
    recommended_next_action: "补一份数据证明",
    round_count: 3,
    updated_at: "2026-09-24T12:00:00+08:00",
    claim_id: "c1",
  });
  assert.ok(done);
  assert.equal(done!.sessionId, "s2");
  assert.deepEqual(done!.weakPoints, ["表达偏散", "缺证据"]);
  assert.equal(done!.gapType, "EVIDENCE_GAP");
  saveLastMockDebrief("m-test", done!);
  loadLastMockDebrief("m-test");
  const resolved = resolveLastMockDebrief("m-test", {
    id: "s2",
    status: "COMPLETED",
    weak_points: ["表达偏散"],
  });
  assert.equal(resolved?.sessionId, "s2");
});


test("isInterviewableClaim mirrors API: bare UNSUPPORTED blocked; evidenced OK", () => {
  assert.equal(
    isInterviewableClaim({ id: "c1", readiness_status: "UNSUPPORTED", evidence_refs: [] }),
    false,
  );
  assert.equal(
    isInterviewableClaim({ id: "c2", readiness_status: "UNSUPPORTED", evidence_refs: ["ev-1"] }),
    true,
  );
  assert.equal(
    isInterviewableClaim({ id: "c3", readiness_status: "WEAK_EVIDENCE", evidence_refs: [] }),
    true,
  );
  assert.equal(
    isInterviewableClaim({ id: "c4", readiness_status: "DEFENDABLE", evidence_refs: ["ev-2"] }),
    true,
  );
  assert.equal(
    isInterviewableClaim({ id: "c5", readiness_status: "SUPPORTED", evidence_refs: [] }),
    true,
  );
  assert.equal(hasInterviewableClaim([]), false);
  assert.equal(
    hasInterviewableClaim([{ id: "u1", readiness_status: "UNSUPPORTED", evidence_refs: [] }]),
    false,
  );
  assert.equal(
    hasInterviewableClaim([
      { id: "u1", readiness_status: "UNSUPPORTED", evidence_refs: [] },
      { id: "d1", readiness_status: "DEFENDABLE", evidence_refs: ["e1"] },
    ]),
    true,
  );
});

test("isInterviewableClaim treats literal None/null/undefined refs as no evidence", () => {
  assert.equal(
    isInterviewableClaim({ id: "n1", readiness_status: "UNSUPPORTED", evidence_refs: ["None"] }),
    false,
  );
  assert.equal(
    isInterviewableClaim({ id: "n2", readiness_status: "UNSUPPORTED", evidence_refs: ["none"] }),
    false,
  );
  assert.equal(
    isInterviewableClaim({ id: "n3", readiness_status: "UNSUPPORTED", evidence_refs: ["null", "undefined", "", "  "] }),
    false,
  );
  assert.equal(
    isInterviewableClaim({ id: "n4", readiness_status: "UNSUPPORTED", evidence_refs: [null, undefined, "None"] }),
    false,
  );
  assert.equal(
    isInterviewableClaim({ id: "ok1", readiness_status: "UNSUPPORTED", evidence_refs: ["ev-real-1"] }),
    true,
  );
  assert.equal(
    isInterviewableClaim({ id: "ok2", readiness_status: "DEFENDABLE", evidence_refs: [] }),
    true,
  );
  assert.equal(
    isInterviewableClaim({ id: "ok3", readiness_status: "DEFENDABLE", evidence_refs: ["None"] }),
    true,
  );
  assert.equal(
    hasInterviewableClaim([
      { id: "n1", readiness_status: "UNSUPPORTED", evidence_refs: ["None"] },
    ]),
    false,
  );
  assert.equal(
    hasInterviewableClaim([
      { id: "n1", readiness_status: "UNSUPPORTED", evidence_refs: ["None"] },
      { id: "d1", readiness_status: "DEFENDABLE", evidence_refs: ["e1"] },
    ]),
    true,
  );
});

test("READY + pack but only bare UNSUPPORTED claims: hide mock + Chinese why", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 0,
    workflowState: "INTERVIEW_PREP_READY",
    hasInterviewableClaim: false,
  });
  assert.equal(gate.canStartInterview, false);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.primaryLabel, "下一步：进入补强");
  assert.match(gate.statusMessage, /尚无可面试主张|补证据/);
  assert.doesNotMatch(gate.statusMessage, /UNSUPPORTED|interviewable/i);
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "READY_TO_APPLY",
      highRiskCount: 0,
      hasInterviewPack: true,
      hasInterviewableClaim: false,
    }),
    false,
  );
});

test("READY + interviewable claim allows mock CTA", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 0,
    workflowState: "INTERVIEW_PREP_READY",
    hasInterviewableClaim: true,
  });
  assert.equal(gate.canStartInterview, true);
  assert.equal(gate.hideMock, false);
  assert.equal(gate.primaryKind, "mock");
  assert.equal(gate.primaryLabel, "开始完整模拟面试");
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "READY_TO_APPLY",
      highRiskCount: 0,
      hasInterviewPack: true,
      hasInterviewableClaim: true,
    }),
    true,
  );
});

test("STRENGTHEN_FIRST still wins over missing interviewable claims", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 4,
    workflowState: "INTERVIEW_PREP_READY",
    hasInterviewableClaim: false,
  });
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.primaryLabel, "下一步：进入补强");
  assert.match(gate.statusMessage, /4/);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.canGeneratePack, false);
});

test("strengthenPrimaryLabel first vs return", () => {
  assert.equal(strengthenPrimaryLabel({ hasVisitedProof: false }), "下一步：进入补强");
  assert.equal(strengthenPrimaryLabel({}), "下一步：进入补强");
  assert.equal(strengthenPrimaryLabel({ hasVisitedProof: true }), "返回补强");
});

test("hasVisitedProofWorkflow detects proof lane", () => {
  assert.equal(hasVisitedProofWorkflow("STRENGTHENING_REQUIRED"), true);
  assert.equal(hasVisitedProofWorkflow("PROOF_IN_PROGRESS"), true);
  assert.equal(hasVisitedProofWorkflow("CLAIM_REEVALUATION_REQUIRED"), true);
  assert.equal(hasVisitedProofWorkflow("STRESS_TEST_REQUIRED"), false);
  assert.equal(hasVisitedProofWorkflow("INTERVIEW_PREP_READY"), false);
});

test("resolveInterviewTabCta keeps a forward next-step label", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 2,
    workflowState: "INTERVIEW_PREP_READY",
    hasVisitedProof: true,
  });
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.primaryLabel, "下一步：进入补强");
});

test("claimStrengthenProgressLabel humanizes without raw enums", () => {
  assert.equal(claimStrengthenProgressLabel({ readinessStatus: "WEAK_EVIDENCE" }), "仍不足");
  assert.equal(claimStrengthenProgressLabel({ readinessStatus: "UNSUPPORTED" }), "待处理");
  assert.equal(claimStrengthenProgressLabel({ readinessStatus: "SUPPORTED" }), "已补强");
  assert.equal(claimStrengthenProgressLabel({ hasArtifact: true }), "已提交材料");
  assert.equal(claimStrengthenProgressLabel({ markedNoExperience: true }), "已标记无此经历");
  assert.equal(
    claimStrengthenProgressLabel({
      readinessStatus: "WEAK_EVIDENCE",
      actionStatuses: ["PROPOSED"],
      markedNoExperience: false,
    }),
    "仍不足",
  );
  assert.doesNotMatch(claimStrengthenProgressLabel({ readinessStatus: "WEAK_EVIDENCE" }), /WEAK_EVIDENCE/);
});

test("proof action labels and no-experience mark use completed state", () => {
  assert.equal(proofActionStatusLabel("PROPOSED"), "待填写");
  assert.equal(proofActionStatusLabel("COMPLETED"), "已提交");
  assert.equal(proofActionStatusLabel("SKIPPED"), "已跳过");
  const mark = { artifact_type: "NO_EXPERIENCE_MARK", title: "标记：我没有这段经历" };
  assert.equal(hasCompletedNoExperienceAction([{ ...mark, status: "PROPOSED" }]), false);
  assert.equal(hasCompletedNoExperienceAction([{ ...mark, status: "COMPLETED" }]), true);
});

test("TARGET_RESUME_CONFIRMED stays on target substep", () => {
  assert.equal(deriveResumeSubstep("TARGET_RESUME_CONFIRMED"), "target");
  assert.equal(deriveResumeSubstep("STRESS_TEST_REQUIRED"), "stress");
});


test("canStartFullMissionMock true only when READY + pack + interviewable", () => {
  const base = {
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY" as const,
    highRiskCount: 0,
    hasInterviewPack: true,
    hasInterviewableClaim: true,
  };
  assert.equal(canStartFullMissionMock(base), true);
  assert.equal(canStartInterview(base), true);
  assert.equal(canStartFullMissionMock({ ...base, readinessStatus: "STRENGTHEN_FIRST" }), false);
  assert.equal(canStartFullMissionMock({ ...base, hasInterviewPack: false }), false);
  assert.equal(canStartFullMissionMock({ ...base, hasInterviewableClaim: false }), false);
  assert.equal(canStartFullMissionMock({ ...base, highRiskCount: 1 }), false);
  assert.equal(canStartFullMissionMock({ ...base, redTeamLoading: true }), false);
});

test("canStartClaimMock true under STRENGTHEN_FIRST with interviewable claim", () => {
  const input = {
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: false,
    hasInterviewableClaim: true,
    evidenceGapCount: 5,
  };
  assert.equal(canStartClaimMock(input), true);
  assert.equal(canStartFullMissionMock(input), false);
  const gate = resolveInterviewTabCta(input);
  assert.equal(gate.canStartClaimMock, true);
  assert.equal(gate.canStartFullMissionMock, false);
  assert.equal(gate.canStartInterview, false);
  assert.equal(gate.hideMock, true);
  assert.equal(gate.primaryKind, "strengthen");
  assert.equal(gate.secondaryLabel, "开始单主张拷问");
  assert.match(gate.statusMessage, /单主张拷问/);
});

test("canStartClaimMock false without interviewable claim", () => {
  const input = {
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    hasInterviewableClaim: false,
    evidenceGapCount: 3,
  };
  assert.equal(canStartClaimMock(input), false);
  assert.equal(canStartFullMissionMock(input), false);
  const gate = resolveInterviewTabCta(input);
  assert.equal(gate.canStartClaimMock, false);
  assert.equal(gate.canStartFullMissionMock, false);
  assert.equal(gate.secondaryLabel, undefined);
});

test("full mock false under STRENGTHEN even with interviewable; claim mock true", () => {
  const input = {
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    hasInterviewableClaim: true,
    evidenceGapCount: 8,
    workflowState: "INTERVIEW_PREP_READY",
  };
  assert.equal(canStartFullMissionMock(input), false);
  assert.equal(canStartInterview(input), false);
  assert.equal(canStartClaimMock(input), true);
  const gate = resolveInterviewTabCta(input);
  assert.equal(gate.canStartFullMissionMock, false);
  assert.equal(gate.canStartClaimMock, true);
  assert.equal(gate.primaryKind, "strengthen");
  assert.notEqual(gate.primaryLabel, "开始完整模拟面试");
});

test("READY gate exposes full mock primary label 开始完整模拟面试", () => {
  const gate = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    hasInterviewableClaim: true,
  });
  assert.equal(gate.canStartFullMissionMock, true);
  assert.equal(gate.canStartClaimMock, true);
  assert.equal(gate.primaryKind, "mock");
  assert.equal(gate.primaryLabel, "开始完整模拟面试");
});
