import type { Route } from "next";
/** Pure mission UX state helpers — driven by server workflow_state. No React. */

export type MissionTab = "role" | "resume" | "proof" | "interview" | "outcome";

/** Maximum number of resume changes shown in the ordinary user flow. */
export const CORE_RESUME_SUGGESTION_LIMIT = 4;

export type CoreResumeNextStep = {
  kind: "resume" | "interview";
  label: string;
};

/** The confirmed resume is the hand-off point to mock interview. */
export function coreResumeNextStep(input: { targetConfirmed: boolean }): CoreResumeNextStep {
  return input.targetConfirmed
    ? { kind: "interview", label: "下一步：进入模拟面试" }
    : { kind: "resume", label: "确认优化建议" };
}

export function coreInterviewCopy(input: { hasFinalResume: boolean; hasQuestions: boolean }): {
  title: string;
  description: string;
  primaryLabel: string;
} {
  return {
    title: "模拟面试",
    description: input.hasFinalResume
      ? input.hasQuestions
        ? "先看问题预览，再逐题回答。每题完成后会记录评分、优点和待改进点。"
        : "先生成一组针对岗位的问题预览，再开始回答。"
      : "先完成简历优化并确认，再开始模拟面试。",
    primaryLabel: input.hasFinalResume ? (input.hasQuestions ? "开始回答第 1 题" : "生成问题预览") : "回到简历优化",
  };
}

export type WorkflowState =
  | "JD_REQUIRED"
  | "JOB_ANALYZING"
  | "ROLE_UNDERSTOOD"
  | "RESUME_REQUIRED"
  | "RESUME_SELECTED"
  | "EXPERIENCE_SELECTION_REQUIRED"
  | "EXPERIENCES_CONFIRMED"
  | "RESUME_STRATEGY_REQUIRED"
  | "RESUME_STRATEGY_CONFIRMED"
  | "TARGET_RESUME_DRAFT"
  | "TARGET_RESUME_CONFIRMED"
  | "STRESS_TEST_REQUIRED"
  | "STRENGTHENING_REQUIRED"
  | "PROOF_IN_PROGRESS"
  | "CLAIM_REEVALUATION_REQUIRED"
  | "RESUME_UPGRADE_AVAILABLE"
  | "INTERVIEW_PREP_READY"
  | "INTERVIEW_IN_PROGRESS"
  | "INTERVIEW_DEBRIEF_READY"
  | "OUTCOME";

export type ResumeSubstep =
  | "source"
  | "selection"
  | "strategy"
  | "target"
  | "stress"
  | "strengthen"
  | "ready";

export type MissionResumeBinding = {
  mode: "master" | "upload" | "paste";
  boundAt: string;
};

export type PrimaryCtaContext = {
  company?: string;
  hasStrategy?: boolean;
  hasSelection?: boolean;
  hasTargetResume?: boolean;
  bulletsDecided?: boolean;
  targetConfirmed?: boolean;
  highRiskCount?: number;
  hasInterviewPack?: boolean;
  modeSelected?: boolean;
  redTeamExecuted?: boolean;
  readinessStatus?: "READY_TO_APPLY" | "STRENGTHEN_FIRST" | "INSUFFICIENT_EVIDENCE" | null;
  evidenceGapCount?: number;
};

const ROLE_STATES: WorkflowState[] = ["JD_REQUIRED", "JOB_ANALYZING", "ROLE_UNDERSTOOD"];
const RESUME_STATES: WorkflowState[] = [
  "RESUME_REQUIRED",
  "RESUME_SELECTED",
  "EXPERIENCE_SELECTION_REQUIRED",
  "EXPERIENCES_CONFIRMED",
  "RESUME_STRATEGY_REQUIRED",
  "RESUME_STRATEGY_CONFIRMED",
  "TARGET_RESUME_DRAFT",
  "TARGET_RESUME_CONFIRMED",
  "STRESS_TEST_REQUIRED",
];
const PROOF_STATES: WorkflowState[] = [
  "STRENGTHENING_REQUIRED",
  "PROOF_IN_PROGRESS",
  "CLAIM_REEVALUATION_REQUIRED",
  "RESUME_UPGRADE_AVAILABLE",
];
const INTERVIEW_STATES: WorkflowState[] = [
  "INTERVIEW_PREP_READY",
  "INTERVIEW_IN_PROGRESS",
  "INTERVIEW_DEBRIEF_READY",
];

export function normalizeWorkflowState(raw: string | null | undefined): WorkflowState {
  const value = String(raw || "").trim().toUpperCase();
  const known: WorkflowState[] = [
    "JD_REQUIRED",
    "JOB_ANALYZING",
    "ROLE_UNDERSTOOD",
    "RESUME_REQUIRED",
    "RESUME_SELECTED",
    "EXPERIENCE_SELECTION_REQUIRED",
    "EXPERIENCES_CONFIRMED",
    "RESUME_STRATEGY_REQUIRED",
    "RESUME_STRATEGY_CONFIRMED",
    "TARGET_RESUME_DRAFT",
    "TARGET_RESUME_CONFIRMED",
    "STRESS_TEST_REQUIRED",
    "STRENGTHENING_REQUIRED",
    "PROOF_IN_PROGRESS",
    "CLAIM_REEVALUATION_REQUIRED",
    "RESUME_UPGRADE_AVAILABLE",
    "INTERVIEW_PREP_READY",
    "INTERVIEW_IN_PROGRESS",
    "INTERVIEW_DEBRIEF_READY",
    "OUTCOME",
  ];
  return (known.includes(value as WorkflowState) ? value : "ROLE_UNDERSTOOD") as WorkflowState;
}

export type DeriveTabContext = {
  resumeSource?: { mode?: string } | null;
  resumeStrategy?: Record<string, unknown> | null;
};

/**
 * Open tab for mission home / deep links.
 * Prefer the first incomplete gate (ROLE → RESUME → …) over a late status label.
 * Never jump to proof/interview/outcome when resume is not bound.
 */
export function deriveTab(
  workflowState: string | null | undefined,
  ctx?: DeriveTabContext,
): MissionTab {
  const state = normalizeWorkflowState(workflowState);
  const resumeBound = Boolean(ctx?.resumeSource && typeof ctx.resumeSource === "object" && ctx.resumeSource.mode);
  const hasStrategy = Boolean(ctx?.resumeStrategy && Object.keys(ctx.resumeStrategy).length > 0);

  if (ROLE_STATES.includes(state)) return "role";

  // Incomplete resume gate wins over INTERVIEW_* / PROOF_* labels
  if (!resumeBound) return "resume";

  if (RESUME_STATES.includes(state)) return "resume";

  // Inconsistent late labels without strategy → stay on resume pipeline
  if (!hasStrategy && (PROOF_STATES.includes(state) || INTERVIEW_STATES.includes(state) || state === "OUTCOME")) {
    return "resume";
  }

  if (PROOF_STATES.includes(state)) return "proof";
  if (INTERVIEW_STATES.includes(state)) return "interview";
  if (state === "OUTCOME") return "outcome";
  return "role";
}

export function deriveResumeSubstep(workflowState: string | null | undefined): ResumeSubstep {
  const state = normalizeWorkflowState(workflowState);
  switch (state) {
    case "RESUME_REQUIRED":
    case "ROLE_UNDERSTOOD":
      return "source";
    case "RESUME_SELECTED":
    case "EXPERIENCE_SELECTION_REQUIRED":
      return "selection";
    case "EXPERIENCES_CONFIRMED":
    case "RESUME_STRATEGY_REQUIRED":
      return "strategy";
    case "RESUME_STRATEGY_CONFIRMED":
    case "TARGET_RESUME_DRAFT":
      return "target";
    case "TARGET_RESUME_CONFIRMED":
      // Stay on target so export + next-stress CTAs remain after confirm.
      return "target";
    case "STRESS_TEST_REQUIRED":
      return "stress";
    case "STRENGTHENING_REQUIRED":
    case "PROOF_IN_PROGRESS":
    case "CLAIM_REEVALUATION_REQUIRED":
      return "strengthen";
    case "INTERVIEW_PREP_READY":
      return "ready";
    default:
      if (PROOF_STATES.includes(state)) return "strengthen";
      if (INTERVIEW_STATES.includes(state)) return "ready";
      return "source";
  }
}

/** @deprecated prefer deriveResumeSubstep(workflow_state) */
export type ResumeFlowInput = {
  resumeBound: boolean;
  experienceCount: number;
  selectionCount: number;
  hasStrategy: boolean;
  hasTargetResume: boolean;
  targetConfirmed: boolean;
  hasRedTeam: boolean;
  highRiskCount: number;
  workflowState?: string | null;
};

export function deriveResumeFlowStep(input: ResumeFlowInput): ResumeSubstep {
  if (input.workflowState) return deriveResumeSubstep(input.workflowState);
  if (!input.resumeBound || input.experienceCount <= 0) return "source";
  if (input.selectionCount <= 0) return "selection";
  if (!input.hasStrategy) return "strategy";
  if (!input.hasTargetResume) return "target";
  if (!input.targetConfirmed) return "target";
  if (!input.hasRedTeam) return "stress";
  if (input.highRiskCount > 0) return "stress";
  return "ready";
}

export function resumeStepTitle(step: ResumeSubstep): string {
  switch (step) {
    case "source":
      return "选择简历";
    case "selection":
      return "经历筛选";
    case "strategy":
      return "简历策略";
    case "target":
      return "目标简历";
    case "stress":
      return "简历压力测试";
    case "strengthen":
      return "需要补强";
    case "ready":
      return "可以进入面试准备";
  }
}

