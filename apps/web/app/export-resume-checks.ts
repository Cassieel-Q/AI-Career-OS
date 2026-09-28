/**
 * 投递版导出前的纯逻辑检查（无 React / DOM）。
 *
 * - resolveExportProfileId：从 mission.resume_source 解析本岗位实际绑定的档案。
 * - classifyExperienceSection：把经历归入 教育补充 / 校园经历 / 荣誉奖项 / 项目经历 / 工作/实习经历 / 其他经历。
 * - normalizeSkills：技能去重 + 常见大小写规范。
 * - formatHonorsSection：生成「荣誉奖项」节的行文本。
 * - buildPreExportChecklist：导出前检查（block 阻止导出 / warn 仅提示）。
 * - buildExportFileName：`姓名-公司-岗位` 文件名（Windows 安全）。
 *
 * 暂未接入 export-target-resume.ts；后续接入投递版 HTML / 打印 PDF 时使用。
 */

import type { ExportBullet, ExportExperience, ExportProfile, ExportSelection, ExportSkill } from "./export-target-resume.ts";

// ---------------------------------------------------------------------------
// shared helpers
// ---------------------------------------------------------------------------

const PLACEHOLDER_VALUES = ["unknown", "n/a", "none", "null", "undefined", "未知", "待确认"];

function text(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value).replace(/\s+/g, " ").trim();
}

function isPlaceholder(value: unknown): boolean {
  const t = text(value);
  if (!t) return true;
  if (PLACEHOLDER_VALUES.indexOf(t.toLowerCase()) >= 0) return true;
  return /\bunknown\b/i.test(t);
}

function clean(value: unknown): string {
  const t = text(value);
  return isPlaceholder(t) ? "" : t;
}

function isOmitted(selections: ExportSelection[] | null | undefined, experienceId: string): boolean {
  for (const row of selections ?? []) {
    if (row.experience_id === experienceId) return String(row.decision).toUpperCase() === "OMIT";
  }
  return false;
}

function normType(value: unknown): string {
  return text(value).toLowerCase().replace(/[\s-]+/g, "_");
}

// ---------------------------------------------------------------------------
// 1. resolveExportProfileId
// ---------------------------------------------------------------------------

/**
 * resume_source 实际写入的键（见 apps/api mission_service.py
 * confirm_resume_source / bind_mission_resume_from_extraction）：
 * - mode=master：{ mode, bound_at, isolation: "shared_master", master_profile_id }
 * - mode=upload|paste，默认 copy-on-write：{ mode, bound_at, isolation: "mission_local",
 *   bound_profile_id, master_profile_id, filename, content_hash, section_order }
 * - mode=upload|paste，update_master=true：{ mode, bound_at, isolation: "shared_master",
 *   updated_master: true, master_profile_id, filename, content_hash, section_order }（无 bound_profile_id）
 * 后端有效档案 = resume_source.bound_profile_id || mission.profile_id（_bound_profile_id / _effective_profile_for_mission）。
 */
export type ExportResumeSource = {
  mode?: string | null;
  isolation?: string | null;
  bound_profile_id?: string | null;
  master_profile_id?: string | null;
  /** 旧数据 / 兼容键，后端当前不写入。 */
  profile_id?: string | null;
  [key: string]: unknown;
};

export type ExportMissionLike = {
  profile_id?: string | null;
  resume_source?: ExportResumeSource | Record<string, unknown> | null;
};

export type ExportProfileIdSource =
  | "resume_source.bound_profile_id"
  | "resume_source.master_profile_id"
  | "resume_source.profile_id"
  | "mission.profile_id"
  | "none";

export type ResolvedExportProfileId = {
  profileId: string | null;
  source: ExportProfileIdSource;
  mode: string | null;
  isolation: string | null;
};

function idValue(value: unknown): string {
  if (typeof value !== "string" && typeof value !== "number") return "";
  return clean(value);
}

