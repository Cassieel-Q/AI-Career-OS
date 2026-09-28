import test from "node:test";
import assert from "node:assert/strict";

import {
  deriveTab,
  countHighRiskFindings,
  deriveResumeFlowStep,
  humanizeMissionError,
  validateMissionDebrief,
  isUnknownIdentity,
  identityInputValue,
  seniorityLabel,
  locationLabel,
  missionIdentityLabel,
  missionStatusLabel,
  resumePrimaryCta,
  primaryCta,
  deriveResumeSubstep,
  targetResumeConfirmed,
  targetResumeBulletDisplayText,
  buildTargetResumeInlineEditPatch,
  targetResumeBulletStatusLabel,
  classifyIntelSource,
  intelSourceTypeLabel,
  summarizeIntelCoverage,
  resolveJdEvidenceTexts,
  buildCapabilityEvidenceView,
  buildJdRequirementEvidenceCoverage,
  classifyCapabilityEvidenceLevel,
  PENDING_CONFIRM_LABEL,
  COMPANY_PENDING_LABEL,
  COMPANY_INPUT_PLACEHOLDER,
  partitionIntelBySource,
  canStartInterview,
  isRedTeamExecuted,
  normalizeRedTeamReport,
  redTeamResultCopy,
  parseEvidenceGapCount,
  resolveInterviewTabCta,
  resolveProofNextStep,
  buildInterviewTabCompactHints,
  looksLikePlaceholderResume,
  boundResumeSourceSummary,
} from "../app/mission-state.ts";
import { missionTabLabel, MISSION_TABS } from "../app/missions.ts";

test("mission tabs are the four user-facing stages in Chinese", () => {
  assert.deepEqual(MISSION_TABS, ["role", "resume", "interview", "outcome"]);
  assert.equal(missionTabLabel("role"), "目标岗位");
  assert.equal(missionTabLabel("resume"), "简历优化");
  assert.equal(missionTabLabel("proof"), "补强");
  assert.equal(missionTabLabel("interview"), "模拟面试");
  assert.equal(missionTabLabel("outcome"), "面试记录");
});

test("resume flow requires binding before generation steps", () => {
  assert.equal(deriveResumeFlowStep({
    resumeBound: false,
    experienceCount: 0,
    selectionCount: 0,
    hasStrategy: false,
    hasTargetResume: false,
    targetConfirmed: false,
    hasRedTeam: false,
    highRiskCount: 0,
  }), "source");

  assert.equal(deriveResumeFlowStep({
    resumeBound: true,
    experienceCount: 2,
    selectionCount: 0,
    hasStrategy: false,
    hasTargetResume: false,
    targetConfirmed: false,
    hasRedTeam: false,
    highRiskCount: 0,
  }), "selection");

  assert.equal(deriveResumeFlowStep({
    resumeBound: true,
    experienceCount: 2,
    selectionCount: 2,
    hasStrategy: true,
    hasTargetResume: false,
    targetConfirmed: false,
    hasRedTeam: false,
    highRiskCount: 0,
  }), "target");

  assert.equal(deriveResumeFlowStep({
    resumeBound: true,
    experienceCount: 2,
    selectionCount: 2,
    hasStrategy: true,
    hasTargetResume: true,
    targetConfirmed: true,
    hasRedTeam: true,
    highRiskCount: 2,
  }), "stress");

  assert.equal(resumePrimaryCta("strategy", 0, { hasStrategy: false }), "生成本岗位简历策略");
  assert.equal(resumePrimaryCta("strategy", 0, { hasStrategy: true }), "下一步：生成目标简历");
  assert.equal(resumePrimaryCta("stress", 2), "先补最危险的一项");
  assert.equal(resumePrimaryCta("stress", 0), "进入面试准备");
  assert.equal(resumePrimaryCta("strengthen"), "下一步：进入补强");
  assert.equal(primaryCta("TARGET_RESUME_CONFIRMED"), "下一步：进入模拟面试");
  assert.equal(deriveResumeSubstep("TARGET_RESUME_CONFIRMED"), "target");
  assert.equal(deriveResumeSubstep("STRESS_TEST_REQUIRED"), "stress");
});