export function nextRoute(
  workflowState: string | null | undefined,
  missionId: string,
  ctx?: DeriveTabContext,
): Route {
  const tab = deriveTab(workflowState, ctx);
  const state = normalizeWorkflowState(workflowState);
  if (state === "ROLE_UNDERSTOOD" || state === "JD_REQUIRED" || state === "JOB_ANALYZING") {
    return `/missions/${encodeURIComponent(missionId)}/role` as Route;
  }
  return `/missions/${encodeURIComponent(missionId)}/${tab}` as Route;
}

export function canAccessTab(workflowState: string | null | undefined, tab: MissionTab): boolean {
  const state = normalizeWorkflowState(workflowState);
  const order: MissionTab[] = ["role", "resume", "proof", "interview", "outcome"];
  const current = deriveTab(state);
  // Always allow role + current + prior tabs; proof/interview/outcome only once resume progressed far enough
  const currentIdx = order.indexOf(current);
  const tabIdx = order.indexOf(tab);
  if (tab === "role") return true;
  if (tab === "resume") return !ROLE_STATES.includes(state) || state === "ROLE_UNDERSTOOD";
  if (tab === "proof") {
    return (
      PROOF_STATES.includes(state) ||
      state === "STRESS_TEST_REQUIRED" ||
      state === "TARGET_RESUME_CONFIRMED" ||
      state === "INTERVIEW_PREP_READY" ||
      INTERVIEW_STATES.includes(state) ||
      state === "OUTCOME"
    );
  }
  if (tab === "interview") {
    return (
      INTERVIEW_STATES.includes(state) ||
      state === "INTERVIEW_PREP_READY" ||
      state === "OUTCOME" ||
      (state === "STRESS_TEST_REQUIRED" && false) // stress alone does not unlock interview
    );
  }
  if (tab === "outcome") return true;
  return tabIdx <= currentIdx;
}

export function primaryCta(workflowState: string | null | undefined, ctx: PrimaryCtaContext = {}): string {
  const state = normalizeWorkflowState(workflowState);
  const company = (ctx.company || "本岗位").trim() || "本岗位";
  switch (state) {
    case "JD_REQUIRED":
    case "JOB_ANALYZING":
      return "分析这个岗位";
    case "ROLE_UNDERSTOOD":
      return "下一步：选择简历";
    case "RESUME_REQUIRED":
      return "用这份简历继续";
    case "RESUME_SELECTED":
    case "EXPERIENCE_SELECTION_REQUIRED":
      return ctx.hasSelection ? "下一步：制定简历策略" : "生成经历筛选并继续";
    case "EXPERIENCES_CONFIRMED":
    case "RESUME_STRATEGY_REQUIRED":
      return ctx.hasStrategy ? "根据这个岗位优化我的简历" : "生成本岗位简历策略";
    case "RESUME_STRATEGY_CONFIRMED":
      return "根据这个岗位优化我的简历";
    case "TARGET_RESUME_DRAFT":
      if (ctx.bulletsDecided && !ctx.targetConfirmed) {
        return `确认 ${company} 目标简历`;
      }
      if (ctx.targetConfirmed) {
        return "下一步：进入模拟面试";
      }
      return `确认 ${company} 目标简历`;
    case "TARGET_RESUME_CONFIRMED":
      return "下一步：进入模拟面试";
    case "STRESS_TEST_REQUIRED":
      return (ctx.highRiskCount ?? 0) > 0 ? "先补最危险的一项" : "进入面试准备";
    case "STRENGTHENING_REQUIRED":
    case "PROOF_IN_PROGRESS":
    case "CLAIM_REEVALUATION_REQUIRED":
      return "继续补强";
    case "RESUME_UPGRADE_AVAILABLE":
      return "根据这个岗位优化我的简历";
    case "INTERVIEW_PREP_READY": {
      if (
        ctx.readinessStatus != null ||
        ctx.redTeamExecuted === false ||
        (ctx.highRiskCount ?? 0) > 0 ||
        ctx.targetConfirmed === false
      ) {
        const gate = resolveInterviewTabCta({
          targetConfirmed: ctx.targetConfirmed !== false,
          redTeamExecuted: Boolean(ctx.redTeamExecuted),
          readinessStatus: ctx.readinessStatus,
          highRiskCount: ctx.highRiskCount ?? 0,
          hasInterviewPack: Boolean(ctx.hasInterviewPack),
          evidenceGapCount: ctx.evidenceGapCount,
          workflowState: state,
        });
        return gate.primaryLabel;
      }
      return ctx.hasInterviewPack ? "开始模拟面试" : "生成面试准备包";
    }
    case "INTERVIEW_IN_PROGRESS":
      return "继续模拟面试";
    case "INTERVIEW_DEBRIEF_READY":
      return "填写面试复盘";
    case "OUTCOME":
      return "查看结果";
    default:
      return "继续准备";
  }
}

/** @deprecated prefer primaryCta(workflow_state, ctx) */
export function resumePrimaryCta(
  step: ResumeSubstep,
  highRiskCount = 0,
  opts?: { hasStrategy?: boolean; hasSelection?: boolean; company?: string; bulletsDecided?: boolean; targetConfirmed?: boolean },
): string {
  switch (step) {
    case "source":
      return "用这份简历继续";
    case "selection":
      return opts?.hasSelection ? "下一步：制定简历策略" : "生成经历筛选并继续";
    case "strategy":
      return opts?.hasStrategy ? "下一步：生成目标简历" : "生成本岗位简历策略";
    case "target":
      if (opts?.targetConfirmed) return "下一步：进入模拟面试";
      return `确认 ${(opts?.company || "本岗位").trim() || "本岗位"} 目标简历`;
    case "stress":
      return highRiskCount > 0 ? "先补最危险的一项" : "进入面试准备";
    case "strengthen":
      return strengthenPrimaryLabel({ hasVisitedProof: false });
    case "ready":
      return "进入面试准备";
  }
}


export const PENDING_CONFIRM_LABEL = "待确认";
export const COMPANY_PENDING_LABEL = "公司待确认";
export const COMPANY_INPUT_PLACEHOLDER = "例如：百度";

export function isUnknownIdentity(value?: string | null): boolean {
  const text = String(value ?? "").trim();
  if (!text) return true;
  const upper = text.toUpperCase();
  if (upper === "UNKNOWN" || upper === "N/A" || upper === "NULL" || upper === "NONE" || upper === "-" || upper === "UNDEFINED") {
    return true;
  }
  if (text === "未知" || text === PENDING_CONFIRM_LABEL) return true;
  return false;
}

/** Form / input value: never prefill UNKNOWN / N/A / NULL as confirmed text. */
export function identityInputValue(value?: string | null): string {
  return isUnknownIdentity(value) ? "" : String(value).trim();
}

/** Stable BE enums → Chinese UI (校招 / 实习 / …). Already-Chinese values pass through. */
const SENIORITY_DISPLAY: Record<string, string> = {
  ENTRY_LEVEL: "校招",
  INTERN: "实习",
  JUNIOR: "初级",
  MID: "中级",
  SENIOR: "高级",
  LEAD: "资深",
};

export function seniorityLabel(value?: string | null): string {
  if (isUnknownIdentity(value)) return "";
  const raw = String(value).trim();
  const key = raw.toUpperCase().replace(/[-\s]+/g, "_");
  return SENIORITY_DISPLAY[key] ?? raw;
}

/** Display location without trailing 市 for plain cities (北京市 → 北京). */
export function locationLabel(value?: string | null): string {
  if (isUnknownIdentity(value)) return "";
  let text = String(value).trim();
  if (
    text.endsWith("市") &&
    text.length >= 3 &&
    !text.includes("区") &&
    !text.includes("县") &&
    !text.includes("州")
  ) {
    text = text.slice(0, -1);
  }
  return text;
}

/** Prefer API display_name; never render UNKNOWN · UNKNOWN in chrome. */
export function missionIdentityLabel(mission: { company?: string | null; role?: string | null; display_name?: string | null }): string {
  const display = String(mission.display_name ?? "").trim();
  const companyUnknown = isUnknownIdentity(mission.company);
  const roleUnknown = isUnknownIdentity(mission.role);
  // Prefer display_name only when company is already confirmed; otherwise surface 公司待确认.
  if (
    display &&
    !companyUnknown &&
    !isUnknownIdentity(display) &&
    !display.toUpperCase().includes("UNKNOWN")
  ) {
    return display;
  }
  const company = companyUnknown ? "" : String(mission.company).trim();
  const role = roleUnknown ? "" : String(mission.role).trim();
  if (company && role) return `${company} · ${role}`;
  if (company) return company;
  if (role) return `${COMPANY_PENDING_LABEL} · ${role}`;
  return COMPANY_PENDING_LABEL;
}

export function missionStatusLabel(status: string): string {
  const map: Record<string, string> = {
    DRAFT: "草稿",
    RESUME_PREP: "准备中",
    STRENGTHENING: "补强中",
    INTERVIEW_PREP: "面试准备中",
    APPLIED: "已投递",
    INTERVIEWING: "面试中",
    COMPLETED: "已完成",
    ARCHIVED: "已归档",
  };
  return map[status] ?? status;
}

