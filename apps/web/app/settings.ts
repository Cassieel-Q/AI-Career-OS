import { MISSION_API_BASE_URL } from "./missions.ts";

export type LocalStatus = {
  local_mode: boolean;
  data_dir: string | null;
  default_data_dir: string;
  database_url_scheme: string | null;
  using_dataset: boolean;
  active_dataset_id: string | null;
  model_configured: boolean;
  backup_supported: boolean;
};

export type DatasetItem = {
  id: string;
  label: string;
  source: string;
  created_at: string | null;
  counts: Record<string, number>;
  size_bytes: number;
  active: boolean;
};

export type BackupInspection = {
  format: string;
  version: number;
  created_at: string | null;
  dataset_label: string | null;
  counts: Record<string, number>;
  files: Array<{ path: string; declared_size: number; actual_size: number; sha256_ok: boolean }>;
  database_present: boolean;
  integrity_ok: boolean;
  excluded: string[];
  notes: string[];
  size_bytes: number;
};

export type RestoreResult = {
  dataset_id: string;
  label: string;
  database_file: string;
  previous_dataset_id: string | null;
  counts: Record<string, number>;
  restored_files: number;
  note: string;
};

const api = MISSION_API_BASE_URL;

export function readLocalStatus(): Promise<LocalStatus> {
  return fetch(`${api}/api/v1/local/status`).then((r) => r.json());
}

export function readDatasets(): Promise<{ local_mode: boolean; datasets: DatasetItem[] }> {
  return fetch(`${api}/api/v1/local/datasets`).then((r) => r.json());
}

export function activateDataset(id: string): Promise<{ active_dataset_id: string }> {
  return fetch(`${api}/api/v1/local/datasets/${encodeURIComponent(id)}/activate`, { method: "POST" }).then((r) => r.json());
}

export function backupExportUrl(label: string): string {
  return `${api}/api/v1/backup/export?label=${encodeURIComponent(label)}`;
}

export async function inspectBackup(file: File): Promise<BackupInspection> {
  const form = new FormData();
  form.append("file", file);
  const response = await fetch(`${api}/api/v1/backup/inspect`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export async function restoreBackup(file: File, label?: string): Promise<RestoreResult> {
  const form = new FormData();
  form.append("file", file);
  const query = label ? `?label=${encodeURIComponent(label)}` : "";
  const response = await fetch(`${api}/api/v1/backup/restore${query}`, { method: "POST", body: form });
  if (!response.ok) throw new Error(await readError(response));
  return response.json();
}

export function readBackupSummary(): Promise<{ counts: Record<string, number>; status: LocalStatus }> {
  return fetch(`${api}/api/v1/backup/summary`).then((r) => r.json());
}

async function readError(response: Response): Promise<string> {
  try {
    const body = await response.json();
    return typeof body?.detail === "string" ? body.detail : JSON.stringify(body);
  } catch {
    return `请求失败（${response.status}）`;
  }
}