test("proof next step keeps the user on a concrete forward path", () => {
  assert.deepEqual(
    resolveProofNextStep({
      targetConfirmed: false,
      readinessStatus: "STRENGTHEN_FIRST",
      claims: [],
    }),
    { kind: "resume", label: "下一步：确认目标简历" },
  );
  assert.deepEqual(
    resolveProofNextStep({
      targetConfirmed: true,
      readinessStatus: "STRENGTHEN_FIRST",
      claims: [{ id: "c1", readiness_status: "WEAK_EVIDENCE", evidence_refs: [] }],
      proofActions: [{ status: "PROPOSED" }],
    }),
    { kind: "strengthen", label: "继续补强" },
  );
  assert.deepEqual(
    resolveProofNextStep({
      targetConfirmed: true,
      readinessStatus: "STRENGTHEN_FIRST",
      claims: [{ id: "c1", readiness_status: "WEAK_EVIDENCE", evidence_refs: ["ev-1"] }],
      proofActions: [{ status: "COMPLETED" }],
    }),
    { kind: "strengthen", label: "继续补强" },
  );
  assert.deepEqual(
    resolveProofNextStep({
      targetConfirmed: true,
      readinessStatus: "READY_TO_APPLY",
      claims: [{ id: "c1", readiness_status: "DEFENDABLE", evidence_refs: ["ev-1"] }],
      proofActions: [{ status: "PROPOSED" }],
    }),
    { kind: "interview", label: "下一步：进入面试拷问" },
  );
});

test("provider errors are humanized for users", () => {
  assert.match(
    humanizeMissionError("Mission intelligence returned an unusable response; please retry", "company_intel"),
    /公司面试情报/,
  );
  assert.match(humanizeMissionError("schema_validation provider", "jd_analysis"), /岗位分析/);
  assert.match(humanizeMissionError("Generate a Resume Strategy before drafting a Target Resume"), /简历策略/);
  assert.match(
    humanizeMissionError("Complete an interview stress test before creating proof actions"),
    /请先完成压力测试，再创建补强证据/,
  );
  assert.match(humanizeMissionError("请先完成压力测试，再创建补强证据"), /请先完成压力测试/);
});

test("target confirmation and risk counting helpers", () => {
  assert.equal(targetResumeConfirmed([{ status: "SUGGESTED" }]), true); // default-accept
  assert.equal(targetResumeConfirmed([{ status: "ACCEPTED" }, { status: "EDITED" }]), true);
  assert.equal(countHighRiskFindings([{ risk_level: "HIGH" }, { risk_level: "MEDIUM" }]), 1);
  assert.equal(missionStatusLabel("RESUME_PREP"), "准备中");
});


test("mission identity helpers hide UNKNOWN chrome", () => {
  assert.equal(isUnknownIdentity("UNKNOWN"), true);
  assert.equal(isUnknownIdentity("n/a"), true);
  assert.equal(isUnknownIdentity("NULL"), true);
  assert.equal(isUnknownIdentity("Staff"), false);
  assert.equal(identityInputValue("UNKNOWN"), "");
  assert.equal(identityInputValue("百度"), "百度");
  assert.equal(identityInputValue(null), "");
  assert.equal(
    missionIdentityLabel({ company: "UNKNOWN", role: "UNKNOWN", display_name: "UNKNOWN · UNKNOWN" }),
    COMPANY_PENDING_LABEL,
  );
  assert.equal(
    missionIdentityLabel({ company: "UNKNOWN", role: "AI产品经理", display_name: "AI产品经理" }),
    `${COMPANY_PENDING_LABEL} · AI产品经理`,
  );
  assert.equal(
    missionIdentityLabel({ company: "Acme", role: "UNKNOWN", display_name: null }),
    "Acme",
  );
  assert.equal(
    missionIdentityLabel({ company: "Acme", role: "SWE", display_name: "Acme · SWE" }),
    "Acme · SWE",
  );
  assert.equal(COMPANY_INPUT_PLACEHOLDER, "例如：百度");
  // Card/form surfaces must not echo bare UNKNOWN.
  const cardCompany = isUnknownIdentity("UNKNOWN") ? "" : "UNKNOWN";
  const cardSeniority = isUnknownIdentity("UNKNOWN") ? "" : "UNKNOWN";
  const formCompany = identityInputValue("UNKNOWN");
  assert.equal(cardCompany, "");
  assert.equal(cardSeniority, "");
  assert.equal(formCompany, "");
  assert.doesNotMatch(`${cardCompany}|${formCompany}|${cardSeniority}`, /UNKNOWN/i);
  assert.equal(PENDING_CONFIRM_LABEL, "待确认");
});

