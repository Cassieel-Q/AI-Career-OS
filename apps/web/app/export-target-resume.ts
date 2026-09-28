/**
 * 投递版导出：把 target resume + profile 已有字段拼成打印友好 HTML。
 * 缺失节跳过，不造假数据。不改简历生成算法。
 */

export type ExportBullet = {
  id?: string;
  source_experience_id?: string | null;
  suggested_text?: string | null;
  final_text?: string | null;
  status?: string;
  risk_flags?: string[];
  sort_order?: number;
};

export type ExportExperience = {
  id: string;
  title?: string | null;
  organization?: string | null;
  dates?: string | null;
  description?: string | null;
  experience_type?: string | null;
};

export type ExportEducation = {
  id?: string;
  institution?: string | null;
  school?: string | null;
  degree?: string | null;
  field_of_study?: string | null;
  major?: string | null;
  dates?: string | null;
  relevant_courses?: string[] | null;
};

export type ExportSkill = {
  id?: string;
  name?: string | null;
};

export type ExportCertification = {
  id?: string;
  name?: string | null;
  issuer?: string | null;
  date?: string | null;
  score?: string | null;
};

export type ExportProfile = {
  profile_id?: string;
  full_name?: string | null;
  display_name?: string | null;
  name?: string | null;
  email?: string | null;
  phone?: string | null;
  location?: string | null;
  headline?: string | null;
  summary?: string | null;
  education?: ExportEducation[];
  skills?: Array<ExportSkill | string>;
  certifications?: ExportCertification[];
  experiences?: ExportExperience[];
};

export type ExportSelection = {
  experience_id: string;
  decision: string;
};

export type ExportTargetResume = {
  version?: number;
  positioning_statement?: string | null;
  recommended_experience_order?: string[];
  /** Original top-level resume sections, in source order when extraction supplied it. */
  section_order?: string[];
  bullets: ExportBullet[];
};

export type BuildExportHtmlInput = {
  company: string;
  role: string;
  seniority?: string | null;
  targetResume: ExportTargetResume;
  profile?: ExportProfile | null;
  experiences?: ExportExperience[];
  selections?: ExportSelection[];
};

const WORK_TYPES = new Set(["work", "internship", "full_time", "part_time", "job", "employment"]);
const PROJECT_TYPES = new Set(["project", "side_project", "personal_project"]);
const CAMPUS_TYPES = new Set(["campus", "student", "leadership", "volunteer", "activity", "extracurricular"]);
const EDUCATION_TYPES = new Set(["education", "school", "degree"]);
const SKILL_TYPES = new Set(["skill", "skills"]);


function isPlaceholder(value: unknown): boolean {
  const text = String(value ?? "").trim();
  if (!text) return true;
  const folded = text.toLowerCase();
  // Align with mission-state isUnknownIdentity. Printable export omits placeholders (no UNKNOWN / no 待确认 on PDF).
  if (
    folded === "unknown" ||
    folded === "n/a" ||
    folded === "none" ||
    folded === "null" ||
    folded === "undefined" ||
    folded === "未知"
  ) {
    return true;
  }
  if (/\bunknown\b/i.test(text)) return true;
  return false;
}

function cleanLabel(value: unknown): string {
  let text = String(value ?? "").trim();
  if (!text || isPlaceholder(text)) return "";
  text = text
    .replace(/\[DOGFOOD\]/gi, "")
    .replace(/\bSynthetic\b/gi, "")
    .replace(/\s{2,}/g, " ")
    .replace(/^[\-\u00b7|:\s]+|[\-\u00b7|:\s]+$/g, "")
    .trim();
  return isPlaceholder(text) ? "" : text;
}

function looksLikeModelMeta(value: string): boolean {
  const text = value.toLowerCase();
  return (
    text.includes("every claim must") ||
    text.includes("evidence refs") ||
    text.includes("must be handled as gaps") ||
    text.includes("supplied evidence") ||
    text.includes("do not invent") ||
    text.includes("不要编造")
  );
}

