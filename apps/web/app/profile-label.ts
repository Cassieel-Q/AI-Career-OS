export const PROFILE_LABELS_STORAGE_KEY = "ai-career-os-profile-labels";

export type ProfileLabelEntry = {
  label: string;
  updatedAt: string;
  /** How the label was last derived; resume basename wins over profile fields. */
  source?: "resume" | "profile" | "fallback";
  /** Archive origin for dropdown metadata (never show UUID). */
  origin?: "master" | "mission_local" | "upload" | "unknown";
  isMaster?: boolean;
  isMissionLocal?: boolean;
};

export type ProfileOptionView = {
  profileId: string;
  label: string;
  updatedAt: string;
  origin: NonNullable<ProfileLabelEntry["origin"]>;
  isMaster: boolean;
  isMissionLocal: boolean;
  /** Chinese one-line dropdown text; never includes profile UUID. */
  displayLabel: string;
};

export type ProfileLabelRegistry = Record<string, ProfileLabelEntry>;

const FALLBACK_LABEL = "未命名档案";

export function stripResumeExtension(filename: string): string {
  const base = filename.trim().replace(/\\/g, "/").split("/").pop() || filename.trim();
  return base.replace(/\.pdf$/i, "").trim();
}

export function pickLabel(input: {
  resumeFilename?: string | null;
  display_name?: string | null;
  full_name?: string | null;
  name?: string | null;
}): string {
  const fromFile = input.resumeFilename ? stripResumeExtension(String(input.resumeFilename)) : "";
  if (fromFile) return fromFile;
  for (const value of [input.display_name, input.full_name, input.name]) {
    const text = typeof value === "string" ? value.trim() : "";
    if (text) return text;
  }
  return FALLBACK_LABEL;
}

export function readProfileLabelRegistry(): ProfileLabelRegistry {
  if (typeof window === "undefined") return {};
  try {
    const raw = window.localStorage.getItem(PROFILE_LABELS_STORAGE_KEY);
    if (!raw) return {};
    const parsed = JSON.parse(raw) as unknown;
    if (!parsed || typeof parsed !== "object" || Array.isArray(parsed)) return {};
    const out: ProfileLabelRegistry = {};
    for (const [profileId, entry] of Object.entries(parsed as Record<string, unknown>)) {
      if (!profileId.trim() || !entry || typeof entry !== "object") continue;
      const record = entry as {
        label?: unknown;
        updatedAt?: unknown;
        source?: unknown;
        origin?: unknown;
        isMaster?: unknown;
        isMissionLocal?: unknown;
      };
      const label = typeof record.label === "string" ? record.label.trim() : "";
      if (!label) continue;
      out[profileId] = {
        label,
        updatedAt: typeof record.updatedAt === "string" ? record.updatedAt : new Date().toISOString(),
        source:
          record.source === "resume" || record.source === "profile" || record.source === "fallback"
            ? record.source
            : undefined,
        origin:
          record.origin === "master" ||
          record.origin === "mission_local" ||
          record.origin === "upload" ||
          record.origin === "unknown"
            ? record.origin
            : undefined,
        isMaster: record.isMaster === true,
        isMissionLocal: record.isMissionLocal === true,
      };
    }
    return out;
  } catch {
    return {};
  }
}

function writeRegistry(registry: ProfileLabelRegistry): void {
  window.localStorage.setItem(PROFILE_LABELS_STORAGE_KEY, JSON.stringify(registry));
}

/** Keep first occurrence per profile_id. */
export function dedupeProfileOptions<T extends { profileId: string }>(options: T[]): T[] {
  const seen = new Set<string>();
  const out: T[] = [];
  for (const item of options) {
    const id = String(item.profileId || "").trim();
    if (!id || seen.has(id)) continue;
    seen.add(id);
    out.push(item);
  }
  return out;
}