test("company_manual_entry_and_retry_intel closes identity + provenance loop", () => {
  // 1) Pending company chrome before补录
  assert.equal(
    missionIdentityLabel({ company: "UNKNOWN", role: "AI产品经理", display_name: "AI产品经理" }),
    `${COMPANY_PENDING_LABEL} · AI产品经理`,
  );
  assert.equal(isUnknownIdentity("UNKNOWN"), true);
  assert.equal(isUnknownIdentity(""), true);

  // 2) After保存识别结果 with 百度, title + enable gate flip
  const saved = { company: "百度", role: "AI产品经理", display_name: "百度 · AI产品经理" };
  assert.equal(isUnknownIdentity(saved.company), false);
  assert.equal(missionIdentityLabel(saved), "百度 · AI产品经理");
  const retryDisabled = isUnknownIdentity(saved.company); // mirrors button: busy || companyPending
  assert.equal(retryDisabled, false);

  // 3) Rematch layers: curated SAME_COMPANY vs synthetic demo; synthetic never in realCompany
  const afterRetry = [
    {
      skill_id: "CURATED_BAIDU_AI_PRODUCT",
      name: "Baidu curated AI_PRODUCT interview signals",
      company_relevance: "SAME_COMPANY",
      source_refs: ["https://www.nowcoder.com/discuss/1"],
      provenance: "CURATED",
    },
    {
      skill_id: "AGENT_WORKFLOW",
      name: "Agent workflow",
      company_relevance: "GENERIC",
      source_refs: ["synthetic-generic-report"],
      provenance: "SYNTHETIC_GENERIC",
    },
    {
      skill_id: "DEMO_BAIDU_AI_PM_METRICS",
      name: "Demo baidu metrics",
      company_relevance: "SAME_COMPANY",
      source_refs: ["demo-only"],
      provenance: "SYNTHETIC_DEMO",
    },
    {
      skill_id: "CURATED_RELATED",
      name: "Adjacent role",
      company_relevance: "ROLE_FAMILY",
      source_refs: ["https://www.nowcoder.com/discuss/2"],
      provenance: "CURATED",
    },
  ];
  assert.equal(classifyIntelSource(afterRetry[0]), "REAL_COMPANY");
  assert.equal(classifyIntelSource(afterRetry[1]), "SYNTHETIC_DEMO");
  assert.equal(classifyIntelSource(afterRetry[2]), "SYNTHETIC_DEMO"); // demo skill_id wins over SAME_COMPANY
  assert.equal(classifyIntelSource(afterRetry[3]), "RELATED_ROLE");
  const layers = partitionIntelBySource(afterRetry);
  assert.equal(layers.realCompany.length, 1);
  assert.equal(layers.realCompany[0]?.skill_id, "CURATED_BAIDU_AI_PRODUCT");
  assert.equal(layers.relatedRole.length, 1);
  assert.equal(layers.synthetic.length, 2);
  assert.ok(layers.realCompany.every((item) => classifyIntelSource(item) === "REAL_COMPANY"));
  assert.ok(!layers.realCompany.some((item) => String(item.skill_id || "").startsWith("DEMO_")));

  // 4) Zero-real copy when company confirmed (UI acceptance string)
  const coverage = summarizeIntelCoverage([afterRetry[1], afterRetry[2]]);
  assert.equal(coverage.curatedCompany, 0);
  assert.equal(coverage.synthetic, 2);
  const companyName = identityInputValue(saved.company) || "该公司";
  const zeroRealCopy = `目标公司真实面经：0 条。当前没有已验证的${companyName}真实面经，以下为通用或合成演示。`;
  assert.match(zeroRealCopy, /目标公司真实面经：0 条/);
  assert.match(zeroRealCopy, /当前没有已验证的百度真实面经，以下为通用或合成演示/);
});