export function workflowStateLabel(state: string | null | undefined): string {
  const map: Record<string, string> = {
    JD_REQUIRED: "待粘贴 JD",
    JOB_ANALYZING: "正在分析岗位",
    ROLE_UNDERSTOOD: "岗位已理解",
    RESUME_REQUIRED: "待选择简历",
    RESUME_SELECTED: "简历已选择",
    EXPERIENCE_SELECTION_REQUIRED: "待确认经历筛选",
    EXPERIENCES_CONFIRMED: "经历已确认",
    RESUME_STRATEGY_REQUIRED: "待确认简历策略",
    RESUME_STRATEGY_CONFIRMED: "策略已确认",
    TARGET_RESUME_DRAFT: "目标简历草稿",
    TARGET_RESUME_CONFIRMED: "目标简历已确认",
    STRESS_TEST_REQUIRED: "待完成压力测试",
    STRENGTHENING_REQUIRED: "需要补强",
    PROOF_IN_PROGRESS: "补强进行中",
    CLAIM_REEVALUATION_REQUIRED: "待重评主张",
    RESUME_UPGRADE_AVAILABLE: "可升级简历",
    INTERVIEW_PREP_READY: "可开始面试准备",
    INTERVIEW_IN_PROGRESS: "面试进行中",
    INTERVIEW_DEBRIEF_READY: "待复盘",
    OUTCOME: "结果",
  };
  return map[normalizeWorkflowState(state)] ?? String(state || "");
}


export type MissionDebriefFields = {
  interview_round?: string | null;
  questions_asked?: string[] | null;
  where_struggled?: string | null;
  interviewer_feedback?: string | null;
};

/** Empty debrief guard: require at least one substantive field (notes alone do not count). */
export function validateMissionDebrief(fields: MissionDebriefFields): string | null {
  const roundOk = Boolean(String(fields.interview_round ?? "").trim());
  const questionsOk = (fields.questions_asked ?? []).some((q) => Boolean(String(q ?? "").trim()));
  const struggleOk = Boolean(String(fields.where_struggled ?? "").trim());
  const feedbackOk = Boolean(String(fields.interviewer_feedback ?? "").trim());
  if (roundOk || questionsOk || struggleOk || feedbackOk) return null;
  return "请至少填写面试轮次、被问到的问题、卡点或面试官反馈中的一项后再保存。";
}

export type FriendlyErrorKind = "company_intel" | "jd_analysis" | "resume_parse" | "resume_ingest" | "resume_bind" | "experience_selection" | "generic";


/** Detect placeholder / demo Master resumes (XX公司、文职助理模板、AI 生成注记). */
export function looksLikePlaceholderResume(input: {
  experiences?: Array<{ title?: string | null; organization?: string | null; description?: string | null; evidence_text?: string | null }> | null;
  education?: Array<{ institution?: string | null; field_of_study?: string | null }> | null;
}): boolean {
  const blobs: string[] = [];
  for (const item of input.experiences || []) {
    for (const value of [item?.title, item?.organization, item?.description, item?.evidence_text]) {
      if (typeof value === "string" && value.trim()) blobs.push(value.trim());
    }
  }
  for (const item of input.education || []) {
    for (const value of [item?.institution, item?.field_of_study]) {
      if (typeof value === "string" && value.trim()) blobs.push(value.trim());
    }
  }
  if (!blobs.length) return true;
  const joined = blobs.join("\n");
  const markers = [
    "XX信息咨询",
    "XX交通",
    "XX大学",
    "某某公司",
    "可能由 AI 生成",
    "（注：部分内容可能由 AI 生成）",
    "(注：部分内容可能由 AI 生成)",
  ];
  if (markers.some((m) => joined.includes(m))) return true;
  const hasWenZhi = blobs.some((b) => b.includes("文职助理"));
  const hasXxOrg = blobs.some((b) => /XX[\u4e00-\u9fff]/.test(b) || b.includes("XX信息"));
  if (hasWenZhi && hasXxOrg) return true;
  return false;
}

export type BoundResumeSourceSummary = {
  mode: string;
  modeLabel: string;
  nameLabel: string;
  isolationLabel: string;
  /** One Chinese line for UI; never includes profile UUID. */
  line: string;
};

/** Human-readable bound resume source (name + origin). No UUIDs. */
export function boundResumeSourceSummary(
  mission: {
    resume_source?: {
      mode?: string | null;
      isolation?: string | null;
      filename?: string | null;
      bound_profile_id?: string | null;
      updated_master?: boolean | null;
    } | null;
  } | null,
  options?: { experienceTitle?: string | null; profileLabel?: string | null },
): BoundResumeSourceSummary | null {
  const src = mission?.resume_source;
  if (!src?.mode) return null;
  const mode = String(src.mode);
  const modeLabel =
    mode === "master" ? "Master 档案" : mode === "upload" ? "上传 PDF" : mode === "paste" ? "粘贴文本" : mode;
  const isolation = String(src.isolation || "");
  const isolationLabel =
    isolation === "mission_local"
      ? "仅本岗位"
      : isolation === "shared_master" || mode === "master"
        ? "共享 Master"
        : isolation || "已绑定";
  let nameLabel = "";
  const filename = typeof src.filename === "string" ? src.filename.trim() : "";
  if (filename) {
    nameLabel = filename.replace(/\.pdf$/i, "").trim() || filename;
  } else if (options?.profileLabel?.trim()) {
    nameLabel = options.profileLabel.trim();
  } else if (options?.experienceTitle?.trim()) {
    nameLabel = options.experienceTitle.trim();
  } else if (mode === "master") {
    nameLabel = "Master 简历";
  } else if (mode === "paste") {
    nameLabel = "粘贴简历";
  } else {
    nameLabel = "已绑定简历";
  }
  if (/^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i.test(nameLabel)) {
    nameLabel = mode === "master" ? "Master 简历" : "已绑定简历";
  }
  const line = `${modeLabel} · ${nameLabel}（${isolationLabel}）`;
  return { mode, modeLabel, nameLabel, isolationLabel, line };
}

export function humanizeMissionError(raw: string, kind: FriendlyErrorKind = "generic"): string {
  const text = (raw || "").trim();
  const lower = text.toLowerCase();
  if (
    lower.includes("confirmed profile is required") ||
    (lower.includes("confirmed profile") && lower.includes("proof")) ||
    text.includes("证明补强需要先确认个人档案")
  ) {
    return "证明补强需要先确认个人档案。请在本页上方确认 Profile 后，再点「找出最危险的一项」。";
  }
  if (lower.includes("exceeds the 10 mb") || lower.includes("10 mb limit") || lower.includes("payload too large") || text.includes("413")) {
    return "这份 PDF 超过 10MB，压缩后再上传，或改用「粘贴文本」。";
  }
  if (lower.includes("resume_source") || lower.includes("select a resume") || lower.includes("选择简历")) {
    return "请先选择这份岗位要用的简历，再继续。";
  }
  if (lower.includes("generate a resume strategy before") || lower.includes("resume_strategy_confirmed")) {
    return "还需要先完成本岗位的简历策略，再生成目标简历。";
  }
  if (
    lower.includes("unknown source experience") ||
    text.includes("不存在的经历") ||
    text.includes("未知来源经历")
  ) {
    return "目标简历引用了当前简历来源中不存在的经历。请返回经历筛选核对后，再点「重试生成」。";
  }
  if (lower.includes("confirm experience selection before") || lower.includes("experiences_confirmed")) {
    return "请先确认经历筛选，再制定简历策略。";
  }
  if (lower.includes("target_resume_confirmed") || lower.includes("draft a target resume before")) {
    return "请先确认目标简历，再做压力测试。";
  }
  if (lower.includes("interview_prep_ready") || lower.includes("complete target resume and red team")) {
    return "请先完成压力测试并处理高风险项，再生成面试准备包。";
  }
  if (
    lower.includes("complete an interview stress test") ||
    lower.includes("before creating proof actions") ||
    text.includes("请先完成压力测试，再创建补强证据")
  ) {
    return "请先完成压力测试，再创建补强证据。";
  }
  if (lower.includes("proof actions must target") || text.includes("补强证据必须针对当前主张")) {
    return "补强证据必须针对当前主张。";
  }
  if (
    lower.includes("no extractable text") ||
    lower.includes("could not be extracted") ||
    lower.includes("未能从") ||
    lower.includes("扫描件") ||
    lower.includes("图片型")
  ) {
    return "没能从这份 PDF 提取到文字或经历。若是扫描件/图片型 PDF，请改用「粘贴文本」。";
  }
  if (lower.includes("only pdf") || lower.includes("not a valid pdf") || lower.includes("unsupported media")) {
    return "请上传有效的 PDF 简历。";
  }
  // Stale API / route mismatch (common when uvicorn not restarted after mission-local CoW)
  if (
    lower.includes("extra inputs are not permitted") ||
    lower.includes("extra fields not permitted") ||
    (lower.includes("update_master") && (lower.includes("extra") || lower.includes("not permitted")))
  ) {
    return "简历绑定接口版本不匹配（update_master）。请刷新页面后重试；若仍失败，请让管理员重启 API 后再试。";
  }
  if (
    lower === "not found" ||
    lower.endsWith(": not found") ||
    /\b404\b/.test(lower) ||
    text.trim() === "Not Found"
  ) {
    if (kind === "resume_ingest" || kind === "resume_bind" || kind === "resume_parse") {
      return "简历上传/绑定接口不存在或未就绪。请刷新后重试；若仍失败，请确认 API 已重启到最新版本。";
    }
    return "请求的接口不存在，请刷新页面后重试。";
  }
  if (kind === "experience_selection") {
    if (
      lower.includes("mission intelligence") ||
      lower.includes("unusable response") ||
      lower.includes("schema") ||
      lower.includes("provider") ||
      lower.includes("502") ||
      lower.includes("invalid structured")
    ) {
      return "经历筛选这一步暂时没跑通，请重试。简历来源已经选好，不必换 PDF。";
    }
  }
  if (kind === "resume_bind") {
    if (
      lower.includes("mission intelligence") ||
      lower.includes("unusable response") ||
      lower.includes("schema") ||
      lower.includes("provider") ||
      lower.includes("502") ||
      lower.includes("invalid structured")
    ) {
      return "简历已解析，但绑定到本岗位时失败，请重试。";
    }
  }
  if (
    lower.includes("mission intelligence") ||
    lower.includes("unusable response") ||
    lower.includes("schema") ||
    lower.includes("provider") ||
    lower.includes("502") ||
    lower.includes("invalid structured")
  ) {
    if (kind === "company_intel") {
      return "公司面试情报暂时没有成功加载。我们会先根据岗位 JD 继续分析。";
    }
    if (kind === "jd_analysis") {
      return "岗位分析暂时失败，请重试。";
    }
    if (kind === "resume_parse" || kind === "resume_ingest") {
      return "简历解析暂时失败，请换一份 PDF 或粘贴文本后重试。";
    }
    if (kind === "experience_selection") {
      return "经历筛选这一步暂时没跑通，请重试。简历来源已经选好，不必换 PDF。";
    }
    if (kind === "resume_bind") {
      return "简历绑定暂时失败，请重试。";
    }
    return "模型这一步暂时没跑通，请重试。已保存的内容还在。";
  }
  if (
    text.includes("请至少填写面试轮次") ||
    text.includes("卡点或面试官反馈") ||
    lower.includes("empty debrief") ||
    lower.includes("debrief requires")
  ) {
    return "请至少填写面试轮次、被问到的问题、卡点或面试官反馈中的一项后再保存。";
  }
  if (!text) return "出了点问题，请重试。";
  if (/traceback|pydantic|validationerror|typescript|extra inputs|not permitted/i.test(text)) {
    return "这一步暂时没能完成，请重试。";
  }
  if (kind === "resume_ingest" || kind === "resume_bind" || kind === "resume_parse") {
    // Never surface bare HTTP/framework strings on resume path
    if (/^not found$/i.test(text) || /\b404\b/.test(text) || /^error[:\s]/i.test(text)) {
      return "简历处理失败，请重试。若刚重启过服务，请先刷新页面。";
    }
  }
  return text;
}