/** 解析投递版应读取的档案 id：bound_profile_id → master_profile_id → profile_id(兼容) → mission.profile_id。 */
export function resolveExportProfileId(mission: ExportMissionLike | null | undefined): ResolvedExportProfileId {
  const raw = mission && mission.resume_source;
  const src: Record<string, unknown> = raw && typeof raw === "object" ? (raw as Record<string, unknown>) : {};
  const mode = clean(src.mode) || null;
  const isolation = clean(src.isolation) || null;
  const order: Array<[string, ExportProfileIdSource]> = [
    ["bound_profile_id", "resume_source.bound_profile_id"],
    ["master_profile_id", "resume_source.master_profile_id"],
    ["profile_id", "resume_source.profile_id"],
  ];
  for (const [key, source] of order) {
    const value = idValue(src[key]);
    if (value) return { profileId: value, source, mode, isolation };
  }
  const fallback = idValue(mission && mission.profile_id);
  if (fallback) return { profileId: fallback, source: "mission.profile_id", mode, isolation };
  return { profileId: null, source: "none", mode, isolation };
}

// ---------------------------------------------------------------------------
// 2. classifyExperienceSection + honors
// ---------------------------------------------------------------------------

export type ExportSectionKey = "education_extra" | "campus" | "honors" | "project" | "work" | "other";

export const EXPORT_SECTION_LABELS: Record<ExportSectionKey, string> = {
  education_extra: "教育补充",
  campus: "校园经历",
  honors: "荣誉奖项",
  project: "项目经历",
  work: "工作/实习经历",
  other: "其他经历",
};

export type HonorEntry = {
  title?: string | null;
  level?: string | null;
  date?: string | null;
};

export type ExperienceClassification = {
  section: ExportSectionKey;
  label: string;
  /** type=显式 experience_type 命中；keyword=关键词规则；default=无法判断，按类型默认放置。 */
  rule: "type" | "keyword" | "default";
  /** false 表示无法自动归类（导出前检查会提示）。 */
  classified: boolean;
  /**
   * 进入「荣誉奖项」节的条目：section=honors 时为经历本身；其他节仅当是竞赛类经历且含获奖等级时给出
   * （经历本身仍留在原节，如竞赛项目留在项目经历）；否则 null。
   */
  honor: HonorEntry | null;
};

const TYPE_SECTIONS: Record<string, ExportSectionKey> = {
  work: "work",
  internship: "work",
  intern: "work",
  full_time: "work",
  part_time: "work",
  job: "work",
  employment: "work",
  campus: "campus",
  student: "campus",
  leadership: "campus",
  volunteer: "campus",
  activity: "campus",
  extracurricular: "campus",
  project: "project",
  side_project: "project",
  personal_project: "project",
  research: "project",
  education: "education_extra",
  school: "education_extra",
  degree: "education_extra",
  coursework: "education_extra",
  course: "education_extra",
  award: "honors",
  awards: "honors",
  honor: "honors",
  honors: "honors",
  competition: "honors",
};

const COURSEWORK_RE = /主修课程|主修|核心课程|相关课程|专业课程|课程/;
const CAMPUS_RE = /学生会|班委|班长|团支书|委员|社团|志愿|协会|团委|学生干部/;
const HONOR_TITLE_RE = /大赛|竞赛|比赛|挑战杯|奖|荣誉|获/;
const COMPETITION_TITLE_RE = /大赛|竞赛|比赛|挑战杯/;
const AWARD_LEVEL_RE = /(?:国家级|国际级|省级|市级|校级|院级|国家|省|市|校|院)?(?:特等|一等|二等|三等|金|银|铜|优胜|优秀)奖|冠军|亚军|季军/;
const PROJECT_RE = /项目|课题|研究|毕业设计|毕设/;
const WORK_RE = /实习|有限公司|公司|集团|工作室/;

function expTitle(exp: ExportExperience): string {
  return clean(exp.title);
}

function expText(exp: ExportExperience): string {
  return [clean(exp.title), clean(exp.organization), clean(exp.description)].filter(Boolean).join(" ");
}

/** 竞赛类经历（标题含 大赛/竞赛/比赛/挑战杯）且标题或描述含获奖等级 → 荣誉条目；否则 null。 */
export function extractHonorFromExperience(exp: ExportExperience): HonorEntry | null {
  const title = expTitle(exp);
  const type = normType(exp.experience_type);
  const isAwardType = TYPE_SECTIONS[type] === "honors";
  if (!title || (!isAwardType && !COMPETITION_TITLE_RE.test(title))) return null;
  const match = AWARD_LEVEL_RE.exec(expText(exp));
  if (!match && !isAwardType) return null;
  return { title, level: match ? match[0] : null, date: clean(exp.dates) || null };
}