test("interview intel source types distinguish synthetic from real company reports", () => {
  assert.equal(
    classifyIntelSource({
      skill_id: "CURATED_BAIDU_AI_PRODUCT",
      company_relevance: "SAME_COMPANY",
      source_refs: ["https://www.nowcoder.com/discuss/1"],
      provenance: "CURATED_NIUKE",
    }),
    "REAL_COMPANY",
  );
  assert.equal(intelSourceTypeLabel("REAL_COMPANY"), "目标公司真实面经");
  assert.equal(intelSourceTypeLabel("RELATED_ROLE"), "相近岗位真实面经");
  assert.equal(intelSourceTypeLabel("GENERIC_FALLBACK"), "通用面经");
  assert.equal(
    classifyIntelSource({
      skill_id: "AGENT_WORKFLOW",
      company_relevance: "GENERIC",
      source_refs: ["synthetic-generic-report"],
      provenance: "SYNTHETIC_GENERIC",
    }),
    "SYNTHETIC_DEMO",
  );
  assert.equal(intelSourceTypeLabel("SYNTHETIC_DEMO"), "合成演示");
  const coverageItems = [
    { company_relevance: "SAME_COMPANY", source_refs: ["https://nowcoder.com/x"], provenance: "CURATED" },
    { company_relevance: "ROLE_FAMILY", source_refs: ["https://nowcoder.com/y"], provenance: "CURATED" },
    { company_relevance: "GENERIC", source_refs: ["generic-report"], provenance: "GENERIC_FALLBACK" },
    { company_relevance: "GENERIC", source_refs: ["synthetic-generic-report"], skill_id: "DEMO_X" },
  ];
  const coverage = summarizeIntelCoverage(coverageItems);
  assert.equal(coverage.curatedCompany, 1);
  assert.equal(coverage.relatedRole, 1);
  assert.equal(coverage.generic, 1);
  assert.equal(coverage.synthetic, 1);
  assert.equal(coverage.otherCompany, 1);
  assert.equal(coverage.fallback, 2);
  const parts = partitionIntelBySource(coverageItems);
  assert.equal(parts.realCompany.length, 1);
  assert.equal(parts.relatedRole.length, 1);
  assert.equal(parts.generic.length, 1);
  assert.equal(parts.synthetic.length, 1);
});

test("capability evidence view surfaces JD snippet and pending confirm", () => {
  const parsedJd = {
    requirements: [{ id: "req_2", text: "有 AI/LLM 相关项目优先", evidence_text: "有 AI/LLM 相关项目优先" }],
    preferred_requirements: [],
  };
  assert.deepEqual(resolveJdEvidenceTexts(["req_2"], parsedJd), ["有 AI/LLM 相关项目优先"]);
  const withJd = buildCapabilityEvidenceView({
    capability: { name: "大模型应用产品规划与落地", why: "核心", evidence_refs: ["req_2"] },
    parsedJd,
    whatMatters: { confidence: 0.55, jd_evidence_refs: ["req_2"] },
    interviewIntel: [
      {
        skill_id: "CURATED_BAIDU_AI_PRODUCT",
        name: "Baidu curated AI_PRODUCT interview signals",
        company_relevance: "SAME_COMPANY",
        competency: "项目深挖",
        confidence: 0.95,
        source_refs: ["https://www.nowcoder.com/discuss/1"],
        provenance: "CURATED_NIUKE",
        body: "大模型 RAG Agent",
      },
    ],
  });
  assert.deepEqual(withJd.jdEvidence, ["有 AI/LLM 相关项目优先"]);
  assert.equal(withJd.sourceType, "目标公司真实面经");
  assert.equal(withJd.pendingConfirm, false);
  assert.match(withJd.confidenceLabel, /95%/);

  const inferred = buildCapabilityEvidenceView({
    capability: { name: "神秘能力", why: "模型猜的", evidence_refs: [] },
    parsedJd,
    whatMatters: { confidence: 0.4, jd_evidence_refs: [] },
    interviewIntel: [],
  });
  assert.equal(inferred.jdEvidence.length, 0);
  assert.equal(inferred.pendingConfirm, true);
  assert.match(inferred.pendingReason, /模型推断|待确认/);
  assert.equal(inferred.sourceType, "模型推断");
});