export type IntelSourceKind = "REAL_COMPANY" | "RELATED_ROLE" | "GENERIC_FALLBACK" | "SYNTHETIC_DEMO";

export type InterviewIntelLike = {
  skill_id?: string;
  name?: string;
  company_relevance?: string;
  role_relevance?: string;
  competency?: string;
  source_count?: number;
  confidence?: number;
  source_refs?: string[];
  observed_label?: string;
  body?: string;
  provenance?: string;
};

function _foldIntelBlob(item: InterviewIntelLike): string {
  return [
    item.skill_id,
    item.name,
    item.company_relevance,
    item.role_relevance,
    item.observed_label,
    item.provenance,
    ...(item.source_refs ?? []),
  ]
    .map((part) => String(part ?? "").toLowerCase())
    .join(" ");
}

/** Classify interview intel for user-facing provenance (never mark synthetic as real company reports). */
export function classifyIntelSource(item: InterviewIntelLike): IntelSourceKind {
  const blob = _foldIntelBlob(item);
  const skill = String(item.skill_id ?? "").toUpperCase();
  const prov = String(item.provenance ?? "").toUpperCase();
  if (
    skill.startsWith("DEMO_") ||
    blob.includes("synthetic") ||
    blob.includes("demo_only") ||
    blob.includes("demo-only") ||
    prov.includes("SYNTHETIC") ||
    prov.endsWith("_DEMO_ONLY")
  ) {
    return "SYNTHETIC_DEMO";
  }
  const relevance = String(item.company_relevance ?? "").toUpperCase();
  if (relevance === "SAME_COMPANY") return "REAL_COMPANY";
  if (relevance === "ROLE_FAMILY" || relevance === "OTHER_COMPANY" || relevance.includes("RELATED")) {
    return "RELATED_ROLE";
  }
  if (relevance === "GENERIC" || blob.includes("generic") || blob.includes("fallback")) {
    return "GENERIC_FALLBACK";
  }
  if (blob.includes("curated") || blob.includes("niuke") || blob.includes("nowcoder") || blob.includes("牛客")) {
    return "RELATED_ROLE";
  }
  return "GENERIC_FALLBACK";
}

export function intelSourceTypeLabel(kind: IntelSourceKind): string {
  switch (kind) {
    case "REAL_COMPANY":
      return "目标公司真实面经";
    case "RELATED_ROLE":
      return "相近岗位真实面经";
    case "GENERIC_FALLBACK":
      return "通用面经";
    case "SYNTHETIC_DEMO":
      return "合成演示";
  }
}

export function summarizeIntelCoverage(items: InterviewIntelLike[]): {
  curatedCompany: number;
  relatedRole: number;
  generic: number;
  synthetic: number;
  /** @deprecated alias of relatedRole — keep for older callers */
  otherCompany: number;
  /** @deprecated generic + synthetic — keep for older callers */
  fallback: number;
} {
  let curatedCompany = 0;
  let relatedRole = 0;
  let generic = 0;
  let synthetic = 0;
  for (const item of items) {
    const kind = classifyIntelSource(item);
    if (kind === "REAL_COMPANY") curatedCompany += 1;
    else if (kind === "RELATED_ROLE") relatedRole += 1;
    else if (kind === "SYNTHETIC_DEMO") synthetic += 1;
    else generic += 1;
  }
  return {
    curatedCompany,
    relatedRole,
    generic,
    synthetic,
    otherCompany: relatedRole,
    fallback: generic + synthetic,
  };
}

/** Partition intel into four provenance layers for UI (synthetic stays separate). */
export function partitionIntelBySource(items: InterviewIntelLike[]): {
  realCompany: InterviewIntelLike[];
  relatedRole: InterviewIntelLike[];
  generic: InterviewIntelLike[];
  synthetic: InterviewIntelLike[];
} {
  const realCompany: InterviewIntelLike[] = [];
  const relatedRole: InterviewIntelLike[] = [];
  const generic: InterviewIntelLike[] = [];
  const synthetic: InterviewIntelLike[] = [];
  for (const item of items) {
    const kind = classifyIntelSource(item);
    if (kind === "REAL_COMPANY") realCompany.push(item);
    else if (kind === "RELATED_ROLE") relatedRole.push(item);
    else if (kind === "SYNTHETIC_DEMO") synthetic.push(item);
    else generic.push(item);
  }
  return { realCompany, relatedRole, generic, synthetic };
}

type ParsedRequirement = { id?: string; text?: string; evidence_text?: string };

function _requirementMap(parsedJd: Record<string, unknown> | null | undefined): Map<string, string> {
  const map = new Map<string, string>();
  if (!parsedJd || typeof parsedJd !== "object") return map;
  const buckets = [parsedJd.requirements, parsedJd.preferred_requirements, parsedJd.responsibilities];
  for (const bucket of buckets) {
    if (!Array.isArray(bucket)) continue;
    for (const raw of bucket) {
      if (!raw || typeof raw !== "object") continue;
      const row = raw as ParsedRequirement;
      const id = String(row.id ?? "").trim();
      const evidence = String(row.evidence_text ?? row.text ?? "").trim();
      if (id && evidence) map.set(id, evidence);
    }
  }
  return map;
}

/** Resolve capability evidence_refs to JD verbatim snippets. */
export function resolveJdEvidenceTexts(
  refs: string[] | undefined,
  parsedJd?: Record<string, unknown> | null,
  _jdEvidenceRefs?: string[] | null,
): string[] {
  const map = _requirementMap(parsedJd);
  const out: string[] = [];
  const seen = new Set<string>();
  for (const ref of refs ?? []) {
    const key = String(ref ?? "").trim();
    if (!key) continue;
    let resolved = map.get(key) ?? "";
    if (!resolved && key.length >= 8 && !/^(req_|pref_|q\d|p\d)/i.test(key)) {
      resolved = key;
    }
    if (!resolved || seen.has(resolved)) continue;
    seen.add(resolved);
    out.push(resolved);
  }
  return out.slice(0, 4);
}

function capabilityMatchTokens(name: string): string[] {
  const raw = name.trim().toLowerCase();
  if (!raw) return [];
  const tokens = new Set<string>();
  for (const part of raw.split(/[\s/·,，、与和的及]+/)) {
    if (part.length >= 2) tokens.add(part);
  }
  const cjk = raw.match(/[\u4e00-\u9fff]{2,}/g) ?? [];
  for (const chunk of cjk) {
    tokens.add(chunk);
    tokens.add(chunk.slice(0, 2));
    if (chunk.length >= 4) tokens.add(chunk.slice(0, 4));
    // Prefer meaningful domains like 大模型 / 评测 / 产品
    for (let size = 2; size <= Math.min(4, chunk.length); size += 1) {
      tokens.add(chunk.slice(0, size));
    }
  }
  return Array.from(tokens);
}

export function matchIntelForCapability(
  capabilityName: string,
  items: InterviewIntelLike[],
): InterviewIntelLike | null {
  const needle = capabilityName.trim().toLowerCase();
  if (!needle || !items.length) return null;
  const tokens = capabilityMatchTokens(needle);
  let best: InterviewIntelLike | null = null;
  let bestScore = 0;
  for (const item of items) {
    const hay = `${item.name ?? ""} ${item.competency ?? ""} ${item.body ?? ""}`.toLowerCase();
    let score = 0;
    if (hay.includes(needle) || needle.includes(String(item.competency ?? "").toLowerCase())) score += 3;
    for (const token of tokens) {
      if (token.length >= 2 && hay.includes(token)) score += token.length >= 4 ? 2 : 1;
    }
    if (score > bestScore) {
      bestScore = score;
      best = item;
    }
  }
  return bestScore > 0 ? best : null;
}