function honorFromSelf(exp: ExportExperience): HonorEntry | null {
  const title = expTitle(exp);
  if (!title) return null;
  const match = AWARD_LEVEL_RE.exec(expText(exp));
  return { title, level: match ? match[0] : null, date: clean(exp.dates) || null };
}

function result(
  section: ExportSectionKey,
  rule: ExperienceClassification["rule"],
  classified: boolean,
  honor: HonorEntry | null,
): ExperienceClassification {
  return { section, label: EXPORT_SECTION_LABELS[section], rule, classified, honor };
}

/**
 * 归类规则（保守）：
 * 1. 显式 experience_type 命中已知类型 → 直接使用（PROJECT→项目经历，CAMPUS→校园经历，WORK/INTERNSHIP→工作/实习经历，
 *    EDUCATION/COURSEWORK→教育补充，AWARD/HONOR/COMPETITION→荣誉奖项）。
 * 2. 类型为 OTHER / 空 / 未知时按关键词，依次：
 *    教育补充（标题或描述含 主修课程/主修/课程…）→ 校园经历（学生会/班委/委员/社团/志愿…）→
 *    荣誉奖项（标题含 大赛/竞赛/比赛/奖/获…）→ 项目经历（项目/课题/研究…）→ 工作/实习经历（实习/公司…）。
 *    关键词命中荣誉但标题是竞赛且有已确认要点（opts.bulletCount>0）→ 视为竞赛项目，归项目经历。
 * 3. 都不命中 → classified=false，OTHER 放「其他经历」，空/未知类型放「工作/实习经历」（与现有导出默认一致）。
 * 竞赛类经历（无论归入哪节）只要含获奖等级（如 国家级一等奖），honor 字段给出荣誉条目，供「荣誉奖项」节额外展示；
 * 不含获奖等级的竞赛项目不进荣誉。
 */
export function classifyExperienceSection(
  exp: ExportExperience,
  opts: { bulletCount?: number } = {},
): ExperienceClassification {
  const type = normType(exp.experience_type);
  const honor = extractHonorFromExperience(exp);
  const typed = TYPE_SECTIONS[type];
  if (typed) return result(typed, "type", true, typed === "honors" ? honorFromSelf(exp) : honor);

  const title = expTitle(exp);
  const all = expText(exp);
  if (COURSEWORK_RE.test(title) || COURSEWORK_RE.test(clean(exp.description).slice(0, 12))) {
    return result("education_extra", "keyword", true, null);
  }
  if (CAMPUS_RE.test(title)) return result("campus", "keyword", true, honor);
  if (HONOR_TITLE_RE.test(title)) {
    if (COMPETITION_TITLE_RE.test(title) && (opts.bulletCount ?? 0) > 0) {
      return result("project", "keyword", true, honor);
    }
    return result("honors", "keyword", true, honorFromSelf(exp));
  }
  if (PROJECT_RE.test(all)) return result("project", "keyword", true, honor);
  if (WORK_RE.test(all)) return result("work", "keyword", true, honor);
  return result(type === "other" ? "other" : "work", "default", false, honor);
}

/** 教育补充行：把「主修课程」类经历合并成一行，如「主修课程：结构力学、海洋工程水文学」。 */
export function formatCourseworkLine(exp: ExportExperience): string {
  const title = clean(exp.title);
  const body = clean(exp.description).replace(/^(主修课程|核心课程|相关课程|专业课程|课程)\s*[:：]\s*/, "");
  const label = title && COURSEWORK_RE.test(title) ? title : "主修课程";
  if (!body) return title && title !== label ? title : "";
  return `${label}：${body}`;
}

export function formatHonorLine(honor: HonorEntry): string {
  const title = clean(honor.title);
  if (!title) return "";
  const level = clean(honor.level);
  const date = clean(honor.date);
  const main = level && title.indexOf(level) < 0 ? `${title} · ${level}` : title;
  return date ? `${main}（${date}）` : main;
}