test("JD requirement evidence coverage uses direct/total and honest empty", () => {
  const parsedJd = {
    requirements: [{ id: "req_2", text: "有 AI/LLM 相关项目优先", evidence_text: "有 AI/LLM 相关项目优先" }],
    preferred_requirements: [],
  };
  const filled = buildJdRequirementEvidenceCoverage({
    whatMatters: {
      confidence: 0.55,
      jd_evidence_refs: ["req_2"],
      core_capabilities: [
        { name: "大模型应用产品规划与落地", why: "核心", evidence_refs: ["req_2"] },
        { name: "神秘能力", why: "模型猜的", evidence_refs: [] },
      ],
    },
    parsedJd,
    interviewIntel: [
      {
        skill_id: "CURATED_BAIDU_AI_PRODUCT",
        name: "Baidu curated AI_PRODUCT interview signals",
        company_relevance: "SAME_COMPANY",
        competency: "项目深挖",
        confidence: 0.95,
        source_refs: ["https://www.nowcoder.com/discuss/1"],
        provenance: "CURATED_NIUKE",
        body: "大模型 RAG Agent",
      },
    ],
  });
  assert.equal(filled.total, 2);
  assert.equal(filled.direct, 1);
  assert.equal(filled.coveragePct, 50);
  assert.equal(filled.rows[0]?.level, "直接证据");
  assert.ok(filled.rows[1]?.level === "没有证据" || filled.rows[1]?.level === "待用户确认");
  assert.equal(
    classifyCapabilityEvidenceLevel(
      buildCapabilityEvidenceView({
        capability: { name: "神秘能力", evidence_refs: [] },
        parsedJd,
        whatMatters: {},
        interviewIntel: [],
      }),
    ),
    "没有证据",
  );

  const empty = buildJdRequirementEvidenceCoverage({
    whatMatters: { core_capabilities: [] },
    parsedJd: { requirements: [] },
    interviewIntel: [],
  });
  assert.equal(empty.total, 0);
  assert.equal(empty.coveragePct, null);
});

test("deriveTab prefers first incomplete gate over late INTERVIEW label", () => {
  assert.equal(deriveTab("INTERVIEW_PREP_READY"), "resume");
  assert.equal(deriveTab("INTERVIEW_PREP_READY", { resumeSource: null }), "resume");
  assert.equal(
    deriveTab("INTERVIEW_PREP_READY", { resumeSource: { mode: "master" }, resumeStrategy: { positioning: "x" } }),
    "interview",
  );
  assert.equal(deriveTab("ROLE_UNDERSTOOD"), "role");
  assert.equal(deriveTab("RESUME_REQUIRED", { resumeSource: null }), "resume");
  assert.equal(
    deriveTab("STRENGTHENING_REQUIRED", { resumeSource: { mode: "upload" }, resumeStrategy: {} }),
    "resume",
  );
  assert.equal(
    deriveTab("STRENGTHENING_REQUIRED", { resumeSource: { mode: "upload" }, resumeStrategy: { focus: "impact" } }),
    "proof",
  );
});


test("canStartInterview rejects INTERVIEW_PREP_READY + STRENGTHEN_FIRST", () => {
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "STRENGTHEN_FIRST",
      highRiskCount: 0,
      hasInterviewPack: true,
      workflowState: "INTERVIEW_PREP_READY",
    }),
    false,
  );
  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: true,
    evidenceGapCount: 15,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(cta.canStartInterview, false);
  assert.equal(cta.hideMock, true);
  assert.equal(cta.canGeneratePack, false);
  assert.equal(cta.primaryKind, "strengthen");
  assert.equal(cta.primaryLabel, "下一步：进入补强");
  assert.match(cta.statusMessage, /15/);
});