export type CapabilityEvidenceView = {
  jdEvidence: string[];
  intelName: string;
  sourceType: string;
  sourceKind: IntelSourceKind | null;
  confidenceLabel: string;
  pendingConfirm: boolean;
  pendingReason: string;
};

/** Build user-facing evidence trail for a What Matters capability row. */
export function buildCapabilityEvidenceView(input: {
  capability: { name?: unknown; why?: unknown; evidence_refs?: unknown };
  parsedJd?: Record<string, unknown> | null;
  whatMatters?: Record<string, unknown> | null;
  interviewIntel?: InterviewIntelLike[] | null;
}): CapabilityEvidenceView {
  const cap = input.capability ?? {};
  const refs = Array.isArray(cap.evidence_refs)
    ? cap.evidence_refs.map((item) => String(item ?? "").trim()).filter(Boolean)
    : [];
  const jdEvidenceRefs = Array.isArray(input.whatMatters?.jd_evidence_refs)
    ? (input.whatMatters?.jd_evidence_refs as unknown[]).map((item) => String(item ?? "").trim())
    : [];
  const jdEvidence = resolveJdEvidenceTexts(refs, input.parsedJd, jdEvidenceRefs);
  const matched = matchIntelForCapability(String(cap.name ?? ""), input.interviewIntel ?? []);
  const sourceKind = matched ? classifyIntelSource(matched) : null;
  const wmConfidence = Number(input.whatMatters?.confidence);
  const intelConfidence = matched && typeof matched.confidence === "number" ? matched.confidence : NaN;
  const confidence = Number.isFinite(intelConfidence)
    ? intelConfidence
    : Number.isFinite(wmConfidence)
      ? wmConfidence
      : NaN;
  const pendingConfirm =
    jdEvidence.length === 0 || !matched || sourceKind === "SYNTHETIC_DEMO" || sourceKind === "GENERIC_FALLBACK";
  let pendingReason = "";
  if (jdEvidence.length === 0 && !matched) pendingReason = "模型推断 / 待确认";
  else if (jdEvidence.length === 0) pendingReason = "缺 JD 原文证据 / 待确认";
  else if (!matched) pendingReason = "面经未对齐 / 待确认";
  else if (sourceKind === "SYNTHETIC_DEMO") pendingReason = "合成演示，非真实公司面经";
  else if (sourceKind === "GENERIC_FALLBACK") pendingReason = "通用面经 / 待确认";

  return {
    jdEvidence,
    intelName: matched?.name ? String(matched.name) : "",
    sourceType: sourceKind ? intelSourceTypeLabel(sourceKind) : "模型推断",
    sourceKind,
    confidenceLabel: Number.isFinite(confidence) ? `${Math.round(confidence * 100)}%` : PENDING_CONFIRM_LABEL,
    pendingConfirm,
    pendingReason,
  };
}

/** JD requirement / What Matters evidence level for coverage UI. */
export type JdRequirementEvidenceLevel = "直接证据" | "部分证据" | "没有证据" | "待用户确认";

export type JdRequirementEvidenceRow = {
  id: string;
  label: string;
  level: JdRequirementEvidenceLevel;
  evidence: CapabilityEvidenceView;
};

export type JdRequirementEvidenceCoverage = {
  total: number;
  direct: number;
  partial: number;
  none: number;
  pendingConfirm: number;
  /** direct/total*100; null when total===0 (honest empty, not fake 100%). */
  coveragePct: number | null;
  rows: JdRequirementEvidenceRow[];
};

/** Map a capability evidence view to one of four Chinese coverage labels. */
export function classifyCapabilityEvidenceLevel(view: CapabilityEvidenceView): JdRequirementEvidenceLevel {
  const hasJd = view.jdEvidence.length > 0;
  const kind = view.sourceKind;
  const hasStrong = kind === "REAL_COMPANY" || kind === "RELATED_ROLE";
  if (hasJd && hasStrong) return "直接证据";
  if (hasJd || hasStrong) return "部分证据";
  if (!hasJd && !view.intelName) return "没有证据";
  return "待用户确认";
}

function _capabilityLabel(cap: { name?: unknown; text?: unknown; id?: unknown }, index: number): string {
  const name = String(cap?.name ?? "").trim();
  if (name) return name;
  const text = String(cap?.text ?? "").trim();
  if (text) return text.length > 48 ? `${text.slice(0, 48)}…` : text;
  const id = String(cap?.id ?? "").trim();
  if (id) return id;
  return `要求 ${index + 1}`;
}

/**
 * Build JD requirement evidence coverage for role / What Matters.
 * Prefers what_matters.core_capabilities; falls back to parsed_jd requirements.
 * coveragePct = direct/total only; empty input → null (no fake 100%).
 */
export function buildJdRequirementEvidenceCoverage(input: {
  whatMatters?: Record<string, unknown> | null;
  parsedJd?: Record<string, unknown> | null;
  interviewIntel?: InterviewIntelLike[] | null;
}): JdRequirementEvidenceCoverage {
  const what = input.whatMatters && typeof input.whatMatters === "object" ? input.whatMatters : {};
  const rawCaps = Array.isArray(what.core_capabilities) ? (what.core_capabilities as unknown[]) : [];
  let caps: Array<{ name?: unknown; why?: unknown; evidence_refs?: unknown; text?: unknown; id?: unknown }> = [];
  if (rawCaps.length) {
    caps = rawCaps
      .filter((row) => row && typeof row === "object")
      .map((row) => row as { name?: unknown; why?: unknown; evidence_refs?: unknown; text?: unknown; id?: unknown });
  } else if (input.parsedJd && typeof input.parsedJd === "object") {
    const buckets = [input.parsedJd.requirements, input.parsedJd.preferred_requirements];
    for (const bucket of buckets) {
      if (!Array.isArray(bucket)) continue;
      for (const raw of bucket) {
        if (!raw || typeof raw !== "object") continue;
        const row = raw as { id?: unknown; text?: unknown; evidence_text?: unknown };
        caps.push({
          id: row.id,
          name: row.text ?? row.evidence_text,
          text: row.text ?? row.evidence_text,
          evidence_refs: row.id ? [String(row.id)] : [],
        });
      }
    }
  }

  const rows: JdRequirementEvidenceRow[] = caps.slice(0, 12).map((cap, index) => {
    const evidence = buildCapabilityEvidenceView({
      capability: cap,
      parsedJd: input.parsedJd,
      whatMatters: what,
      interviewIntel: input.interviewIntel ?? [],
    });
    const level = classifyCapabilityEvidenceLevel(evidence);
    return {
      id: String(cap.id ?? `${_capabilityLabel(cap, index)}-${index}`),
      label: _capabilityLabel(cap, index),
      level,
      evidence,
    };
  });

  let direct = 0;
  let partial = 0;
  let none = 0;
  let pendingConfirm = 0;
  for (const row of rows) {
    if (row.level === "直接证据") direct += 1;
    else if (row.level === "部分证据") partial += 1;
    else if (row.level === "没有证据") none += 1;
    else pendingConfirm += 1;
  }
  const total = rows.length;
  return {
    total,
    direct,
    partial,
    none,
    pendingConfirm,
    coveragePct: total === 0 ? null : Math.round((direct / total) * 100),
    rows,
  };
}

export function jdRequirementEvidenceLevelLabel(level: JdRequirementEvidenceLevel): string {
  return level;
}

export function targetResumeBulletDisplayText(bullet: {
  final_text?: string | null;
  suggested_text?: string | null;
}): string {
  return String(bullet.final_text || bullet.suggested_text || "");
}

export function buildTargetResumeInlineEditPatch(
  draft: string,
): { ok: true; payload: { final_text: string; status: "EDITED" } } | { ok: false; error: string } {
  const final_text = draft.trim();
  if (!final_text) {
    return { ok: false, error: "请输入要点内容后再保存。" };
  }
  return { ok: true, payload: { final_text, status: "EDITED" } };
}

export function targetResumeBulletStatusLabel(status: string): string | null {
  if (status === "EDITED") return "已编辑";
  if (status === "ACCEPTED") return "已接受";
  if (status === "REJECTED") return "已拒绝";
  return null;
}

export function targetResumeConfirmed(bullets: Array<{ status: string }>): boolean {
  // Default-accept: any non-empty draft is confirmable; REJECTED omitted at export.
  if (!bullets.length) return false;
  return true;
}

export function countHighRiskFindings(findings: Array<Record<string, unknown>>): number {
  return findings.filter((item) => {
    const level = String(item.risk_level ?? item.severity ?? item.level ?? "").toUpperCase();
    return level.includes("HIGH") || level.includes("高");
  }).length;
}

export function countMediumRiskFindings(findings: Array<Record<string, unknown>>): number {
  return findings.filter((item) => {
    const level = String(item.risk_level ?? item.severity ?? item.level ?? "").toUpperCase();
    return level.includes("MEDIUM") || level.includes("中");
  }).length;
}

export type ReadinessStatus = "READY_TO_APPLY" | "STRENGTHEN_FIRST" | "INSUFFICIENT_EVIDENCE";

/** Red-team GET may return {mission_id, findings:[]} with no report — that is NOT executed. */
export type RedTeamSnapshot = {
  id?: string | null;
  created_at?: string | null;
  mission_id?: string | null;
  findings?: Array<Record<string, unknown>> | null;
  /** Alternate / nested shapes from GET or POST. */
  report_id?: string | null;
  report?: {
    id?: string | null;
    created_at?: string | null;
    findings?: Array<Record<string, unknown>> | null;
  } | null;
};

