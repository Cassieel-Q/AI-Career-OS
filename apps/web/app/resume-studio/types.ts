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
  revision: number;
  confirmed_revision: number | null;
  language: "zh" | "en";
  template_id: string;
  document: StudioDocument;
};
export type StudioTemplate = {
  id: string;
  language: "zh" | "en";
  name: string;
  family: string;
  description: string;
  [key: string]: unknown;
};
export type StudioCheck = { level: "block" | "warn"; code: string; node_id?: string; message: string };
export type StudioPreview = {
  revision: number;
  template_id: string;
  page_count: number;
  pages: string[];
  layout_map: { id: string; page: number; x: number; y: number; width: number; height: number }[];
  checks: StudioCheck[];
};
export type StudioOperation =
  | { type: "set_text"; node_id: string; text: string }
  | { type: "add_entry"; section_id: string; title: string }
  | { type: "add_bullet"; entry_id: string; text: string }
  | { type: "omit" | "restore" | "confirm_fact"; node_id: string }
  | { type: "move"; node_id: string; before_id?: string }
  | { type: "set_template"; template_id: string }
  | { type: "set_language"; language: "zh" | "en" }
  | { type: "set_evidence"; node_id: string; evidence_refs: string[] };