function formatUpdatedAtCn(iso: string | undefined): string {
  if (!iso) return "时间未知";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "时间未知";
  const pad = (n: number) => String(n).padStart(2, "0");
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}`;
}

function originLabelCn(entry: Pick<ProfileLabelEntry, "origin" | "source" | "isMaster" | "isMissionLocal">): string {
  if (entry.isMissionLocal || entry.origin === "mission_local") return "岗位专属上传/粘贴";
  if (entry.isMaster || entry.origin === "master") return "Master 档案";
  if (entry.origin === "upload") return "首页上传";
  if (entry.source === "resume") return "简历文件名";
  if (entry.source === "profile") return "档案字段";
  return "未知来源";
}

/** Build Chinese dropdown line: 档案名称 / 更新时间 / 来源类型 / Master / 岗位专属. */
export function formatProfileOptionLabel(
  entry: { label?: string } & Partial<ProfileLabelEntry>,
  opts?: { currentMissionBoundId?: string | null; profileId?: string },
): string {
  const name = (entry.label || "").trim() || FALLBACK_LABEL;
  const time = formatUpdatedAtCn(entry.updatedAt);
  const origin = originLabelCn(entry);
  const isMaster = Boolean(entry.isMaster || entry.origin === "master");
  const isMissionLocal = Boolean(entry.isMissionLocal || entry.origin === "mission_local");
  const isCurrent =
    opts?.currentMissionBoundId &&
    opts?.profileId &&
    opts.currentMissionBoundId.trim() === opts.profileId.trim();
  const masterText = isMaster ? "是" : "否";
  const missionText = isCurrent ? "当前岗位专属" : isMissionLocal ? "是" : "否";
  return `${name} · 更新 ${time} · ${origin} · Master:${masterText} · 岗位专属:${missionText}`;
}

function toOptionView(profileId: string, entry: ProfileLabelEntry): ProfileOptionView {
  const isMaster = Boolean(entry.isMaster || entry.origin === "master");
  const isMissionLocal = Boolean(entry.isMissionLocal || entry.origin === "mission_local");
  const origin: ProfileOptionView["origin"] =
    entry.origin ||
    (isMissionLocal ? "mission_local" : isMaster ? "master" : entry.source === "resume" ? "upload" : "unknown");
  const view: ProfileOptionView = {
    profileId,
    label: entry.label || FALLBACK_LABEL,
    updatedAt: entry.updatedAt || "",
    origin,
    isMaster,
    isMissionLocal,
    displayLabel: "",
  };
  view.displayLabel = formatProfileOptionLabel(view, { profileId });
  return view;
}

export function listProfileLabelOptions(): ProfileOptionView[] {
  const registry = readProfileLabelRegistry();
  const options = Object.entries(registry)
    .map(([profileId, entry]) => toOptionView(profileId, entry))
    .sort((a, b) => (b.updatedAt || "").localeCompare(a.updatedAt || ""));
  return dedupeProfileOptions(options);
}

export function removeProfileLabel(profileId: string): void {
  const id = profileId.trim();
  if (!id || typeof window === "undefined") return;
  const registry = readProfileLabelRegistry();
  if (!(id in registry)) return;
  delete registry[id];
  writeRegistry(registry);
}

/** Upsert a human label. Resume-sourced labels are sticky until replaced by another resume. */
export function upsertProfileLabel(
  profileId: string,
  label: string,
  source: ProfileLabelEntry["source"] = "fallback",
  meta?: Pick<ProfileLabelEntry, "origin" | "isMaster" | "isMissionLocal">,
): void {
  const id = profileId.trim();
  const text = label.trim() || FALLBACK_LABEL;
  if (!id || typeof window === "undefined") return;
  const registry = readProfileLabelRegistry();
  const prev = registry[id];
  if (prev?.source === "resume" && source !== "resume" && prev.label && prev.label !== FALLBACK_LABEL) {
    registry[id] = {
      ...prev,
      updatedAt: new Date().toISOString(),
      origin: meta?.origin ?? prev.origin,
      isMaster: meta?.isMaster ?? prev.isMaster,
      isMissionLocal: meta?.isMissionLocal ?? prev.isMissionLocal,
    };
    writeRegistry(registry);
    return;
  }
  registry[id] = {
    label: text,
    updatedAt: new Date().toISOString(),
    source,
    origin: meta?.origin ?? prev?.origin,
    isMaster: meta?.isMaster ?? prev?.isMaster,
    isMissionLocal: meta?.isMissionLocal ?? prev?.isMissionLocal,
  };
  writeRegistry(registry);
}

export function upsertProfileLabelFromFilename(
  profileId: string,
  filename: string,
  meta?: Pick<ProfileLabelEntry, "origin" | "isMaster" | "isMissionLocal">,
): void {
  upsertProfileLabel(profileId, pickLabel({ resumeFilename: filename }), "resume", meta);
}

export function upsertProfileLabelFromSnapshot(
  profileId: string,
  snapshot: {
    display_name?: string | null;
    full_name?: string | null;
    name?: string | null;
  } | null | undefined,
  meta?: Pick<ProfileLabelEntry, "origin" | "isMaster" | "isMissionLocal">,
): string {
  const label = pickLabel({
    display_name: snapshot?.display_name,
    full_name: snapshot?.full_name,
    name: snapshot?.name,
  });
  const source = label === FALLBACK_LABEL ? "fallback" : "profile";
  upsertProfileLabel(profileId, label, source, meta);
  const registry = readProfileLabelRegistry();
  return registry[profileId.trim()]?.label ?? label;
}

export function ensureProfileOption(
  profileId: string,
  options = listProfileLabelOptions(),
): ProfileOptionView[] {
  const id = profileId.trim();
  const deduped = dedupeProfileOptions(options);
  if (!id) return deduped;
  if (deduped.some((item) => item.profileId === id)) return deduped;
  return [toOptionView(id, { label: FALLBACK_LABEL, updatedAt: "", origin: "unknown" }), ...deduped];
}