test("red_team_empty_report_counts_as_executed", () => {
  assert.equal(isRedTeamExecuted({ findings: [] }), false);
  assert.equal(isRedTeamExecuted({ mission_id: "m1", findings: [] }), false);
  assert.equal(isRedTeamExecuted({ id: "r1", findings: [] }), true);
  assert.equal(isRedTeamExecuted({ created_at: "2026-09-24T00:00:00Z", findings: [] }), true);
  assert.equal(isRedTeamExecuted({ id: "r1", created_at: "2026-09-24T00:00:00Z", findings: [] }), true);

  const emptyCopy = redTeamResultCopy({ executed: true, findingsCount: 0, highRiskCount: 0 });
  assert.match(emptyCopy, /压力测试已完成/);
  assert.doesNotMatch(emptyCopy, /还没有压力测试结果/);

  const missingCopy = redTeamResultCopy({ executed: false, findingsCount: 0 });
  assert.match(missingCopy, /还没有压力测试结果/);

  const highCopy = redTeamResultCopy({ executed: true, findingsCount: 3, highRiskCount: 2 });
  assert.equal(highCopy, "发现 2 项需要补强的高风险追问");

  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "STRENGTHEN_FIRST",
    highRiskCount: 0,
    hasInterviewPack: false,
    evidenceGapCount: 2,
    workflowState: "STRESS_TEST_REQUIRED",
  });
  assert.equal(cta.primaryKind, "strengthen");
  assert.doesNotMatch(cta.statusMessage, /请先完成压力测试/);
  assert.doesNotMatch(cta.statusMessage, /还没有压力测试/);

  const hints = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "upload",
    targetConfirmed: true,
    redTeamExecuted: true,
    highRiskCount: 0,
    readinessStatus: "STRENGTHEN_FIRST",
  });
  assert.ok(!hints.includes("没有压力测试"));
});

test("red-team loading copy and CTA", () => {
  assert.equal(redTeamResultCopy({ executed: false, findingsCount: 0, loading: true }), "正在同步压力测试结果…");
  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: false,
    redTeamLoading: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: false,
  });
  assert.equal(cta.primaryKind, "syncing");
  assert.equal(cta.statusMessage, "正在同步压力测试结果…");
  assert.doesNotMatch(cta.statusMessage, /还没有压力测试报告/);
  const hints = buildInterviewTabCompactHints({
    company: "X",
    resumeSourceMode: "master",
    targetConfirmed: true,
    redTeamExecuted: false,
    redTeamLoading: true,
    highRiskCount: 0,
  });
  assert.ok(hints.includes("正在同步压力测试结果…"));
  assert.ok(!hints.includes("没有压力测试"));
});

test("core interview hints describe question preview instead of strengthen gate", () => {
  const before = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "master",
    targetConfirmed: true,
    redTeamExecuted: true,
    highRiskCount: 2,
    readinessStatus: "STRENGTHEN_FIRST",
    hasInterviewPack: false,
    coreMode: true,
  });
  assert.ok(before.includes("先生成问题预览"));
  assert.ok(!before.includes("需要补强"));

  const after = buildInterviewTabCompactHints({
    company: "百度",
    resumeSourceMode: "master",
    targetConfirmed: true,
    redTeamExecuted: true,
    highRiskCount: 2,
    readinessStatus: "STRENGTHEN_FIRST",
    hasInterviewPack: true,
    coreMode: true,
  });
  assert.ok(after.includes("问题预览已生成"));
  assert.ok(!after.includes("需要补强"));
});


test("no red-team shows pressure-test CTA and hides mock", () => {
  assert.equal(isRedTeamExecuted({ findings: [] }), false);
  assert.equal(isRedTeamExecuted({ id: "r1", findings: [] }), true);
  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: false,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
    workflowState: "INTERVIEW_PREP_READY",
  });
  assert.equal(cta.canStartInterview, false);
  assert.equal(cta.hideMock, true);
  assert.equal(cta.primaryKind, "red_team");
  assert.equal(cta.primaryLabel, "\u5f00\u59cb\u538b\u529b\u6d4b\u8bd5");
  assert.equal(cta.canGeneratePack, false);
});