function honorKey(title: string): string {
  return title.replace(/[\s·・\-—_，,。.]/g, "").toLowerCase();
}

/**
 * 「荣誉奖项」节：profile.honors 在前，经历派生的荣誉（classifyExperienceSection().honor）在后；
 * 按标题去重（同名时补全缺失的等级/日期）。传入 selections 时跳过 OMIT 的经历。
 * 返回空 lines 时该节不渲染。
 */
export function formatHonorsSection(input: {
  honors?: HonorEntry[] | null;
  experiences?: ExportExperience[] | null;
  selections?: ExportSelection[] | null;
}): { title: string; lines: string[] } {
  const merged: HonorEntry[] = [];
  const index: Record<string, number> = {};
  const add = (row: HonorEntry | null | undefined) => {
    if (!row) return;
    const title = clean(row.title);
    if (!title) return;
    const key = honorKey(title);
    const existing = index[key];
    if (existing === undefined) {
      index[key] = merged.length;
      merged.push({ title, level: clean(row.level) || null, date: clean(row.date) || null });
      return;
    }
    const prev = merged[existing];
    if (!prev.level && clean(row.level)) prev.level = clean(row.level);
    if (!prev.date && clean(row.date)) prev.date = clean(row.date);
  };
  for (const row of input.honors ?? []) add(row);
  for (const exp of input.experiences ?? []) {
    if (!exp || (exp.id && isOmitted(input.selections, exp.id))) continue;
    add(classifyExperienceSection(exp).honor);
  }
  return {
    title: EXPORT_SECTION_LABELS.honors,
    lines: merged.map(formatHonorLine).filter(Boolean),
  };
}

// ---------------------------------------------------------------------------
// 3. normalizeSkills
// ---------------------------------------------------------------------------

/** 已知技能的规范写法（按小写全称匹配）。 */
const SKILL_CASING: Record<string, string> = {
  python: "Python",
  matlab: "MATLAB",
  "c++": "C++",
  "c#": "C#",
  c: "C",
  java: "Java",
  javascript: "JavaScript",
  typescript: "TypeScript",
  sql: "SQL",
  mysql: "MySQL",
  autocad: "AutoCAD",
  revit: "Revit",
  supermap: "SuperMap",
  solidworks: "SolidWorks",
  excel: "Excel",
  word: "Word",
  powerpoint: "PowerPoint",
  ppt: "PPT",
  office: "Office",
  ansys: "ANSYS",
  abaqus: "ABAQUS",
  photoshop: "Photoshop",
  git: "Git",
};

/** 厂商前缀：去掉后核心相同即视为重复（如 MS Excel ≈ Excel）。 */
const VENDOR_PREFIX_RE = /^(ms|microsoft|autodesk|adobe)\s+/i;
const VENDOR_CASING: Record<string, string> = { ms: "MS", microsoft: "Microsoft", autodesk: "Autodesk", adobe: "Adobe" };

function canonicalSkill(raw: string): string {
  const lower = raw.toLowerCase();
  if (SKILL_CASING[lower]) return SKILL_CASING[lower];
  const prefix = VENDOR_PREFIX_RE.exec(raw);
  if (prefix) {
    const vendor = VENDOR_CASING[prefix[1].toLowerCase()] ?? prefix[1];
    const core = raw.slice(prefix[0].length);
    return `${vendor} ${SKILL_CASING[core.toLowerCase()] ?? core}`;
  }
  return raw;
}

function skillCoreKey(value: string): string {
  return value.replace(VENDOR_PREFIX_RE, "").replace(/\s+/g, "").toLowerCase();
}

/**
 * 技能规范化：
 * - trim、合并空白、丢弃空值与占位符（UNKNOWN / 未知 等）；
 * - 已知技能统一写法：python→Python，matlab→MATLAB，c++→C++，autocad→AutoCAD 等；厂商前缀 ms→MS；
 * - 大小写不敏感去重；去掉厂商前缀（MS/Microsoft/Autodesk/Adobe）后核心相同也视为重复；
 * - 重复时保留**首次出现**的那一项（位置与写法均取首个），顺序按首次出现。
 *   例：["MS Excel", "Excel"] → ["MS Excel"]；["Excel", "MS Excel"] → ["Excel"]。
 */