/** Claim fields needed to mirror API start_interview_session gate (2d8878019). */
export type ClaimInterviewLite = {
  id?: string | null;
  readiness_status?: string | null;
  evidence_refs?: unknown;
};

/**
 * Same semantics as proof_service.start_interview_session:
 * bare UNSUPPORTED (no evidence_refs) is a strengthen gap, not mock-interviewable.
 */
export function isInterviewableClaim(claim: ClaimInterviewLite | null | undefined): boolean {
  if (!claim || typeof claim !== "object") return false;
  const readiness = String(claim.readiness_status ?? "").trim().toUpperCase();
  // Align with API write-side: literal "None"/"null"/"undefined"/blank are not evidence.
  const refs = Array.isArray(claim.evidence_refs)
    ? claim.evidence_refs.filter((item) => {
        if (item == null) return false;
        const s = String(item).trim();
        if (!s) return false;
        const lower = s.toLowerCase();
        if (lower === "none" || lower === "null" || lower === "undefined") return false;
        return true;
      })
    : [];
  if (readiness === "UNSUPPORTED" && refs.length === 0) return false;
  // Need a usable resume-claim id to open claim-session.
  if (claim.id != null && !String(claim.id).trim()) return false;
  return Boolean(readiness);
}

/** True when at least one claim can start mock interview (API-aligned). Empty list => false. */
export function hasInterviewableClaim(
  claims: Array<ClaimInterviewLite> | null | undefined,
): boolean {
  if (!Array.isArray(claims) || claims.length === 0) return false;
  return claims.some((claim) => isInterviewableClaim(claim));
}

export type ProofNextStep = {
  kind: "resume" | "strengthen" | "interview";
  label: string;
};

/**
 * Keep the proof page from ending in a dead end. Only a READY_TO_APPLY mission
 * with an interviewable claim can hand the user to the interview lane;
 * strengthening readiness keeps the user in补强 until the evidence is rechecked.
 */
export function resolveProofNextStep(input: {
  targetConfirmed: boolean;
  readinessStatus?: string | null;
  claims?: Array<ClaimInterviewLite> | null;
  proofActions?: Array<{ status?: string | null }> | null;
}): ProofNextStep {
  const readiness = String(input.readinessStatus ?? "").trim().toUpperCase();
  if (!input.targetConfirmed) {
    return { kind: "resume", label: "下一步：确认目标简历" };
  }
  const pendingAction = (input.proofActions ?? []).some((action) => {
    const status = String(action.status ?? "").trim().toUpperCase();
    return status !== "COMPLETED" && status !== "SKIPPED";
  });
  if (pendingAction) {
    if (readiness === "READY_TO_APPLY" && hasInterviewableClaim(input.claims ?? [])) {
      return { kind: "interview", label: "下一步：进入面试拷问" };
    }
    return { kind: "strengthen", label: "继续补强" };
  }
  if (readiness === "STRENGTHEN_FIRST" || readiness === "INSUFFICIENT_EVIDENCE") {
    return { kind: "strengthen", label: "继续补强" };
  }
  if (hasInterviewableClaim(input.claims ?? [])) {
    return { kind: "interview", label: "下一步：进入面试拷问" };
  }
  return { kind: "strengthen", label: "继续补强" };
}

export type InterviewGateInput = {
  targetConfirmed: boolean;
  redTeamExecuted: boolean;
  /**
   * True while GET red-team has not settled. Must hide empty-report / start CTA
   * and show syncing copy instead of treating initial {findings:[]} as no report.
   */
  redTeamLoading?: boolean;
  readinessStatus?: ReadinessStatus | string | null;
  highRiskCount: number;
  hasInterviewPack: boolean;
  /** Parsed from readiness.blocks (e.g. Strengthen N claim(s)). */
  evidenceGapCount?: number;
  workflowState?: string | null;
  /**
   * At least one interviewable resume-claim (not bare UNSUPPORTED).
   * Omit / undefined keeps legacy callers green; mission-page always passes an explicit boolean.
   */
  hasInterviewableClaim?: boolean;
  /** Opened 补强 already (workflow lane or localStorage). */
  hasVisitedProof?: boolean;
};

/**
 * Normalize GET/POST red-team payloads so every surface sees the same report identity.
 * Empty findings with id/created_at still count as executed.
 */
export function normalizeRedTeamReport(
  redTeam: RedTeamSnapshot | null | undefined,
): {
  id?: string;
  created_at?: string;
  mission_id?: string;
  findings: Array<Record<string, unknown>>;
} {
  if (!redTeam || typeof redTeam !== "object") {
    return { findings: [] };
  }
  const nested = redTeam.report && typeof redTeam.report === "object" ? redTeam.report : null;
  const idRaw = redTeam.id ?? redTeam.report_id ?? nested?.id;
  const createdRaw = redTeam.created_at ?? nested?.created_at;
  const findingsRaw = Array.isArray(redTeam.findings)
    ? redTeam.findings
    : Array.isArray(nested?.findings)
      ? nested!.findings!
      : [];
  const id = idRaw != null && String(idRaw).trim() ? String(idRaw) : undefined;
  const created_at = createdRaw != null && String(createdRaw).trim() ? String(createdRaw) : undefined;
  const mission_id = redTeam.mission_id != null ? String(redTeam.mission_id) : undefined;
  return {
    id,
    created_at,
    mission_id,
    findings: findingsRaw.filter(
      (item): item is Record<string, unknown> => Boolean(item && typeof item === "object"),
    ),
  };
}

/**
 * Report exists (id / created_at) OR findings present after a run.
 * Empty findings with a report still count as executed.
 * Missing report (GET often returns {mission_id, findings:[]} with no id) must NEVER count as ready.
 * All surfaces: Boolean(report?.id || report?.created_at || findings.length)
 */
export function isRedTeamExecuted(redTeam: RedTeamSnapshot | null | undefined): boolean {
  const report = normalizeRedTeamReport(redTeam);
  return Boolean(report.id || report.created_at || report.findings.length > 0);
}

/** Resume-tab stress-test status line — never say「还没有」when a report already exists. */
export function redTeamResultCopy(input: {
  executed: boolean;
  findingsCount: number;
  highRiskCount?: number;
  loading?: boolean;
}): string {
  if (input.loading) {
    return "正在同步压力测试结果…";
  }
  if (!input.executed) {
    return "还没有压力测试结果。点击下方按钮开始检查。";
  }
  if (input.findingsCount <= 0) {
    return "压力测试已完成，暂未发现结构化风险项。";
  }
  const high = input.highRiskCount ?? 0;
  if (high > 0) {
    return `发现 ${high} 项需要补强的高风险追问`;
  }
  return `发现 ${input.findingsCount} 项追问风险`;
}

/** Parse "还有 N 项" from readiness blocks; falls back to block count when strengthening. */
export function parseEvidenceGapCount(
  readiness: { status?: string | null; blocks?: string[] | null } | null | undefined,
): number {
  if (!readiness) return 0;
  let total = 0;
  for (const block of readiness.blocks ?? []) {
    const text = String(block ?? "");
    const claim = text.match(/Strengthen\s+(\d+)\s+claim/i);
    if (claim) {
      total += Number(claim[1]);
      continue;
    }
    const high = text.match(/Resolve\s+(\d+)\s+high-risk/i);
    if (high) {
      total += Number(high[1]);
      continue;
    }
    const zh = text.match(/(\d+)\s*(?:项|个).*(?:证据|主张|风险)/);
    if (zh) {
      total += Number(zh[1]);
    }
  }
  if (total > 0) return total;
  const status = String(readiness.status ?? "").toUpperCase();
  if (status === "STRENGTHEN_FIRST" || status === "INSUFFICIENT_EVIDENCE") {
    return Math.max(1, (readiness.blocks ?? []).length);
  }
  return 0;
}

export function canGenerateInterviewPack(
  input: Pick<InterviewGateInput, "targetConfirmed" | "redTeamExecuted">,
): boolean {
  return Boolean(input.targetConfirmed && input.redTeamExecuted);
}

/**
 * Full mission mock (完整模拟): READY_TO_APPLY + target + red-team + pack + no high risk
 * + hasInterviewableClaim !== false. INTERVIEW_PREP_READY alone must NEVER unlock.
 */
export function canStartFullMissionMock(input: InterviewGateInput): boolean {
  if (!input.targetConfirmed) return false;
  if (!input.redTeamExecuted) return false;
  if (input.redTeamLoading) return false;
  if (String(input.readinessStatus ?? "").toUpperCase() !== "READY_TO_APPLY") return false;
  if ((input.highRiskCount ?? 0) > 0) return false;
  if (!input.hasInterviewPack) return false;
  // Explicit false (mission proof snapshot) blocks; omit/undefined = legacy callers.
  if (input.hasInterviewableClaim === false) return false;
  return true;
}

/**
 * Single-claim mock (单主张拷问): lighter than full mission mock.
 * Allows STRENGTHEN_FIRST / INSUFFICIENT_EVIDENCE so users can drill one interviewable claim
 * while still strengthening. Still requires target confirmed + red-team settled + interviewable claim.
 * Does NOT require READY_TO_APPLY, pack, or zero high-risk.
 */
export function canStartClaimMock(input: InterviewGateInput): boolean {
  if (!input.targetConfirmed) return false;
  if (!input.redTeamExecuted) return false;
  if (input.redTeamLoading) return false;
  if (input.hasInterviewableClaim === false) return false;
  return true;
}