test("READY_TO_APPLY + confirmed target + red-team done allows mock", () => {
  assert.equal(
    canStartInterview({
      targetConfirmed: true,
      redTeamExecuted: true,
      readinessStatus: "READY_TO_APPLY",
      highRiskCount: 0,
      hasInterviewPack: true,
    }),
    true,
  );
  const cta = resolveInterviewTabCta({
    targetConfirmed: true,
    redTeamExecuted: true,
    readinessStatus: "READY_TO_APPLY",
    highRiskCount: 0,
    hasInterviewPack: true,
  });
  assert.equal(cta.canStartInterview, true);
  assert.equal(cta.hideMock, false);
  assert.equal(cta.primaryKind, "mock");
  assert.equal(cta.primaryLabel, "\u5f00\u59cb\u5b8c\u6574\u6a21\u62df\u9762\u8bd5");
  assert.equal(cta.canStartFullMissionMock, true);
  assert.equal(cta.canStartClaimMock, true);
});

test("interview compactHints stay consistent with body status lines", () => {
  assert.deepEqual(
    buildInterviewTabCompactHints({
      company: "\u767e\u5ea6\u667a\u80fd\u4e91",
      resumeSourceMode: "paste",
      targetConfirmed: true,
      redTeamExecuted: false,
      highRiskCount: 0,
      readinessStatus: "STRENGTHEN_FIRST",
      workflowState: "INTERVIEW_PREP_READY",
    }),
    ["JD \u5df2\u89e3\u6790", "\u7b80\u5386\u5df2\u9009\u62e9", "\u6ca1\u6709\u538b\u529b\u6d4b\u8bd5"],
  );
  assert.deepEqual(
    buildInterviewTabCompactHints({
      company: "UNKNOWN",
      resumeSourceMode: null,
      targetConfirmed: false,
      redTeamExecuted: true,
      highRiskCount: 0,
      readinessStatus: "STRENGTHEN_FIRST",
      workflowState: "INTERVIEW_PREP_READY",
    }),
    ["JD \u5f85\u786e\u8ba4", "\u5c1a\u672a\u9009\u62e9\u7b80\u5386", "\u9700\u8981\u8865\u5f3a"],
  );
  // resume_source alone is enough — do not require experiences.length
  assert.equal(
    buildInterviewTabCompactHints({
      company: "Acme",
      resumeSourceMode: "upload",
      targetConfirmed: false,
      redTeamExecuted: true,
      highRiskCount: 0,
      readinessStatus: "READY_TO_APPLY",
      workflowState: "INTERVIEW_PREP_READY",
    })[1],
    "\u7b80\u5386\u5df2\u9009\u62e9",
  );
  assert.equal(parseEvidenceGapCount({
    status: "STRENGTHEN_FIRST",
    blocks: ["Strengthen 15 claim(s) before relying on them in an interview"],
  }), 15);
});

test("empty debrief is rejected; one substantive field is enough", () => {
  assert.match(
    validateMissionDebrief({
      interview_round: "",
      questions_asked: [],
      where_struggled: "",
      interviewer_feedback: "",
    }) || "",
    /请至少填写/,
  );
  assert.equal(
    validateMissionDebrief({
      interview_round: "",
      questions_asked: [],
      where_struggled: "",
      interviewer_feedback: "",
    }) !== null,
    true,
  );
  // notes alone must not be considered — helper does not accept notes
  assert.equal(
    validateMissionDebrief({ interview_round: "一面" }),
    null,
  );
  assert.equal(
    validateMissionDebrief({ questions_asked: ["介绍一个项目"] }),
    null,
  );
  assert.equal(
    validateMissionDebrief({ where_struggled: "系统设计追问" }),
    null,
  );
  assert.equal(
    validateMissionDebrief({ interviewer_feedback: "表达偏散" }),
    null,
  );
});

test("stale API and empty-debrief errors are humanized", () => {
  assert.match(humanizeMissionError("Not Found", "resume_ingest"), /简历上传|不存在|重试/);
  assert.match(humanizeMissionError("Not Found", "generic"), /接口不存在|刷新/);
  assert.match(
    humanizeMissionError("body.update_master: Extra inputs are not permitted"),
    /简历绑定|update_master|重试/,
  );
  assert.match(
    humanizeMissionError("Value error, 请至少填写面试轮次、被问到的问题、卡点或面试官反馈中的一项后再保存。"),
    /请至少填写面试轮次/,
  );
});

