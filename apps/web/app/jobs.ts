import { MISSION_API_BASE_URL } from "./missions.ts";

export type JobSource = {
  id: string;
  label: string;
  mode: string;
  auto_collect: boolean;
  note: string;
  capabilities?: Record<string, boolean>;
  filter_mode?: "server" | "local";
  requires_config?: boolean;
  config_key?: string | null;
  config_placeholder?: string | null;
  presets?: string[];
  preset_verified_at?: string | null;
  has_collect?: boolean;
};

export type FetchedJob = {
  url: string;
  status: "PARSED" | "BLOCKED" | "PARSE_EMPTY" | "UNSUPPORTED_PAGE" | "ERROR";
  title: string;
  text: string;
  content_type: string;
  note: string;
  fetched_at: string;
};

export type CollectResultStatus = "NEW" | "DUPLICATE" | "UPDATED" | "NEEDS_REVIEW" | "FAILED";

export type CollectedJob = {
  schema?: string;
  source: string;
  source_url: string;
  apply_url?: string;
  company: string;
  company_is_board_token?: boolean;
  role: string;
  location: string;
  jd?: string;
  jd_excerpt?: string;
  tags?: string[];
  posted_at?: string | null;
  collected_at: string;
  employment_type?: "INTERN" | "FULLTIME" | "UNKNOWN";
  dedupe_key?: string;
  content_hash?: string;
  needs_confirm?: string[];
  match_score?: number;
  result_status?: CollectResultStatus;
  result_reason?: string;
  existing?: { kind: string; id: string; company: string | null; role: string | null; hash?: string | null };
  raw?: Record<string, unknown>;
  text: string;
};

export type SourceReport = {
  source: string;
  status: "OK" | "EMPTY" | "ERROR" | "TIMEOUT" | "CANCELLED";
  fetched?: number;
  count: number;
  filtered_out?: number;
  note: string;
  errors?: string[];
  filter_mode?: "server" | "local";
  capabilities?: Record<string, boolean>;
  latency_ms?: number;
};

export type CollectResult = {
  status?: CollectTaskStatus;
  task_id?: string;
  run_id: string;
  started_at: string;
  finished_at: string;
  request: Record<string, unknown>;
  reports: SourceReport[];
  jobs: CollectedJob[];
  duplicates: Array<{ company: string | null; role: string | null; reason: string; kept_source: string; dropped_source: string }>;
  totals: {
    returned: number;
    fetched?: number;
    filtered_out?: number;
    new?: number;
    duplicate?: number;
    updated?: number;
    needs_review?: number;
    failed?: number;
    saveable?: number;
    cross_source_duplicates: number;
    sources_ok: number;
    sources_failed: number;
    sources_empty: number;
    sources_total?: number;
    sources_cancelled?: number;
    sources_timeout?: number;
  };
  warnings?: string[];
};

export type CollectTaskStatus = "IDLE" | "RUNNING" | "COMPLETED" | "PARTIAL" | "FAILED" | "CANCELLED";

export type CollectTaskSnapshot = {
  task_id: string;
  profile_id: string;
  status: CollectTaskStatus;
  stage: string;
  current_source: string | null;
  fetched: number;
  created_at: string;
  started_at: string | null;
  finished_at: string | null;
  elapsed_seconds: number | null;
  request: Record<string, unknown>;
  progress: Array<Record<string, unknown> & { type?: string; source?: string; at?: string }>;
  result: CollectResult | null;
  error: string | null;
};

export type CollectFilter = {
  keywords: string[];
  sources: string[];
  location?: string;
  employment_type?: string;
  posted_within_days?: number;
  limit: number;
  greenhouse_boards: string[];
  lever_companies: string[];
  timeout_seconds?: number | null;
};

export type BridgeStatus = {
  available: boolean;
  bridge_url: string;
  session?: boolean;
  currentUrl?: string | null;
  error?: string;
};

export type BrowserCapture = {
  status: "OK" | "BLOCKED" | "LISTING_UNSUPPORTED" | "EMPTY" | "ERROR";
  page_url?: string;
  page_title?: string;
  note?: string;
  confidence?: Record<string, string>;
  job?: CollectedJob | null;
};

export type LibraryItem = {
  kind: "CANDIDATE" | "MISSION";
  id: string;
  company: string | null;
  role: string | null;
  location: string | null;
  status: string;
  source_kind?: string;
  workflow_state?: string;
  source_url: string | null;
  collected_at: string | null;
  parse_status: string;
  imported_mission_id?: string | null;
  excerpt: string;
};

export type LibraryResult = {
  items: LibraryItem[];
  count: number;
  facets: { companies: string[]; locations: string[] };
};

const api = MISSION_API_BASE_URL;

async function json<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(`${api}${path}`, init);
  if (!response.ok) {
    let detail = `${response.status}`;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
    } catch {
      /* keep code */
    }
    throw new Error(detail);
  }
  return (await response.json()) as T;
}

export function readJobSources(): Promise<{ sources: JobSource[] }> {
  return json("/api/v1/job-ingest/sources");
}

export type ProfileSummary = { id: string; full_name: string; status: string };

/** 本机档案列表：页面在 localStorage 没有档案 ID 时用它挑第一个兜底。 */
export function readProfiles(): Promise<{ profiles: ProfileSummary[] }> {
  return json("/api/v1/profiles");
}

export function fetchJobUrl(url: string): Promise<FetchedJob> {
  return json("/api/v1/job-ingest/fetch-url", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ url }),
  });
}

export async function extractJobFile(file: File): Promise<{ filename: string; status: string; text: string; note: string; size_bytes: number }> {
  const form = new FormData();
  form.append("file", file);
  return json("/api/v1/job-ingest/extract-file", { method: "POST", body: form });
}

