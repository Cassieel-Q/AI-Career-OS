/**
 * 题库客户端（目标三）：独立于 mission 的模拟面试流程。
 *
 * BASIC / PROJECT_DEEP_DIVE / HR_QUESTIONS 三分类；难度、面试官风格；单题参考答案；
 * 真题录入；简历优化建议。参考答案只使用已确认事实，grounding 失败时落 UNKNOWN /
 * NEEDS_CONFIRMATION（不编造）。
 */
import { MISSION_API_BASE_URL } from "./missions.ts";

export const QUESTION_CATEGORIES = ["BASIC", "PROJECT_DEEP_DIVE", "HR_QUESTIONS"] as const;
export type QuestionCategory = (typeof QUESTION_CATEGORIES)[number];

export const QUESTION_CATEGORY_LABEL: Record<QuestionCategory, string> = {
  BASIC: "基础题",
  PROJECT_DEEP_DIVE: "项目深挖",
  HR_QUESTIONS: "HR 面",
};

export const QUESTION_DIFFICULTIES = ["EASY", "MEDIUM", "HARD"] as const;
export type QuestionDifficulty = (typeof QUESTION_DIFFICULTIES)[number];

export const QUESTION_DIFFICULTY_LABEL: Record<QuestionDifficulty, string> = {
  EASY: "简单",
  MEDIUM: "中等",
  HARD: "困难",
};

export type ReferenceAnswer = {
  id: string;
  answer_text: string;
  grounding: string;
  evidence_refs: string[];
};

export type QuestionItem = {
  id: string;
  bank_id: string;
  category: QuestionCategory | string;
  difficulty: QuestionDifficulty | string;
  interviewer_style: string | null;
  question_text: string;
  source: string;
  evidence_refs: string[];
  /** 第六阶段：每道题都必须能回答的六个问题。 */
  jd_requirement_refs: string[];
  experience_refs: string[];
  why_asked: string | null;
  expected_evidence: string[];
  followup_paths: string[];
  sample_answer: string | null;
  risk_flags: string[];
  sort_order: number;
  reference_answer: ReferenceAnswer | null;
};

export type QuestionBank = {
  id: string;
  profile_id: string;
  mission_id: string | null;
  name: string;
  item_count: number;
  items: QuestionItem[];
};

export type ResumeSuggestion = {
  kind: string;
  question: string;
  suggestion: string;
  evidence_refs: string[];
  grounding: string | null;
};

export class QuestionBankApiError extends Error {
  status: number;
  detail: unknown;
  constructor(status: number, detail: unknown) {
    super(typeof detail === "string" ? detail : (detail as { message?: string })?.message || "题库请求失败。");
    this.status = status;
    this.detail = detail;
  }
}

async function request<T>(url: string, init?: RequestInit): Promise<T> {
  const response = await fetch(url, init);
  if (!response.ok) {
    const body = await response.json().catch(() => ({}));
    throw new QuestionBankApiError(response.status, body.detail ?? body);
  }
  return response.json() as Promise<T>;
}

const jsonInit = (method: string, body: unknown): RequestInit => ({
  method,
  headers: { "Content-Type": "application/json" },
  body: JSON.stringify(body),
});

export const listQuestionBanks = (profileId: string) =>
  request<QuestionBank[]>(`${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/question-banks`);

export const createQuestionBank = (profileId: string, name = "默认题库", missionId?: string | null) =>
  request<QuestionBank>(
    `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/question-banks`,
    jsonInit("POST", { name, mission_id: missionId ?? null }),
  );

/** 按真实上下文（JD 要点 + 已确认岗位简历）生成三分类题库。 */
export const generateQuestionBank = (
  profileId: string,
  payload: { mission_id?: string | null; target_resume_id?: string | null; raw_jd?: string | null; name?: string | null } = {},
) =>
  request<QuestionBank>(
    `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/question-banks/generate`,
    jsonInit("POST", {
      mission_id: payload.mission_id ?? null,
      target_resume_id: payload.target_resume_id ?? null,
      raw_jd: payload.raw_jd ?? null,
      name: payload.name ?? null,
    }),
  );

export const addQuestionItem = (
  bankId: string,
  payload: { question_text: string; category?: string; difficulty?: string; interviewer_style?: string; source?: string },
) => request<QuestionItem>(`${MISSION_API_BASE_URL}/api/v1/question-banks/${encodeURIComponent(bankId)}/items`, jsonInit("POST", payload));

export const createRealQuestion = (
  profileId: string,
  payload: { question_text: string; category?: string; difficulty?: string; interviewer_style?: string; bank_id?: string; mission_id?: string },
) =>
  request<QuestionItem>(
    `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/question-items/real`,
    jsonInit("POST", payload),
  );

export const generateReferenceAnswer = (itemId: string, force = false) =>
  request<ReferenceAnswer>(
    `${MISSION_API_BASE_URL}/api/v1/question-items/${encodeURIComponent(itemId)}/reference-answer${force ? "?force=true" : ""}`,
    { method: "POST" },
  );

export const fetchResumeSuggestions = (itemId: string) =>
  request<ResumeSuggestion[]>(`${MISSION_API_BASE_URL}/api/v1/question-items/${encodeURIComponent(itemId)}/resume-suggestions`, {
    method: "POST",
  });

/** 参考答案是否为「无法接地」状态（需人工补充事实，而非被编造）。 */
export function isUngroundedAnswer(answer: ReferenceAnswer | null): boolean {
  if (!answer) return true;
  return answer.grounding === "UNKNOWN" || answer.grounding === "NEEDS_CONFIRMATION";
}

export type QuestionExplainer = {
  why: string;
  jdRefs: string[];
  experienceRefs: string[];
  allowedFacts: string[];
  notToInvent: string;
  followups: string[];
};

const NOT_TO_INVENT_HINT = "只能使用上方「可以说的事实」；没有证据的数字、职责与结果一律不要编造，缺失时标注待确认。";

/**
 * 第六阶段：把一道题渲染成「六个必答问题」的答案视图。
 * 全部来自题目自身字段，不做二次推断，避免前端补写未确认内容。
 */
export function explainQuestion(item: QuestionItem): QuestionExplainer {
  const hasEvidence = item.experience_refs.length > 0 && item.expected_evidence.length > 0;
  return {
    why: item.why_asked || "该题未标注考察意图，建议先在题库里补齐 why_asked。",
    jdRefs: item.jd_requirement_refs,
    experienceRefs: item.experience_refs,
    allowedFacts: item.expected_evidence,
    notToInvent: hasEvidence ? NOT_TO_INVENT_HINT : "当前没有带证据的已确认经历可支撑这道题，回答前请先确认相关经历。",
    followups: item.followup_paths,
  };
}