export function normalizeSkills(skills: Array<string | ExportSkill | null | undefined> | null | undefined): string[] {
  const out: string[] = [];
  const seen: Record<string, true> = {};
  for (const item of skills ?? []) {
    const raw = typeof item === "string" ? item : item ? String(item.name ?? "") : "";
    const value = clean(raw);
    if (!value) continue;
    const display = canonicalSkill(value);
    const key = skillCoreKey(display);
    if (!key || seen[key]) continue;
    seen[key] = true;
    out.push(display);
  }
  return out;
}

// ---------------------------------------------------------------------------
// 4. buildPreExportChecklist
// ---------------------------------------------------------------------------

// 词表以 apps/api resume_claim_guard.py 为准，需同步
export const NON_RESUME_PHRASES: readonly string[] = [
  "体现",
  "展现",
  "彰显",
  "可准备",
  "面试时",
  "面试中",
  "用于回应",
  "背景—工作—业绩",
  "背景-工作-业绩",
  "背景–工作–业绩",
  "背景→工作→业绩",
];

export type ExportChecksProfile = ExportProfile & {
  full_name?: string | null;
  /** 兼容旧字段，优先使用 full_name。 */
  name?: string | null;
  phone?: string | null;
  email?: string | null;
  city?: string | null;
  honors?: HonorEntry[] | null;
};

export type PreExportCheckItem = {
  level: "block" | "warn";
  code:
    | "missing_name"
    | "missing_phone"
    | "missing_email"
    | "non_resume_phrase"
    | "unclassified_experience"
    | "no_exportable_bullets";
  message: string;
  bulletId?: string;
  experienceId?: string;
  snippet?: string;
};

export type PreExportChecklistInput = {
  profile?: ExportChecksProfile | null;
  /** 缺省时使用 profile.experiences。 */
  experiences?: ExportExperience[] | null;
  bullets?: ExportBullet[] | null;
  selections?: ExportSelection[] | null;
};

export function resolveProfileName(profile: ExportChecksProfile | null | undefined): string {
  if (!profile) return "";
  return clean(profile.full_name) || clean(profile.name);
}

function exportableBulletText(bullet: ExportBullet): string {
  const status = String(bullet.status || "").toUpperCase();
  if (status !== "ACCEPTED" && status !== "EDITED") return "";
  return text(bullet.final_text) || text(bullet.suggested_text);
}

/** 从命中处截取到下一个句读（最多 40 字）作为提示片段。 */
function phraseSnippet(source: string, index: number): string {
  const rest = source.slice(index);
  const stop = rest.search(/[。；;！!？?\n]/);
  const piece = stop >= 0 ? rest.slice(0, stop) : rest;
  return piece.length > 40 ? `${piece.slice(0, 40)}…` : piece;
}

/** 返回首个命中的非简历话术及片段；未命中返回 null。 */
export function findNonResumePhrase(value: string): { phrase: string; snippet: string } | null {
  let best: { phrase: string; index: number } | null = null;
  for (const phrase of NON_RESUME_PHRASES) {
    const index = value.indexOf(phrase);
    if (index >= 0 && (!best || index < best.index)) best = { phrase, index };
  }
  if (!best) return null;
  return { phrase: best.phrase, snippet: phraseSnippet(value, best.index) };
}

/**
 * 导出前检查。block：阻止导出；warn：提示但可继续。
 * - 缺姓名 / 电话 / 邮箱 → warn（字段尚未上线时同样视为缺失）；
 * - 可导出要点（ACCEPTED/EDITED 且有文本，非幽灵经历、非 OMIT 经历）含 NON_RESUME_PHRASES → 每条 warn；
 * - 未被 OMIT 的经历无法自动归类 → warn；
 * - 没有任何可导出要点 → block。
 * 结果中 block 在前。
 */
