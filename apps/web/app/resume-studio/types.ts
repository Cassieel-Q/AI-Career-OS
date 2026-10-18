export type FactStatus = "CONFIRMED" | "NEEDS_CONFIRMATION" | "BLOCKED_MISSING" | "OMITTED";
export type StudioNode = {
  id: string;
  text: string;
  source_kind: string;
  source_id: string | null;
  evidence_refs: string[];
  risk_level: "LOW" | "HIGH";
  claim_status: FactStatus;
};
export type StudioEntry = {
  id: string;
  status: "INCLUDED" | "OMITTED";
  title: StudioNode;
  subtitle: StudioNode;
  date: StudioNode;
  location: StudioNode;
  bullets: StudioNode[];
};
export type StudioSection = { id: string; kind: string; title: StudioNode; entries: StudioEntry[] };
export type StudioDocument = {
  schema_version: number;
  basics: Record<string, StudioNode>;
  sections: StudioSection[];
};
export type StudioState = {
  id: string;
  mission_id: string;
  source_target_resume_id: string;
  revision: number;
  confirmed_revision: number | null;
  language: "zh" | "en";
  template_id: string;
  layout_config?: LayoutConfig;
  document: StudioDocument;
};
/** 版式配置（目标五）：Preview / PDF / Word / Markdown 共用同一份。 */
export type LayoutConfig = {
  template: string;
  page_limit: number;
  font_scale: number;
  line_height: number;
  section_gap: number;
  columns: number;
  accent_color: string;
  photo_enabled: boolean;
  section_order: string[];
};
export type StudioTemplate = {
  id: string;
  language: "zh" | "en";
  name: string;
  family: string;
  description: string;
  [key: string]: unknown;
};
export type StudioCheck = { level: "block" | "warn" | "info"; code: string; node_id?: string; message: string };
export type StudioPreview = {
  revision: number;
  template_id: string;
  page_count: number;
  pages: string[];
  layout_map: { id: string; page: number; x: number; y: number; width: number; height: number }[];
  /** 草稿口径：未核对内容只提示。 */
  checks: StudioCheck[];
  /** 正式投递口径：姓名 / 联系方式 / 高风险未核对事实会阻塞确认与正式导出。 */
  final_checks?: StudioCheck[];
};
export type StudioSourceDiffSection = {
  section: string;
  status: "added" | "removed" | "changed" | "unchanged";
  added: string[];
  removed: string[];
  kept: number;
};

export type StudioSourceDiff = {
  update_available: boolean;
  current_source_id: string;
  new_source_id?: string;
  new_source_version?: number;
  added_bullets?: string[];
  removed_bullets?: string[];
  sections?: StudioSourceDiffSection[];
  manual_edit_count?: number;
  manual_edit_samples?: string[];
  will_replace_studio_edits?: boolean;
  will_reset_language?: boolean;
};
export type StudioOperation =
  | { type: "set_text"; node_id: string; text: string }
  | { type: "add_entry"; section_id: string; title: string }
  | { type: "add_bullet"; entry_id: string; text: string }
  | { type: "omit" | "restore" | "confirm_fact"; node_id: string }
  | { type: "move"; node_id: string; before_id?: string }
  | { type: "set_template"; template_id: string }
  | { type: "set_language"; language: "zh" | "en" }
  | { type: "set_evidence"; node_id: string; evidence_refs: string[] }
  | { type: "set_layout"; layout_config: Partial<LayoutConfig> };