test("target_resume_inline_edit builds EDITED patch and status labels", () => {
  assert.equal(
    targetResumeBulletDisplayText({ final_text: null, suggested_text: "建议句" }),
    "建议句",
  );
  assert.equal(
    targetResumeBulletDisplayText({ final_text: "终稿", suggested_text: "建议句" }),
    "终稿",
  );

  const empty = buildTargetResumeInlineEditPatch("   ");
  assert.equal(empty.ok, false);
  if (!empty.ok) assert.match(empty.error, /请输入要点/);

  const built = buildTargetResumeInlineEditPatch("  用户改写的要点  ");
  assert.equal(built.ok, true);
  if (built.ok) {
    assert.deepEqual(built.payload, { final_text: "用户改写的要点", status: "EDITED" });
  }

  assert.equal(targetResumeBulletStatusLabel("EDITED"), "已编辑");
  assert.equal(targetResumeBulletStatusLabel("ACCEPTED"), "已接受");
  assert.equal(targetResumeBulletStatusLabel("REJECTED"), "已拒绝");
  assert.equal(targetResumeBulletStatusLabel("SUGGESTED"), null);
});


test("humanizeMissionError maps unknown source experience to Chinese recovery copy", () => {
  const msg = humanizeMissionError("Target Resume contains an unknown source experience");
  assert.match(msg, /不存在的经历|经历筛选|重试生成/);
  assert.doesNotMatch(msg, /Target Resume contains/i);
});


test("seniorityLabel and locationLabel unify JD enum display", () => {
  assert.equal(seniorityLabel("ENTRY_LEVEL"), "校招");
  assert.equal(seniorityLabel("校招"), "校招");
  assert.equal(seniorityLabel("INTERN"), "实习");
  assert.equal(seniorityLabel("MID"), "中级");
  assert.equal(seniorityLabel("UNKNOWN"), "");
  assert.equal(seniorityLabel(""), "");

  assert.equal(locationLabel("北京市"), "北京");
  assert.equal(locationLabel("北京"), "北京");
  assert.equal(locationLabel("朝阳区"), "朝阳区");
  assert.equal(locationLabel("UNKNOWN"), "");
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


test("looksLikePlaceholderResume detects XX/文职 template", () => {
  assert.equal(
    looksLikePlaceholderResume({
      experiences: [
        {
          title: "文职助理 / 运营助理",
          organization: "XX信息咨询有限公司",
          evidence_text: "（注：部分内容可能由 AI 生成）",
        },
      ],
    }),
    true,
  );
  assert.equal(
    looksLikePlaceholderResume({
      experiences: [
        {
          title: "大连理工大学港口海岸工程竞赛",
          organization: "大连理工大学",
          description: "海洋资源综合利用",
        },
      ],
      education: [{ institution: "大连理工大学", field_of_study: "港口航道" }],
    }),
    false,
  );
});

test("boundResumeSourceSummary shows name/source without UUID", () => {
  const upload = boundResumeSourceSummary({
    resume_source: {
      mode: "upload",
      isolation: "mission_local",
      filename: "潘佳琪-简历.pdf",
      bound_profile_id: "942d35b3-835f-44e9-82b0-193d3ca9d192",
    },
  });
  assert.ok(upload);
  assert.match(upload!.line, /上传 PDF/);
  assert.match(upload!.line, /潘佳琪-简历/);
  assert.match(upload!.line, /仅本岗位/);
  assert.doesNotMatch(upload!.line, /942d35b3/);

  const master = boundResumeSourceSummary(
    { resume_source: { mode: "master", isolation: "shared_master" } },
    { experienceTitle: "港口海岸科研助理" },
  );
  assert.ok(master);
  assert.match(master!.line, /Master 档案/);
  assert.match(master!.line, /港口海岸科研助理/);
  assert.match(master!.line, /共享 Master/);
});

