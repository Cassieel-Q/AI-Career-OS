import { MISSION_API_BASE_URL } from "./missions.ts";

export type JobSource = {
  id: string;
  label: string;
  mode: string;
  auto_collect: boolean;
  note: string;
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
  needs_confirm?: string[];
  raw?: Record<string, unknown>;
  text: string;
};

export type SourceReport = {
  source: string;
  status: "OK" | "EMPTY" | "ERROR";
  fetched?: number;
  count: number;
  filtered_out?: number;
  note: string;
  errors?: string[];
};

export type CollectResult = {
  run_id: string;
  started_at: string;
  finished_at: string;
  request: Record<string, unknown>;
  reports: SourceReport[];
  jobs: CollectedJob[];
  duplicates: Array<{ company: string | null; role: string | null; reason: string; kept_source: string; dropped_source: string }>;
  totals: { returned: number; cross_source_duplicates: number; sources_ok: number; sources_failed: number; sources_empty: number };
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
): Promise<{ saved: SavedCollected[]; skipped: Array<Record<string, unknown>>; saved_count: number; skipped_count: number }> {
  return json(`/api/v1/profiles/${encodeURIComponent(profileId)}/job-ingest/save-collected`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ jobs }),
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