/** @deprecated Prefer canStartFullMissionMock; kept as alias for backward compat. */
export function canStartInterview(input: InterviewGateInput): boolean {
  return canStartFullMissionMock(input);
}

/** localStorage key: user opened 补强 for this mission. */
export function proofVisitedStorageKey(missionId: string): string {
  return `career-os:visited-proof:${encodeURIComponent(String(missionId || "").trim())}`;
}

export function markProofVisited(missionId: string): void {
  const id = String(missionId || "").trim();
  if (!id || typeof window === "undefined") return;
  try {
    window.localStorage.setItem(proofVisitedStorageKey(id), "1");
  } catch {
    /* ignore quota / private mode */
  }
}

export function readProofVisited(missionId: string): boolean {
  const id = String(missionId || "").trim();
  if (!id || typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(proofVisitedStorageKey(id)) === "1";
  } catch {
    return false;
  }
}

/** Workflow already in proof/strengthen lane => return visit. */
export function hasVisitedProofWorkflow(workflowState?: string | null): boolean {
  const ws = normalizeWorkflowState(workflowState);
  return (
    ws === "STRENGTHENING_REQUIRED" ||
    ws === "PROOF_IN_PROGRESS" ||
    ws === "CLAIM_REEVALUATION_REQUIRED"
  );
}

/** Combined: workflow proof lane OR per-mission localStorage flag. */
export function hasVisitedProofForMission(
  missionId: string | null | undefined,
  workflowState?: string | null,
): boolean {
  if (hasVisitedProofWorkflow(workflowState)) return true;
  if (missionId) return readProofVisited(missionId);
  return false;
}

/** First visit => 进入补强; returning => 返回补强. */
export function strengthenPrimaryLabel(input: { hasVisitedProof?: boolean } = {}): string {
  return input.hasVisitedProof ? "返回补强" : "下一步：进入补强";
}

/** Humanize claim/action progress for 补强 list (no raw WEAK_EVIDENCE in UI). */
export function claimStrengthenProgressLabel(input: {
  readinessStatus?: string | null;
  actionStatuses?: string[] | null;
  hasArtifact?: boolean;
  markedNoExperience?: boolean;
}): string {
  if (input.markedNoExperience) return "已标记无此经历";
  const actions = (input.actionStatuses ?? []).map((x) => String(x || "").toUpperCase());
  if (actions.some((x) => x.includes("REEVAL") || x === "RE_EVALUATING")) return "重新评估中";
  if (input.hasArtifact || actions.some((x) => x.includes("SUBMIT") || x === "DONE" || x === "COMPLETED")) {
    return "已提交材料";
  }
  const readiness = String(input.readinessStatus ?? "").toUpperCase();
  if (readiness === "SUPPORTED" || readiness === "DEFENDABLE") return "已补强";
  if (readiness === "WEAK_EVIDENCE") return "仍不足";
  if (readiness === "UNSUPPORTED") return "待处理";
  if (actions.length > 0) return "待处理";
  return "待处理";
}

export function proofActionStatusLabel(status?: string | null): string {
  switch (String(status ?? "").trim().toUpperCase()) {
    case "PROPOSED": return "待填写";
    case "COMPLETED": return "已提交";
    case "SKIPPED": return "已跳过";
    case "SUBMITTED": return "待评估";
    default: return "待处理";
  }
}

export function hasCompletedNoExperienceAction(
  actions: Array<{ status?: string | null; artifact_type?: string | null; title?: string | null }> | null | undefined,
): boolean {
  return (actions ?? []).some((action) =>
    String(action.status ?? "").toUpperCase() === "COMPLETED" &&
    /no[_-]?experience|无此经历|没有这段/i.test(`${action.artifact_type ?? ""} ${action.title ?? ""}`),
  );
}

export type InterviewTabCta = {
  /** Alias of canStartFullMissionMock (backward compat). */
  canStartInterview: boolean;
  canStartFullMissionMock: boolean;
  canStartClaimMock: boolean;
  canGeneratePack: boolean;
  /** Hide full-mission mock CTA (claim mock may still show via canStartClaimMock). */
  hideMock: boolean;
  primaryKind: "mock" | "generate_pack" | "strengthen" | "red_team" | "confirm_resume" | "syncing";
  primaryLabel: string;
  secondaryLabel?: string;
  statusMessage: string;
  evidenceGapCount: number;
};


/** True only when API advance(event=strengthen) is a valid transition. */
export function canAdvanceStrengthenEvent(workflowState?: string | null): boolean {
  const ws = normalizeWorkflowState(workflowState);
  return ws === "STRESS_TEST_REQUIRED" || ws === "CLAIM_REEVALUATION_REQUIRED";
}

/** Interview-tab CTAs — single source consumed by mission-page. */
export function resolveInterviewTabCta(input: InterviewGateInput): InterviewTabCta {
  const readiness = String(input.readinessStatus ?? "").toUpperCase();
  const gaps = input.evidenceGapCount ?? 0;
  const strengthen = readiness === "STRENGTHEN_FIRST" || readiness === "INSUFFICIENT_EVIDENCE";
  const fullMock = canStartFullMissionMock(input);
  const claimMock = canStartClaimMock(input);
  const mockFlags = {
    canStartInterview: fullMock,
    canStartFullMissionMock: fullMock,
    canStartClaimMock: claimMock,
  };

  if (!input.targetConfirmed) {
    return {
      ...mockFlags,
      canGeneratePack: false,
      hideMock: true,
      primaryKind: "confirm_resume",
      primaryLabel: "回到简历步骤",
      statusMessage: "请先完成目标简历确认，并在压力测试里处理完高风险追问点。通过后，这里会开放「生成面试准备包」和「开始完整模拟面试」。",
      evidenceGapCount: gaps,
    };
  }

  if (input.redTeamLoading) {
    return {
      ...mockFlags,
      canGeneratePack: false,
      hideMock: true,
      primaryKind: "syncing",
      primaryLabel: "正在同步压力测试结果…",
      statusMessage: "正在同步压力测试结果…",
      evidenceGapCount: gaps,
    };
  }

  if (!input.redTeamExecuted) {
    return {
      ...mockFlags,
      canGeneratePack: false,
      hideMock: true,
      primaryKind: "red_team",
      primaryLabel: "开始压力测试",
      statusMessage: "还没有压力测试报告。即使工作流显示「可开始面试准备」，也请先完成压力测试后再生成准备包或模拟面试。",
      evidenceGapCount: gaps,
    };
  }

  if (strengthen) {
    const n = gaps > 0 ? gaps : 1;
    return {
      ...mockFlags,
      canGeneratePack: false,
      hideMock: true,
      primaryKind: "strengthen",
      primaryLabel: "下一步：进入补强",
      secondaryLabel: claimMock ? "开始单主张拷问" : undefined,
      statusMessage: claimMock
        ? `还有 ${n} 项证据需要补强。全岗完整模拟暂不可用，可先对已有可追问主张做单主张拷问。`
        : `还有 ${n} 项证据需要补强`,
      evidenceGapCount: n,
    };
  }

  if ((input.highRiskCount ?? 0) > 0) {
    const n = input.highRiskCount ?? 0;
    return {
      ...mockFlags,
      canGeneratePack: false,
      hideMock: true,
      primaryKind: "strengthen",
      primaryLabel: "下一步：进入补强",
      secondaryLabel: claimMock ? "开始单主张拷问" : undefined,
      statusMessage: claimMock
        ? `还有 ${n} 个高风险点需要处理。完整模拟暂不可用，可先做单主张拷问。`
        : `还有 ${n} 个高风险点需要处理`,
      evidenceGapCount: n,
    };
  }

  if (!input.hasInterviewPack) {
    return {
      ...mockFlags,
      canGeneratePack: true,
      hideMock: true,
      primaryKind: "generate_pack",
      primaryLabel: "生成面试准备包",
      secondaryLabel: claimMock ? "开始单主张拷问" : undefined,
      statusMessage: claimMock
        ? "可以生成面试准备包；生成后即可开始完整模拟。也可先做单主张拷问。"
        : "可以生成面试准备包；生成后即可开始完整模拟面试。",
      evidenceGapCount: 0,
    };
  }

  // Align with API 2d8878019: claims exist but none interviewable (bare UNSUPPORTED / empty) → hide mock.
  if (input.hasInterviewableClaim === false) {
    return {
      ...mockFlags,
      canGeneratePack: true,
      hideMock: true,
      primaryKind: "strengthen",
      primaryLabel: "下一步：进入补强",
      statusMessage: "尚无可面试主张，请先补证据再模拟。当前主张多为无履历证据的缺口，不能直接开始模拟面试。",
      evidenceGapCount: gaps > 0 ? gaps : 1,
    };
  }

  return {
    ...mockFlags,
    canGeneratePack: true,
    hideMock: !fullMock,
    primaryKind: fullMock ? "mock" : "generate_pack",
    primaryLabel: fullMock ? "开始完整模拟面试" : "生成面试准备包",
    secondaryLabel: fullMock ? "刷新面试准备包" : claimMock ? "开始单主张拷问" : undefined,
    statusMessage: fullMock
      ? "已具备完整模拟面试条件。"
      : "请先完成目标简历确认，并在压力测试里处理完高风险追问点。",
    evidenceGapCount: 0,
  };
}

/**
 * Interview-tab compactHints: use resume_source / target / red_team / readiness,
 * never experiences.length alone, and never let INTERVIEW_PREP_READY contradict body.
 */
