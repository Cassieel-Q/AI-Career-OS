/**
 * 版式控制（目标五）· 纯逻辑。
 *
 * 与后端 `resume_layout.normalize_layout_config` 保持同一套白名单与夹取范围，
 * 前端控件只提交受限字段，绝不写任意 HTML；`set_layout` 操作让 Preview / PDF / Word /
 * Markdown 共用同一份配置。
 */
import type { LayoutConfig } from "./types.ts";

export const DEFAULT_LAYOUT: LayoutConfig = {
  template: "zh-classic",
  page_limit: 1,
  font_scale: 1.0,
  line_height: 1.5,
  section_gap: 12,
  columns: 1,
  accent_color: "#111111",
  photo_enabled: false,
  section_order: ["education", "experience", "projects", "honors", "skills"],
};

export const SECTION_LABELS: Record<string, string> = {
  education: "教育经历",
  experience: "工作与项目经历",
  projects: "项目经历",
  honors: "荣誉奖项",
  skills: "技能",
  certificates: "证书",
};

const clamp = (value: number, low: number, high: number) => Math.min(high, Math.max(low, value));

/** 与后端一致的归一化（含默认值补齐、范围夹取、颜色白名单）。 */
export function normalizeLayout(raw: Partial<LayoutConfig> | null | undefined): LayoutConfig {
  const data: LayoutConfig = { ...DEFAULT_LAYOUT, ...(raw ?? {}) };
  data.template = String(data.template || DEFAULT_LAYOUT.template).slice(0, 64);
  data.page_limit = clamp(Math.round(Number(data.page_limit) || 1), 1, 5);
  data.font_scale = clamp(Number(data.font_scale) || 1, 0.6, 1.6);
  data.line_height = clamp(Number(data.line_height) || 1.5, 1.0, 2.5);
  data.section_gap = clamp(Math.round(Number(data.section_gap) || 0), 0, 48);
  data.columns = clamp(Math.round(Number(data.columns) || 1), 1, 2);
  data.photo_enabled = Boolean(data.photo_enabled);
  data.accent_color = /^#[0-9a-fA-F]{6}$/.test(String(data.accent_color)) ? String(data.accent_color) : DEFAULT_LAYOUT.accent_color;
  const order = Array.isArray(data.section_order) ? data.section_order : DEFAULT_LAYOUT.section_order;
  const cleaned = Array.from(new Set(order.map((item) => String(item).trim().toLowerCase()).filter(Boolean)));
  data.section_order = cleaned.length ? cleaned : [...DEFAULT_LAYOUT.section_order];
  return data;
}

/** 把某个栏目在顺序里上下移动一格，返回新的 section_order。 */
export function moveSection(order: string[], kind: string, direction: -1 | 1): string[] {
  const next = [...order];
  const index = next.indexOf(kind);
  if (index < 0) return next;
  const target = index + direction;
  if (target < 0 || target >= next.length) return next;
  [next[index], next[target]] = [next[target], next[index]];
  return next;
}

export function sectionLabel(kind: string): string {
  return SECTION_LABELS[kind] ?? kind;
}

/** 构造 set_layout 操作（仅提交改动字段）。 */
export function layoutOperation(patch: Partial<LayoutConfig>) {
  return { type: "set_layout" as const, layout_config: normalizeLayout(patch as LayoutConfig) };
}
