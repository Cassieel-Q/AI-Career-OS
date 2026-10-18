import { MISSION_API_BASE_URL } from "./missions.ts";

/** 事实更新的影响面（指令 5.2）：只读影响分析 + 用户显式选择同步。 */

export type FactImpactMatch = {
  node_id: string | null;
  location: string;
  kind: "field" | "bullet";
  current_text: string;
  source_text: string | null;
  changed: boolean;
  claim_status: string | null;
};

export type FactImpactMission = {
  mission_id: string;
  display_name: string;
  company: string;
  role: string;
  studio_revision: number;
  confirmed_revision: number | null;
  already_delivered: boolean;
  impact: "CHANGED" | "REVIEW" | "NONE";
  matches: FactImpactMatch[];
};

export type FactImpact = {
  source_kind: string;
  source_id: string;
  source_label: string;
  summary: string;
  total_missions: number;
  needs_update_count: number;
  missions: FactImpactMission[];
  auto_update: boolean;
};

export type FactSyncResult = {
  mission_id: string;
  updated: Array<{ node_id: string | null; location: string; before: string; after: string }>;
  skipped: Array<{ node_id: string | null; location: string; reason: string }>;
  revision: number;
  changed: boolean;
  message?: string;
};

const base = (profileId: string, sourceKind: string, sourceId: string) =>
  `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/facts/${encodeURIComponent(sourceKind)}/${encodeURIComponent(sourceId)}`;

type Requester = typeof fetch;

async function request<T>(url: string, init?: RequestInit, send: Requester = fetch): Promise<T> {
  const response = await send(url, init);
  if (!response.ok) {
    const body = (await response.json().catch(() => ({}))) as { detail?: string };
    throw new Error(body.detail ?? `事实影响接口请求失败（${response.status}）`);
  }
  return (await response.json()) as T;
}

export const readFactImpact = (
  profileId: string,
  sourceKind: string,
  sourceId: string,
  send: Requester = fetch,
) => request<FactImpact>(`${base(profileId, sourceKind, sourceId)}/impact`, undefined, send);

/** 按事实键（如 ``experience:<uuid>:description:0``）查询影响面。 */
export const readFactImpactByKey = (profileId: string, factKey: string, send: Requester = fetch) =>
  request<FactImpact>(
    `${MISSION_API_BASE_URL}/api/v1/profiles/${encodeURIComponent(profileId)}/facts/impact?fact_key=${encodeURIComponent(factKey)}`,
    undefined,
    send,
  );

export const syncFactToMission = (
  profileId: string,
  sourceKind: string,
  sourceId: string,
  missionId: string,
  expectedRevision?: number | null,
  send: Requester = fetch,
) =>
  request<FactSyncResult>(
    `${base(profileId, sourceKind, sourceId)}/sync`,
    {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ mission_id: missionId, expected_revision: expectedRevision ?? null }),
    },
    send,
  );

export const IMPACT_LABEL: Record<FactImpactMission["impact"], string> = {
  CHANGED: "需要更新",
  REVIEW: "建议复核",
  NONE: "暂时无需改动",
};

/** 摘要默认用服务端文案，缺失时本地兜底成同样口径，避免 UI 自创说法。 */
export function impactSummary(impact: FactImpact | null): string {
  if (!impact) return "";
  if (impact.summary) return impact.summary;
  return `这项事实关联了 ${impact.total_missions} 份岗位简历，其中 ${impact.needs_update_count} 份可能需要更新。`;
}