export function buildPreExportChecklist(input: PreExportChecklistInput): PreExportCheckItem[] {
  const profile = input.profile ?? null;
  const experiences = input.experiences ?? (profile?.experiences as ExportExperience[] | undefined) ?? [];
  const selections = input.selections ?? [];
  const blocks: PreExportCheckItem[] = [];
  const warns: PreExportCheckItem[] = [];

  if (!resolveProfileName(profile)) {
    warns.push({ level: "warn", code: "missing_name", message: "缺少姓名，投递前请补充。" });
  }
  if (!clean(profile?.phone)) {
    warns.push({ level: "warn", code: "missing_phone", message: "缺少联系电话，投递前请补充。" });
  }
  if (!clean(profile?.email)) {
    warns.push({ level: "warn", code: "missing_email", message: "缺少邮箱，投递前请补充。" });
  }

  const known: Record<string, true> = {};
  for (const exp of experiences) if (exp && exp.id) known[exp.id] = true;
  const hasKnown = experiences.length > 0;

  const bulletCountByExp: Record<string, number> = {};
  let exportable = 0;
  for (const bullet of input.bullets ?? []) {
    const value = exportableBulletText(bullet);
    if (!value) continue;
    const sourceId = bullet.source_experience_id ? String(bullet.source_experience_id) : "";
    if (sourceId && hasKnown && !known[sourceId]) continue; // 幽灵经历不导出
    if (sourceId && isOmitted(selections, sourceId)) continue;
    exportable += 1;
    if (sourceId) bulletCountByExp[sourceId] = (bulletCountByExp[sourceId] ?? 0) + 1;
    const hit = findNonResumePhrase(value);
    if (hit) {
      warns.push({
        level: "warn",
        code: "non_resume_phrase",
        message: `要点含自评/面试话术「${hit.snippet}」，不适合直接写进简历，建议删改后再投递。`,
        bulletId: bullet.id,
        snippet: hit.snippet,
      });
    }
  }

  for (const exp of experiences) {
    if (!exp || !exp.id || isOmitted(selections, exp.id)) continue;
    const verdict = classifyExperienceSection(exp, { bulletCount: bulletCountByExp[exp.id] ?? 0 });
    if (verdict.classified) continue;
    const title = clean(exp.title) || clean(exp.organization) || "未命名经历";
    warns.push({
      level: "warn",
      code: "unclassified_experience",
      message: `经历「${title}」无法自动归类，将放入「${verdict.label}」，请确认。`,
      experienceId: exp.id,
    });
  }

  if (exportable <= 0) {
    blocks.push({
      level: "block",
      code: "no_exportable_bullets",
      message: "暂无已确认要点可导出，请先在目标简历中接受或编辑至少一条要点。",
    });
  }
  return blocks.concat(warns);
}

// ---------------------------------------------------------------------------
// 5. buildExportFileName
// ---------------------------------------------------------------------------

const WINDOWS_RESERVED_RE = /^(con|prn|aux|nul|com[1-9]|lpt[1-9])$/i;

function fileNamePart(value: unknown): string {
  let part = clean(value)
    .replace(/投递版/g, "")
    .replace(/[（(]\s*[)）]/g, "")
    .replace(/[\\/:*?"<>|\u0000-\u001f]/g, " ")
    .replace(/\s+/g, " ")
    .replace(/^[\s.\-]+|[\s.\-]+$/g, "")
    .trim();
  if (isPlaceholder(part)) return "";
  if (part.length > 40) part = part.slice(0, 40).trim();
  return part;
}

/**
 * 文件名：`姓名-公司-岗位`；缺失的部分省略；无姓名时以「简历」开头（`简历-公司-岗位`）。
 * 去除 Windows 非法字符 \ / : * ? " < > | 与控制字符、首尾点/空格、占位符；
 * 不含职级（不接收 seniority）且移除「投递版」字样。extension 可选（如 "pdf"）。
 */
export function buildExportFileName(input: {
  name?: string | null;
  company?: string | null;
  role?: string | null;
  extension?: string | null;
}): string {
  const name = fileNamePart(input.name);
  const parts = [name || "简历", fileNamePart(input.company), fileNamePart(input.role)].filter(Boolean);
  let base = parts.join("-");
  if (WINDOWS_RESERVED_RE.test(base)) base = `简历-${base}`;
  const ext = text(input.extension).replace(/^\.+/, "").replace(/[^A-Za-z0-9]/g, "");
  return ext ? `${base}.${ext}` : base;
}
