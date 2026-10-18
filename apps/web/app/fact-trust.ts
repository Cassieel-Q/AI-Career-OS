import { MISSION_API_BASE_URL } from "./missions.ts";

/** 事实核对：把「提取到 / 采纳改写 / 用户核实」三件事分开呈现。 */

export type FactVerificationStatus = "UNREVIEWED" | "USER_ATTESTED" | "REJECTED";

export type FactItem = {
  fact_key: string;
  title: string;
  original_text: string;
  suggested_text: string | null;
  source_kind: string;
  source_id: string | null;
  source_type: string | null;
  verification_status: FactVerificationStatus;
  verified_at: string | null;
  present_aspects: string[];
  missing_aspects: string[];
  risk: string;
  note: string | null;
};

export type FactList = {
  profile_id: string;
  facts: FactItem[];
  attested_count: number;
  rejected_count: number;
  pending_count: number;
};

export type FactAttestResult = {
  fact_key: string;
  status: FactVerificationStatus;
  verification_status: FactVerificationStatus;
  fact_text: string;
  source_kind: string;
  verified_at: string | null;
  applied_to_source: boolean;
  note: string | null;
};

const base = (profileId: string) => `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}`;

type Requester = typeof fetch;

async function request<T>(url: string, init?: RequestInit, send: Requester = fetch): Promise<T> {
  const response = await send(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `事实接口请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

export const readFacts = (profileId: string, send: Requester = fetch) =>
  request<FactList>(`${base(profileId)}/facts`, undefined, send);

export const attestFact = (
  profileId: string,
  payload: {
    fact_key: string;
    status: FactVerificationStatus;
    fact_text?: string;
    note?: string;
    apply_to_source?: boolean;
  },
  send: Requester = fetch,
) =>
  request<FactAttestResult>(
    `${base(profileId)}/facts/attest`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    },
    send,
  );

export const readAttestedFacts = (profileId: string, send: Requester = fetch) =>
  request<{ profile_id: string; facts: string[] }>(`${base(profileId)}/facts/attested`, undefined, send);

export const FACT_STATUS_LABEL: Record<FactVerificationStatus, string> = {
  UNREVIEWED: "待核对",
  USER_ATTESTED: "你已确认属实",
  REJECTED: "已标记为不属实",
};

/** 只有用户明确确认过才算已核实——「档案已确认」不算。 */
export const isAttested = (fact: FactItem): boolean => fact.verification_status === "USER_ATTESTED";

// --------------------------------------------------------------------------
// 参考答案：把「已知事实 / 待补 / 方法 / 示范」拆开展示
// --------------------------------------------------------------------------

export type ReferenceAnswerDetail = {
  grounded: boolean;
  known_facts?: Array<{ text?: string; source_kind?: string; source_id?: string | null; quote?: string | null }>;
  missing_facts?: Array<{ aspect?: string; question?: string }>;
  answer_structure?: string[];
  sample_wording?: string | null;
  blocked_reason?: string | null;
  screening?: Record<string, unknown>;
};

export type ReferenceAnswerSections = {
  /** 可使用的示范表达；事实不足时为 null。 */
  wording: string | null;
  known: Array<{ text: string; source_kind?: string; quote?: string | null }>;
  missing: Array<{ aspect: string; question: string }>;
  structure: string[];
  /** true 表示已降级：只展示已知事实与待补项，不产出成稿。 */
  blocked: boolean;
};

/**
 * 解析结构化参考答案。
 *
 * 只有 grounded 且确实给了 sample_wording 时才产出示范表达；其余一律降级。
 */
export function referenceAnswerSections(detail: ReferenceAnswerDetail | null | undefined): ReferenceAnswerSections {
  if (!detail) {
    return { wording: null, known: [], missing: [], structure: [], blocked: true };
  }
  const known = (detail.known_facts ?? [])
    .filter((item) => item && typeof item.text === "string" && item.text.trim())
    .map((item) => ({ text: item.text as string, source_kind: item.source_kind, quote: item.quote ?? null }));
  const missing = (detail.missing_facts ?? [])
    .filter((item) => item && (item.aspect || item.question))
    .map((item) => ({ aspect: item.aspect ?? "待补充", question: item.question ?? "" }));
  const structure = (detail.answer_structure ?? []).filter((step) => typeof step === "string" && step.trim());
  const wording = detail.grounded && detail.sample_wording ? detail.sample_wording : null;
  return { wording, known, missing, structure, blocked: wording === null };
}
