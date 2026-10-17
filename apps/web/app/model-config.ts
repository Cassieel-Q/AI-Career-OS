import { MISSION_API_BASE_URL } from "./missions.ts";

/** 本机客户端标识头：跨域请求带自定义头会触发预检，预检被后端 Origin 白名单拦住。 */
export const CLIENT_HEADER_NAME = "X-AI-Career-Client";
export const CLIENT_HEADER_VALUE = "ai-career-web";

const api = MISSION_API_BASE_URL;

export type ProviderPreset = {
  id: string;
  label: string;
  base_url: string;
  models: string[];
  requires_key: boolean;
  local: boolean;
  key_url: string;
  hint: string;
};

export type Capabilities = {
  chat?: boolean | null;
  tools?: boolean | null;
  json?: boolean | null;
  streaming?: boolean | null;
};

export type ModelConfigView = {
  id: string;
  name: string;
  provider_id: string;
  provider_label: string;
  base_url: string;
  model_id: string;
  timeout_seconds: number;
  enabled: boolean;
  is_default: boolean;
  created_at: string | null;
  updated_at: string | null;
  key_present: boolean;
  key_masked: string;
  key_fingerprint: string;
  key_cipher: string | null;
  key_bound: boolean;
  key_bound_base_url: string;
  capabilities: Capabilities;
  last_test: { at: string; ok: boolean; model: string } | null;
};

export type ModuleStatus = {
  key: string;
  label: string;
  source: "user" | "env" | "user-broken" | "none";
  config_id: string | null;
  config_name: string | null;
  model: string | null;
  base_url: string | null;
  note: string;
  usable: boolean;
};

export type ModelStatus = {
  configured: boolean;
  has_user_config: boolean;
  default_config_id: string | null;
  assignments: Record<string, string>;
  configs: ModelConfigView[];
  modules: ModuleStatus[];
  providers: ProviderPreset[];
  env_fallback_active: boolean;
  env_warning: string | null;
  storage: { path: string; in_backup: boolean; note: string };
  secret_cipher: string;
};

export type TestStep = { step: string; ok: boolean | null; detail: string };

export type TestResult = {
  ok: boolean;
  capabilities: Capabilities;
  steps: TestStep[];
  elapsed_ms: number;
  cost_note: string;
  error: { category: string; message: string } | null;
};

export type ConfigDraft = {
  name?: string;
  provider_id?: string;
  base_url?: string | null;
  model_id?: string;
  timeout_seconds?: number;
  api_key?: string | null;
  clear_key?: boolean;
  enabled?: boolean;
};

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, {
    ...init,
    headers: {
      "Content-Type": "application/json",
      [CLIENT_HEADER_NAME]: CLIENT_HEADER_VALUE,
      ...(init?.headers ?? {}),
    },
  });
  if (!response.ok) throw new Error(await readError(response));
  return (await response.json()) as T;
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
  } catch {
    return `请求失败（${response.status}）`;
  }
}

export function readModelStatus(): Promise<ModelStatus> {
  return request<ModelStatus>("/api/v1/model-configs/status");
}

export function createModelConfig(draft: ConfigDraft): Promise<ModelConfigView> {
  return request<ModelConfigView>("/api/v1/model-configs", { method: "POST", body: JSON.stringify(draft) });
}

export function updateModelConfig(id: string, draft: ConfigDraft): Promise<ModelConfigView> {
  return request<ModelConfigView>(`/api/v1/model-configs/${encodeURIComponent(id)}`, {
    method: "PATCH",
    body: JSON.stringify(draft),
  });
}

export function deleteModelConfig(id: string): Promise<{ deleted: string }> {
  return request<{ deleted: string }>(`/api/v1/model-configs/${encodeURIComponent(id)}`, { method: "DELETE" });
}

export function activateModelConfig(id: string): Promise<{ default_config_id: string }> {
  return request<{ default_config_id: string }>(`/api/v1/model-configs/${encodeURIComponent(id)}/activate`, { method: "POST" });
}

export function saveAssignments(assignments: Record<string, string>): Promise<{ assignments: Record<string, string> }> {
  return request<{ assignments: Record<string, string> }>("/api/v1/model-configs/assignments", {
    method: "PUT",
    body: JSON.stringify({ assignments }),
  });
}

export type TestDraft = {
  config_id?: string;
  provider_id?: string;
  base_url?: string;
  model_id?: string;
  api_key?: string;
  timeout_seconds?: number;
  confirm: boolean;
  probe_tools?: boolean;
  probe_stream?: boolean;
};

export function testModelConnection(draft: TestDraft): Promise<TestResult> {
  return request<TestResult>("/api/v1/model-configs/test", { method: "POST", body: JSON.stringify(draft) });
}