function escapeHtml(value: unknown): string {
  return String(value ?? "")
    .replace(/&/g, "&amp;")
    .replace(/</g, "&lt;")
    .replace(/>/g, "&gt;")
    .replace(/"/g, "&quot;");
}

function normType(value: unknown): string {
  return String(value ?? "")
    .trim()
    .toLowerCase()
    .replace(/[\s-]+/g, "_");
}

function isOmitted(selections: ExportSelection[] | undefined, experienceId: string): boolean {
  const row = (selections ?? []).find((item) => item.experience_id === experienceId);
  return Boolean(row && String(row.decision).toUpperCase() === "OMIT");
}

function confirmedBulletText(bullet: ExportBullet): string {
  // Confirmed export: prefer user final_text; ACCEPTED may only have suggested_text.
  const final = String(bullet.final_text || "").trim();
  if (final) return final;
  return String(bullet.suggested_text || "").trim();
}

function bulletText(bullet: ExportBullet): string {
  return confirmedBulletText(bullet);
}

function isExportableBulletStatus(status: unknown): boolean {
  const folded = String(status || "").toUpperCase();
  return folded === "ACCEPTED" || folded === "EDITED";
}

/** 投递版只出用户已接受/已编辑主张；SUGGESTED / REJECTED / 未确认不进。 */
function activeBullets(resume: ExportTargetResume): ExportBullet[] {
  return (resume.bullets ?? [])
    .filter((bullet) => isExportableBulletStatus(bullet.status))
    .filter((bullet) => {
      const flags = (bullet.risk_flags ?? []).map((flag) => String(flag).toUpperCase());
      const needsFact = flags.includes("SYNTHETIC_PROJECT") || flags.includes("GROUNDING:NEEDS_CONFIRMATION");
      return !needsFact || flags.includes("FACT_CONFIRMED");
    })
    .filter((bullet) => Boolean(bulletText(bullet)))
    .slice()
    .sort((a, b) => (a.sort_order ?? 0) - (b.sort_order ?? 0));
}

function contactName(profile?: ExportProfile | null): string {
  return cleanLabel(profile?.full_name || profile?.display_name || profile?.name || "");
}

function contactLine(profile?: ExportProfile | null): string {
  if (!profile) return "";
  return [profile.email, profile.phone, profile.location]
    .map((part) => String(part || "").trim())
    .filter(Boolean)
    .join(" · ");
}

function skillName(skill: ExportSkill | string): string {
  if (typeof skill === "string") return skill.trim();
  return String(skill?.name || "").trim();
}

function educationLine(row: ExportEducation): string {
  const school = cleanLabel(row.institution || row.school);
  const degree = cleanLabel(row.degree);
  const field = cleanLabel(row.field_of_study || row.major);
  const dates = cleanLabel(row.dates);
  const left = [school, [degree, field].filter(Boolean).join(" · ")].filter(Boolean).join(" — ");
  return [left, dates].filter(Boolean).join(" · ");
}

function experienceHeading(exp: ExportExperience | undefined, fallbackId?: string): string {
  if (!exp) return "经历";
  const title = cleanLabel(exp.title);
  const org = cleanLabel(exp.organization);
  const dates = cleanLabel(exp.dates);
  const main = [title, org].filter(Boolean).join(" · ") || "经历";
  return dates ? `${main}（${dates}）` : main;
}

function bucketExperiences(experiences: ExportExperience[]): {
  work: ExportExperience[];
  projects: ExportExperience[];
  educationAsExp: ExportExperience[];
  skillsAsExp: ExportExperience[];
  other: ExportExperience[];
  campus: ExportExperience[];
} {
  const work: ExportExperience[] = [];
  const projects: ExportExperience[] = [];
  const educationAsExp: ExportExperience[] = [];
  const skillsAsExp: ExportExperience[] = [];
  const other: ExportExperience[] = [];
  const campus: ExportExperience[] = [];
  for (const exp of experiences) {
    const t = normType(exp.experience_type);
    if (WORK_TYPES.has(t) || t === "") {
      // empty type: treat as work-like only if it has org/title typical of jobs; still default work
      work.push(exp);
    } else if (CAMPUS_TYPES.has(t)) {
      campus.push(exp);
    } else if (PROJECT_TYPES.has(t)) {
      projects.push(exp);
    } else if (EDUCATION_TYPES.has(t)) {
      educationAsExp.push(exp);
    } else if (SKILL_TYPES.has(t)) {
      skillsAsExp.push(exp);
    } else if (t === "other") {
      other.push(exp);
    } else {
      // unknown types stay with work so we do not drop confirmed content
      work.push(exp);
    }
  }
  return { work, projects, educationAsExp, skillsAsExp, other, campus };
}

function orderIds(resume: ExportTargetResume, experiences: ExportExperience[]): string[] {
  const known = new Set(experiences.map((item) => item.id));
  const ordered = (resume.recommended_experience_order ?? []).filter((id) => known.has(id));
  const seen = new Set(ordered);
  for (const exp of experiences) {
    if (!seen.has(exp.id)) {
      ordered.push(exp.id);
      seen.add(exp.id);
    }
  }
  return ordered;
}

function sectionHtml(title: string, body: string): string {
  if (!body.trim()) return "";
  return `<section class="sec"><h2>${escapeHtml(title)}</h2>${body}</section>`;
}

function renderExperienceBlocks(
  ids: string[],
  expMap: Map<string, ExportExperience>,
  bulletsByExp: Map<string, string[]>,
  orphanLines: string[],
  selections: ExportSelection[] | undefined,
): string {
  const parts: string[] = [];
  for (const id of ids) {
    if (isOmitted(selections, id)) continue;
    const lines = bulletsByExp.get(id) ?? [];
    const exp = expMap.get(id);
    const desc = String(exp?.description || "").trim();
    if (!lines.length && !desc) continue;
    const lis = (lines.length ? lines : desc ? [desc] : []).map((line) => `<li>${escapeHtml(line)}</li>`).join("");
    parts.push(`<article class="exp"><h3>${escapeHtml(experienceHeading(exp, id))}</h3><ul>${lis}</ul></article>`);
  }
  if (orphanLines.length) {
    parts.push(
      `<article class="exp"><h3>${escapeHtml("补充要点")}</h3><ul>${orphanLines
        .map((line) => `<li>${escapeHtml(line)}</li>`)
        .join("")}</ul></article>`,
    );
  }
  return parts.join("");
}

/** 纯函数：生成投递版 HTML（含 @media print）。 */

/** User-facing copy after opening the printable export window. */
/** Count bullets that would appear in the printable export. */
export function countExportableBullets(resume: ExportTargetResume, knownExperienceIds?: ReadonlySet<string> | string[]): number {
  const known = knownExperienceIds
    ? knownExperienceIds instanceof Set
      ? knownExperienceIds
      : new Set(knownExperienceIds)
    : null;
  return activeBullets(resume).filter((bullet) => {
    const sourceId = bullet.source_experience_id ? String(bullet.source_experience_id) : "";
    if (!sourceId) return true;
    if (!known) return true;
    return known.has(sourceId);
  }).length;
}

/** Short status line for the always-on export entry (not a download promise). */
export function exportEntryHint(exportableCount: number): string {
  if (exportableCount <= 0) {
    return "投递版导出：仅含已接受 / 已编辑要点。当前还没有可导出内容，请先确认目标简历要点。";
  }
  return `投递版导出：将用浏览器打印另存 PDF（不是后台自动下载）。当前可导出 ${exportableCount} 条已确认要点。`;
}

export function exportEmptyContentFeedback(): { tone: "error"; message: string } {
  return {
    tone: "error",
    message: "暂无已确认要点可导出。请先在目标简历中接受或编辑至少一条要点。",
  };
}

export function exportPrintWindowFeedback(opened: boolean): { tone: "ok" | "error"; message: string } {
  if (!opened) {
    return {
      tone: "error",
      message: "浏览器拦截了导出窗口，请允许弹窗后重试。",
    };
  }
  return {
    tone: "ok",
    message:
      "已打开投递版预览（尚未保存文件）。请在打印对话框选择「另存为 PDF」；关闭打印窗不会自动下载。",
  };
}

export function buildTargetResumeExportHtml(input: BuildExportHtmlInput): string {
  const resume = input.targetResume;
  const profile = input.profile ?? null;
  const experiences = [...(input.experiences ?? []), ...((profile?.experiences as ExportExperience[]) ?? [])];
  // de-dupe by id, prefer first
  const expMap = new Map<string, ExportExperience>();
  for (const exp of experiences) {
    if (exp?.id && !expMap.has(exp.id)) expMap.set(exp.id, exp);
  }
  const uniqueExperiences = Array.from(expMap.values());
  const buckets = bucketExperiences(uniqueExperiences);
  const bullets = activeBullets(resume);

  const bulletsByExp = new Map<string, string[]>();
  const orphanLines: string[] = [];
  const syntheticProjectLines: string[] = [];
  for (const bullet of bullets) {
    const text = bulletText(bullet);
    const sourceId = bullet.source_experience_id ? String(bullet.source_experience_id) : "";
    // Ghost / foreign experience ids: drop (do not print as orphans).
    if (sourceId && !expMap.has(sourceId)) continue;
    if (sourceId) {
      const list = bulletsByExp.get(sourceId) ?? [];
      list.push(text);
      bulletsByExp.set(sourceId, list);
    } else {
      if ((bullet.risk_flags ?? []).some((flag) => String(flag).toUpperCase() === "SYNTHETIC_PROJECT")) {
        syntheticProjectLines.push(text);
      } else {
        orphanLines.push(text);
      }
    }
  }

  const workAndOther = [...buckets.work, ...buckets.other];
  const workIds = orderIds(resume, workAndOther).filter((id) => workAndOther.some((e) => e.id === id));
  // Keep project ids that either have bullets or are not OMIT
  const projectIds = orderIds(resume, buckets.projects).filter((id) => buckets.projects.some((e) => e.id === id));
  const campusIds = orderIds(resume, buckets.campus).filter((id) => buckets.campus.some((e) => e.id === id));

  const name = contactName(profile);
  const contacts = contactLine(profile);
  const headline = cleanLabel(profile?.headline);
  // 投递版不导出「摘要」：以用户上传的教育/经历为主，避免模型把写作约束写进摘要。

  const experienceBody = renderExperienceBlocks(workIds, expMap, bulletsByExp, orphanLines, input.selections);
  const rendered = new Set(workIds.filter((id) => !isOmitted(input.selections, id)));
  const projectOnlyIds = projectIds.filter((id) => !rendered.has(id));
  const projectBody = [
    renderExperienceBlocks(projectOnlyIds, expMap, bulletsByExp, [], input.selections),
    syntheticProjectLines.length
      ? `<article class="exp"><h3>${escapeHtml("项目草案")}</h3><ul>${syntheticProjectLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("")}</ul></article>`
      : "",
  ].join("");
  const campusBody = renderExperienceBlocks(campusIds, expMap, bulletsByExp, [], input.selections);

  const educationLines: string[] = [];
  for (const row of profile?.education ?? []) {
    const line = educationLine(row);
    if (line) educationLines.push(line);
  }
  for (const exp of buckets.educationAsExp) {
    if (isOmitted(input.selections, exp.id)) continue;
    // Prefer uploaded resume text (title/org/dates + description) with light cleanup only.
    const heading = experienceHeading(exp);
    const detail = cleanLabel(exp.description);
    const line = detail && heading && heading !== "经历"
      ? `${heading} — ${detail}`
      : detail || (heading !== "经历" ? heading : "");
    if (line) educationLines.push(line);
  }
  const educationBody = educationLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("");

  const skillLines: string[] = [];
  for (const skill of profile?.skills ?? []) {
    const nameText = cleanLabel(skillName(skill));
    if (nameText && !skillLines.some((item) => item.replace(/^MS\s+/i, "").toLowerCase() === nameText.replace(/^MS\s+/i, "").toLowerCase())) skillLines.push(nameText);
  }
  for (const exp of buckets.skillsAsExp) {
    if (isOmitted(input.selections, exp.id)) continue;
    const label = cleanLabel(exp.title || exp.description);
    if (label && !skillLines.some((item) => item.toLowerCase() === label.toLowerCase())) skillLines.push(label);
  }
  const skillsBody = skillLines.length
    ? `<p class="skills">${skillLines.map((line) => escapeHtml(line)).join(" · ")}</p>`
    : "";

  const certLines = (profile?.certifications ?? [])
    .map((row) => {
      const bits = [row.name, row.issuer, row.date, row.score].map((v) => cleanLabel(v)).filter(Boolean);
      return bits.join(" · ");
    })
    .filter(Boolean);
  const certBody = certLines.map((line) => `<li>${escapeHtml(line)}</li>`).join("");

  const company = cleanLabel(input.company);
  const role = cleanLabel(input.role);
  const seniority = cleanLabel(input.seniority);
  const title = [company, role].filter(Boolean).join(" · ") || "投递版简历";
  const roleLine = [role, company, seniority].filter(Boolean).join(" · ");

  const header = `
    <header class="hdr">
      ${name ? `<h1>${escapeHtml(name)}</h1>` : ""}
      ${contacts ? `<p class="contact">${escapeHtml(contacts)}</p>` : ""}
      ${headline ? `<p class="headline">${escapeHtml(headline)}</p>` : ""}
      ${roleLine ? `<p class="meta">投递目标：${escapeHtml(roleLine)}</p>` : ""}
    </header>`;

  const hasResumeSections = Boolean(
    experienceBody || projectBody || campusBody || educationBody || skillsBody || certBody
  );
  const sectionBodies: Record<string, string> = {
    education: educationBody ? sectionHtml("教育", `<ul>${educationBody}</ul>`) : "",
    experience: experienceBody ? sectionHtml("经历", experienceBody) : "",
    project: projectBody ? sectionHtml("项目", projectBody) : "",
    campus: campusBody ? sectionHtml("校园经历", campusBody) : "",
    skills: skillsBody ? sectionHtml("技能", skillsBody) : "",
    certifications: certBody ? sectionHtml("证书", `<ul>${certBody}</ul>`) : "",
  };
  const aliases: Record<string, string> = {
    school: "education",
    degree: "education",
    work: "experience",
    internship: "experience",
    internships: "experience",
    projects: "project",
    skill: "skills",
    certification: "certifications",
    certificates: "certifications",
    campus: "campus",
  };
  const requestedOrder = (resume.section_order ?? [])
    .map((value) => String(value ?? "").trim().toLowerCase().replace(/[\s_-]+/g, ""))
    .map((value) => aliases[value] ?? value)
    .filter((value) => value in sectionBodies);
  const sectionOrder = Array.from(new Set([
    ...(requestedOrder.length ? requestedOrder : ["education", "experience", "project", "campus", "skills", "certifications"]),
    "education",
    "experience",
    "project",
    "campus",
    "skills",
    "certifications",
  ]));
  const body = [
    header,
    ...sectionOrder.map((key) => sectionBodies[key]).filter(Boolean),
    hasResumeSections ? "" : "<p>暂无可用的投递内容。</p>",
  ].filter(Boolean).join("\n");

  return `<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>${escapeHtml(title)} · 投递版</title>
  <style>
    :root { color-scheme: light; }
    * { box-sizing: border-box; }
    body {
      font-family: "Noto Sans SC", "Microsoft YaHei", "PingFang SC", sans-serif;
      color: #111;
      background: #fff;
      margin: 0;
      padding: 16px 20px 24px;
      line-height: 1.45;
      font-size: 11.5pt;
    }
    .sheet { max-width: 780px; margin: 0 auto; }
    .hdr { margin: 0 0 10px; padding-bottom: 8px; border-bottom: 1px solid #ddd; }
    h1 { font-size: 18pt; margin: 0 0 4px; font-weight: 700; }
    h2 {
      font-size: 11pt;
      margin: 12px 0 6px;
      padding-bottom: 2px;
      border-bottom: 1px solid #e5e5e5;
      text-transform: none;
      letter-spacing: 0.02em;
      color: #222;
    }
    h3 { font-size: 10.5pt; margin: 0 0 2px; font-weight: 600; }
    .contact, .headline, .meta { margin: 2px 0; color: #444; font-size: 9.5pt; }
    .summary { margin: 0; }
    .sec { margin: 0; }
    .exp { margin: 0 0 8px; }
    ul { margin: 2px 0 0 1.1em; padding: 0; }
    li { margin: 1px 0; }
    .skills { margin: 0; }
    @media print {
      @page { margin: 12mm 14mm; }
      body { padding: 0; font-size: 10.5pt; }
      .hdr { border-bottom-color: #bbb; }
      h2 { break-after: avoid; }
      .exp { break-inside: avoid; }
      a { color: inherit; text-decoration: none; }
    }
  </style>
</head>
<body>
  <div class="sheet">
    ${body}
  </div>
  <script>window.onload=function(){window.print()}</script>
</body>
</html>`;
}
