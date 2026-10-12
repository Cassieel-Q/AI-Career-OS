import assert from "node:assert/strict";
import { test } from "node:test";
import { DEFAULT_LAYOUT, layoutOperation, moveSection, normalizeLayout, sectionLabel } from "../app/resume-studio/layout-config.ts";

test("normalizeLayout mirrors the backend whitelist and clamps", () => {
  const layout = normalizeLayout({ accent_color: "red", font_scale: 9, columns: 5, section_order: ["Skills", "skills", "education"] });
  assert.equal(layout.accent_color, DEFAULT_LAYOUT.accent_color);
  assert.equal(layout.font_scale, 1.6);
  assert.equal(layout.columns, 2);
  assert.deepEqual(layout.section_order, ["skills", "education"]);
});

test("normalizeLayout fills missing fields with defaults", () => {
  const layout = normalizeLayout({});
  assert.deepEqual(layout, DEFAULT_LAYOUT);
});

test("moveSection swaps neighbours and clamps at the ends", () => {
  const order = ["education", "experience", "skills"];
  assert.deepEqual(moveSection(order, "experience", -1), ["experience", "education", "skills"]);
  assert.deepEqual(moveSection(order, "education", -1), order);
  assert.deepEqual(moveSection(order, "skills", 1), order);
  assert.deepEqual(moveSection(order, "projects", 1), order);
});

test("layoutOperation emits a normalized set_layout operation", () => {
  const op = layoutOperation({ columns: 2, accent_color: "#00ff00" });
  assert.equal(op.type, "set_layout");
  assert.equal(op.layout_config.columns, 2);
  assert.equal(op.layout_config.accent_color, "#00ff00");
  assert.deepEqual(op.layout_config.section_order, DEFAULT_LAYOUT.section_order);
});

test("sectionLabel falls back to the raw kind", () => {
  assert.equal(sectionLabel("education"), "教育经历");
  assert.equal(sectionLabel("unknown_kind"), "unknown_kind");
});
