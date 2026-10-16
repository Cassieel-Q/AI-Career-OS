import { MISSION_API_BASE_URL } from "./missions.ts";

export type WebformField = {
  index: number;
  tag: string;
  type: string;
  control: string;
  name: string;
  id: string;
  label: string;
  placeholder: string;
  required: boolean;
  selector: string;
  options: string[];
};

export type WebformPlan = {
  index: number;
  label: string;
  control: string;
  support: "FULL" | "PARTIAL" | "LIMITED" | "UNSUPPORTED" | "BLOCKED";
  required: boolean;
  selector: string;
  match_key: string | null;
  match_label: string | null;
  value: string;
  status: "READY" | "NEEDS_CONFIRM" | "UNSUPPORTED" | "BLOCKED";
  reason: string;
};

export type WebformRead = {
  page_url: string;
  page_title: string;
  fields: WebformField[];
  plans: WebformPlan[];
  summary: {
    total: number;
    ready: number;
    needs_confirm: number;
    unsupported: number;
    blocked: number;
    by_support: Record<string, number>;
  };
  fact_keys_available: string[];
  sensitive_keys_used: string[];
  note: string;
};

export type WebformFillResult = {
  record_id: string;
  page_url: string;
  page_title: string;
  results: Array<{ selector: string; label: string; ok: boolean; reason: string }>;
  rejected: Array<{ label: string; control: string; reason: string }>;
  summary: { total: number; filled: number; failed: number; skipped: number; submitted: boolean };
  note: string;
};

export type WebformRecord = {
  id: string;
  page_url: string;
  page_title: string | null;
  status: string;
  summary: Record<string, number>;
  assignments: unknown[];
  notes: string | null;
  created_at: string | null;
};

export type WebformStatus = {
  available: boolean;
  bridge_url: string;
  session?: boolean;
  currentUrl?: string | null;
  error?: string;
};

const api = MISSION_API_BASE_URL;

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, init);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      /* keep status code */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function readWebformStatus(): Promise<WebformStatus> {
  return request<WebformStatus>("/api/v1/webform/status");
}

export function startWebformSession(url?: string): Promise<{ ok: boolean; pageUrl: string; pageTitle: string }> {
  return request("/api/v1/webform/session/start", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url: url ?? "" }),
  });
}

export function openWebformUrl(url: string): Promise<{ ok: boolean; pageUrl: string; pageTitle: string }> {
  return request("/api/v1/webform/session/open", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export function readWebformPlan(profileId: string): Promise<WebformRead> {
  return request<WebformRead>(`/api/v1/profiles/${encodeURIComponent(profileId)}/webform/read`);
}

export function fillWebform(
  profileId: string,
  payload: {
    page_url: string;
    page_title: string;
    assignments: Array<{ index: number; selector: string; control: string; label: string; value: string }>;
  },
): Promise<WebformFillResult> {
  return request<WebformFillResult>(`/api/v1/profiles/${encodeURIComponent(profileId)}/webform/fill`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(payload),
  });
}

export function readWebformRecords(profileId: string): Promise<{ records: WebformRecord[] }> {
  return request(`/api/v1/profiles/${encodeURIComponent(profileId)}/webform/records`);
}

export const WEBFORM_TEST_PAGE = "/webform-test.html";
