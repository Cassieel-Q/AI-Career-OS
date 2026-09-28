/** Pure helpers for experience-selection copy — keep out of missions.ts client API module. */

export type ExperienceDecision = "KEEP_AND_HIGHLIGHT" | "KEEP" | "DEEMPHASIZE" | "OMIT";

/** Keep decision chip and explanatory why text consistent (esp. OMIT vs 建议保留). */
export function alignedExperienceWhy(
  decision: ExperienceDecision,
  why: string | null | undefined,
  experienceLabel = "这段经历",
): string {
  const cleaned = String(why || "").trim();
  const label = (experienceLabel || "这段经历").trim() || "这段经历";
  const keepTone = /建议保留|建议突出|重点展示|写进核心|保留并突出/.test(cleaned);
  const omitTone = /暂不放入|不放入|不展示|建议排除|关联较弱/.test(cleaned);
  if (decision === "OMIT") {
    if (!cleaned || keepTone) {
      return `与当前岗位关联较弱，这份岗位简历暂不放入「${label}」（不会删除原简历）。`;
    }
    return cleaned;
  }
  if (decision === "DEEMPHASIZE") {
    if (!cleaned || omitTone || (keepTone && /重点展示|保留并突出/.test(cleaned))) {
      return `与岗位有一定关联，但「${label}」在这份简历里弱化处理即可。`;
    }
    return cleaned;
  }
  if (omitTone || !cleaned) {
    return decision === "KEEP_AND_HIGHLIGHT"
      ? `与目标岗位相关，建议重点展示「${label}」中可验证的成果与职责。`
      : `与目标岗位相关，建议保留「${label}」。`;
  }
  return cleaned;
}

/** User-facing title when experience_id is missing from the current resume-source profile. */
export function missingExperienceLabel(): string {
  return "未知经历（不在当前简历来源中）";
}

/** True when id is in the allowed set (current profile experiences). */
export function isKnownExperienceId(experienceId: string | null | undefined, knownIds: Iterable<string>): boolean {
  if (experienceId == null || experienceId === "") return false;
  const set = knownIds instanceof Set ? knownIds : new Set(knownIds);
  return set.has(experienceId);
}