export function collectRemoteOk(tag: string, limit: number): Promise<{
  source: string;
  status: string;
  collected_at?: string;
  count?: number;
  note?: string;
  jobs: CollectedJob[];
}> {
  return json("/api/v1/job-ingest/collect-remoteok", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tag: tag || null, limit }),
  });
}

export function collectJobs(filter: CollectFilter): Promise<CollectResult> {
  return json("/api/v1/job-ingest/collect", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filter),
  });
}

/** 启动一次采集任务：立即返回 task_id，前端轮询进度、可中途取消。 */
export function startCollectRun(profileId: string, filter: CollectFilter): Promise<CollectTaskSnapshot> {
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/job-ingest/collect-runs`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(filter),
  });
}

export function readCollectRun(taskId: string): Promise<CollectTaskSnapshot> {
  return json(`/api/v1/job-ingest/collect-runs/${encodeURIComponent(taskId)}`);
}

export function cancelCollectRun(taskId: string): Promise<CollectTaskSnapshot> {
  return json(`/api/v1/job-ingest/collect-runs/${encodeURIComponent(taskId)}/cancel`, { method: "POST" });
}

export function healthCheckSource(
  sourceId: string,
  config: { greenhouse_boards?: string[]; lever_companies?: string[] } = {},
): Promise<{ source: string; status: string; note: string; latency_ms?: number; checked?: string[] }> {
  return json(`/api/v1/job-ingest/adapters/${encodeURIComponent(sourceId)}/health-check`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ greenhouse_boards: config.greenhouse_boards ?? [], lever_companies: config.lever_companies ?? [] }),
  });
}

export function readBridgeStatus(): Promise<BridgeStatus> {
  return json("/api/v1/job-ingest/bridge-status");
}

export function collectBrowserPage(): Promise<BrowserCapture> {
  return json("/api/v1/job-ingest/collect-browser", { method: "POST" });
}

export type SavedCollected = {
  source?: string;
  source_url?: string;
  company?: string | null;
  role?: string | null;
  location?: string | null;
  parse_status?: string;
  needs_confirm?: string[];
  candidate_ids: string[];
};

export function saveCollectedJobs(
  profileId: string,
  jobs: CollectedJob[],
  updateDuplicates = false,
): Promise<{
  saved: SavedCollected[];
  updated: Array<{ company: string | null; role: string | null; reason: string; targets: Array<Record<string, string>> }>;
  skipped: Array<Record<string, unknown>>;
  saved_count: number;
  updated_count: number;
  skipped_count: number;
}> {
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/job-ingest/save-collected`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobs, update_duplicates: updateDuplicates }),
  });
}

export function readJobLibrary(
  profileId: string,
  filters: { q?: string; company?: string; location?: string; kind?: string },
): Promise<LibraryResult> {
  const params = new URLSearchParams();
  if (filters.q) params.set("q", filters.q);
  if (filters.company) params.set("company", filters.company);
  if (filters.location) params.set("location", filters.location);
  if (filters.kind) params.set("kind", filters.kind);
  const suffix = params.toString() ? `?${params.toString()}` : "";
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/job-ingest/library${suffix}`);
}

export function parseCandidateJobs(profileId: string, sourceText: string, sourceKind: string): Promise<Array<{ id: string; company: string | null; role: string | null }>> {
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/candidate-jobs/parse`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source_text: sourceText, source_kind: sourceKind }),
  });
}

export function importCandidateJob(candidateId: string): Promise<{ candidate_id: string; mission_id: string; company: string; role: string; reused: boolean }> {
  return json(`/api/v1/candidate-jobs/${encodeURIComponent(candidateId)}/import`, { method: "POST" });
}

// ---------------------------------------------------------------------------
// 手动导入（BOSS 直聘等需要登录的中文平台）：粘贴 → 解析 → 确认 → 保存 → 进入匹配
// ---------------------------------------------------------------------------

export type JobDraft = {
  schema?: string;
  source?: string;
  source_site?: string;
  recognition?: string;
  source_url?: string;
  company?: string;
  role?: string;
  location?: string;
  salary_text?: string;
  education?: string;
  experience?: string;
  employment_type?: "INTERN" | "FULLTIME" | "PARTTIME" | "UNKNOWN";
  jd?: string;
  jd_excerpt?: string;
  collected_at?: string;
  dedupe_key?: string;
  content_hash?: string;
  needs_confirm?: string[];
  confidence?: Record<string, string>;
  warnings?: string[];
  text?: string;
  original_length?: number;
};

export function parseManualJob(input: {
  source_text: string;
  source_url?: string;
  source_site?: string;
  provided?: Record<string, string>;
}): Promise<{ status: string; draft: JobDraft }> {
  return json("/api/v1/job-import/parse", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ recognition: "MANUAL_PASTE", ...input }),
  });
}

export type ManualSaveResult = {
  status: "NEW" | "DUPLICATE" | "UPDATED";
  candidate_id: string;
  company?: string | null;
  role?: string | null;
  changed_fields?: string[];
  message?: string;
  mission_id?: string;
  mission_reused?: boolean;
  mission_error?: string;
  user_edited_preserved?: boolean;
};

export function saveManualJob(
  profileId: string,
  draft: JobDraft,
  options: { update_duplicates?: boolean; import_to_mission?: boolean } = {},
): Promise<ManualSaveResult> {
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/job-import/save`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ draft, ...options }),
  });
}

// 扩展配对相关接口统一放在 ../settings.ts（页面「设置 → 浏览器扩展」里生成配对码）。