export function buildInterviewTabCompactHints(input: {
  company?: string | null;
  resumeSourceMode?: string | null;
  targetConfirmed: boolean;
  redTeamExecuted: boolean;
  redTeamLoading?: boolean;
  highRiskCount: number;
  readinessStatus?: string | null;
  workflowState?: string | null;
  hasInterviewPack?: boolean;
  evidenceGapCount?: number;
  hasInterviewableClaim?: boolean;
  /** Main mission UI mode: keep implementation gates out of the user-facing rail. */
  coreMode?: boolean;
}): string[] {
  if (input.coreMode) {
    const jdHint = isUnknownIdentity(input.company) ? "岗位待确认" : "岗位已识别";
    const resumeChosen = Boolean(input.resumeSourceMode) || input.targetConfirmed;
    const resumeHint = resumeChosen ? "简历已选择" : "尚未选择简历";
    const statusHint = !resumeChosen
      ? "等待选择简历"
      : !input.targetConfirmed
        ? "等待确认简历"
        : input.hasInterviewPack
          ? "问题预览已生成"
          : "先生成问题预览";
    return [jdHint, resumeHint, statusHint];
  }
  const jdHint = isUnknownIdentity(input.company) ? "JD 待确认" : "JD 已解析";
  const resumeChosen = Boolean(input.resumeSourceMode) || input.targetConfirmed;
  const resumeHint = resumeChosen ? "简历已选择" : "尚未选择简历";

  let statusHint = "";
  if (input.redTeamLoading) {
    statusHint = "正在同步压力测试结果…";
  } else if (!input.redTeamExecuted) {
    statusHint = "没有压力测试";
  } else if ((input.highRiskCount ?? 0) > 0) {
    statusHint = `${input.highRiskCount} 个高风险点`;
  } else {
    const readiness = String(input.readinessStatus ?? "").toUpperCase();
    if (readiness === "STRENGTHEN_FIRST" || readiness === "INSUFFICIENT_EVIDENCE") {
      statusHint = "需要补强";
    } else if (readiness === "READY_TO_APPLY") {
      statusHint = "可开始面试准备";
    } else {
      const ws = normalizeWorkflowState(input.workflowState);
      if (ws === "INTERVIEW_IN_PROGRESS") statusHint = "面试进行中";
      else if (ws === "INTERVIEW_PREP_READY") statusHint = "待核对准备状态";
      else if (ws === "STRESS_TEST_REQUIRED" || ws === "STRENGTHENING_REQUIRED") statusHint = "压力测试已完成";
      else statusHint = workflowStateLabel(input.workflowState) || "压力测试已完成";
    }
  }

  return [jdHint, resumeHint, statusHint].filter(Boolean);
}

/** Prefer mission-local bound profile for proof/mock deep links. */
export function mockInterviewProfileId(mission: {
  profile_id?: string | null;
  resume_source?: { bound_profile_id?: string | null } | null;
} | null | undefined): string | null {
  const bound = mission?.resume_source?.bound_profile_id;
  if (typeof bound === "string" && bound.trim()) return bound.trim();
  const pid = mission?.profile_id;
  if (typeof pid === "string" && pid.trim()) return pid.trim();
  return null;
}

/**
 * Working mock entry href. Defaults to fresh=1 so round 1 starts.
 * Note: proof/[profileId]/interview currently accepts mission_id + fresh only —
 * claim_id is NOT wired on that route yet, so full/claim mock share the same href.
 * (Claim alone is enough for ProofPageClient to auto-start a session.)
 */
export function mockInterviewHref(
  mission: {
    id?: string | null;
    profile_id?: string | null;
    resume_source?: { bound_profile_id?: string | null } | null;
  } | null | undefined,
  options?: { fresh?: boolean; claimId?: string | null },
): Route | null {
  const profileId = mockInterviewProfileId(mission);
  const missionId = mission?.id != null ? String(mission.id).trim() : "";
  if (!profileId || !missionId) return null;
  const fresh = options?.fresh === false ? "" : "&fresh=1";
  // claimId reserved for when proof interview searchParams accepts claim_id; ignored today.
  void options?.claimId;
  return `/proof/${encodeURIComponent(profileId)}/interview?mission_id=${encodeURIComponent(missionId)}${fresh}` as Route;
}

export type LastMockDebrief = {
  sessionId: string;
  status: string;
  weakPoints: string[];
  strongPoints: string[];
  gapType: string | null;
  gapWhy: string | null;
  recommendedNextAction: string | null;
  roundCount: number;
  updatedAt: string | null;
  claimId?: string | null;
};

type MockSessionLike = {
  id?: unknown;
  status?: unknown;
  claim_id?: unknown;
  round_count?: unknown;
  strong_points?: unknown;
  weak_points?: unknown;
  gap_type?: unknown;
  gap_why?: unknown;
  recommended_next_action?: unknown;
  updated_at?: unknown;
} | null | undefined;

function _stringList(value: unknown): string[] {
  if (!Array.isArray(value)) return [];
  return value.map((item) => String(item ?? "").trim()).filter(Boolean);
}

/** Build a readable last-debrief card from a COMPLETED interview session. */
export function summarizeMockDebrief(session: MockSessionLike): LastMockDebrief | null {
  if (!session || typeof session !== "object") return null;
  const status = String(session.status ?? "").toUpperCase();
  if (status !== "COMPLETED") return null;
  const sessionId = String(session.id ?? "").trim();
  if (!sessionId) return null;
  return {
    sessionId,
    status,
    weakPoints: _stringList(session.weak_points),
    strongPoints: _stringList(session.strong_points),
    gapType: session.gap_type != null && String(session.gap_type).trim() ? String(session.gap_type) : null,
    gapWhy: session.gap_why != null && String(session.gap_why).trim() ? String(session.gap_why) : null,
    recommendedNextAction:
      session.recommended_next_action != null && String(session.recommended_next_action).trim()
        ? String(session.recommended_next_action)
        : null,
    roundCount: typeof session.round_count === "number" ? session.round_count : Number(session.round_count) || 0,
    updatedAt: session.updated_at != null && String(session.updated_at).trim() ? String(session.updated_at) : null,
    claimId: session.claim_id != null && String(session.claim_id).trim() ? String(session.claim_id) : null,
  };
}

const MOCK_DEBRIEF_MEMORY_PREFIX = "careeros.mockDebrief.v1.";

/** Minimal Interview Memory: persist last COMPLETED debrief per mission (localStorage). */
export function saveLastMockDebrief(missionId: string, debrief: LastMockDebrief): void {
  const id = String(missionId || "").trim();
  if (!id || typeof localStorage === "undefined") return;
  try {
    localStorage.setItem(MOCK_DEBRIEF_MEMORY_PREFIX + id, JSON.stringify(debrief));
  } catch {
    /* ignore quota / private mode */
  }
}

export function loadLastMockDebrief(missionId: string): LastMockDebrief | null {
  const id = String(missionId || "").trim();
  if (!id || typeof localStorage === "undefined") return null;
  try {
    const raw = localStorage.getItem(MOCK_DEBRIEF_MEMORY_PREFIX + id);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LastMockDebrief;
    if (!parsed || typeof parsed !== "object" || !parsed.sessionId) return null;
    return {
      sessionId: String(parsed.sessionId),
      status: String(parsed.status || "COMPLETED"),
      weakPoints: Array.isArray(parsed.weakPoints) ? parsed.weakPoints.map(String).filter(Boolean) : [],
      strongPoints: Array.isArray(parsed.strongPoints) ? parsed.strongPoints.map(String).filter(Boolean) : [],
      gapType: parsed.gapType ?? null,
      gapWhy: parsed.gapWhy ?? null,
      recommendedNextAction: parsed.recommendedNextAction ?? null,
      roundCount: Number(parsed.roundCount) || 0,
      updatedAt: parsed.updatedAt ?? null,
      claimId: parsed.claimId ?? null,
    };
  } catch {
    return null;
  }
}

/** Prefer API session; fall back to local memory. Saves when API has COMPLETED. */
export function resolveLastMockDebrief(missionId: string, session: MockSessionLike): LastMockDebrief | null {
  const fromApi = summarizeMockDebrief(session);
  if (fromApi) {
    saveLastMockDebrief(missionId, fromApi);
    return fromApi;
  }
  return loadLastMockDebrief(missionId);
}

export function mockDebriefHref(
  mission: {
    id?: string | null;
    profile_id?: string | null;
    resume_source?: { bound_profile_id?: string | null } | null;
  } | null | undefined,
): Route | null {
  const profileId = mockInterviewProfileId(mission);
  const missionId = mission?.id != null ? String(mission.id).trim() : "";
  if (!profileId || !missionId) return null;
  return `/proof/${encodeURIComponent(profileId)}/debrief?mission_id=${encodeURIComponent(missionId)}` as Route;
}



export function readinessStatusLabel(status: string | null | undefined): string {
  const key = String(status || "").toUpperCase();
  switch (key) {
    case "SUPPORTED":
      return "证据充分";
    case "DEFENDABLE":
      return "基本可辩护";
    case "WEAK_EVIDENCE":
      return "证据偏弱";
    case "UNSUPPORTED":
      return "暂无证据";
    default:
      return key || "待评估";
  }
}

export function strengthenStatusSummary(status: string | null | undefined): string {
  const key = String(status || "").toUpperCase();
  if (key === "STRENGTHEN_FIRST") return "建议先补强证据，再去面试。";
  if (key === "INSUFFICIENT_EVIDENCE") return "证据还不够，先补一条可核对材料。";
  if (key === "READY_TO_APPLY") return "当前主张已可支撑投递。";
  return "";
}
