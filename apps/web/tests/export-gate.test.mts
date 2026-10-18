import assert from "node:assert/strict";
import { test } from "node:test";
import { downloadStudioPdf, filenameFromHeaders } from "../app/resume-studio/api.ts";
import { deliveryGate } from "../app/resume-studio/export-gate.ts";
import type { StudioCheck, StudioPreview, StudioState } from "../app/resume-studio/types.ts";

const node = (id: string, text: string) => ({ id, text, source_kind: "profile", source_id: null, evidence_refs: [], risk_level: "LOW" as const, claim_status: "CONFIRMED" as const });
const state = (revision: number, confirmed: number | null): StudioState => ({
  id: "s", mission_id: "m", source_target_resume_id: "source", revision, confirmed_revision: confirmed, language: "zh", template_id: "zh-classic",
  document: { schema_version: 1, basics: { name: node("n", "陈林") }, sections: [] },
});
const check = (level: StudioCheck["level"], code: string, message = "提示"): StudioCheck => ({ level, code, message });
const preview = (checks: StudioCheck[], finalChecks: StudioCheck[]): StudioPreview => ({
  revision: 3, template_id: "zh-classic", page_count: 1, pages: [], layout_map: [], checks, final_checks: finalChecks,
});

test("filename prefers the server-provided header and falls back safely", () => {
  assert.equal(filenameFromHeaders(new Headers({ "X-Resume-Filename": "Ada%20Lin_Acme_PM_v2.pdf" }), "resume.pdf"), "Ada Lin_Acme_PM_v2.pdf");
  assert.equal(
    filenameFromHeaders(new Headers({ "Content-Disposition": "attachment; filename*=UTF-8''Ada%20Lin_v1_DRAFT.pdf" }), "resume.pdf"),
    "Ada Lin_v1_DRAFT.pdf",
  );
  assert.equal(filenameFromHeaders(new Headers(), "resume_DRAFT.pdf"), "resume_DRAFT.pdf");
});

test("draft PDF goes through the draft query and keeps the DRAFT filename", async () => {
  const urls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url) => {
    urls.push(String(url));
    return new Response(new Blob(["%PDF-fake"]), { headers: { "X-Resume-Filename": "Ada%20Lin_v3_DRAFT.pdf", "X-Resume-Draft": "1" } });
  }) as typeof fetch;
  try {
    const draft = await downloadStudioPdf("m", true);
    assert.match(urls[0], /\/pdf\?draft=1$/);
    assert.equal(draft.draft, true);
    assert.equal(draft.filename, "Ada Lin_v3_DRAFT.pdf");

    const final = await downloadStudioPdf("m");
    assert.equal(urls[1].endsWith("/pdf"), true);
    assert.equal(final.draft, false);
  } finally { globalThis.fetch = original; }
});

test("formal delivery blocks on high-risk unconfirmed facts while draft stays available", () => {
  const gate = deliveryGate(
    state(3, null),
    preview([check("warn", "unconfirmed_fact")], [check("block", "unconfirmed_fact"), check("info", "long_resume")]),
  );
  assert.equal(gate.blocks.length, 1);
  assert.equal(gate.draftBlocks.length, 0);
  assert.equal(gate.canConfirm, false);
  assert.equal(gate.canDownloadFinal, false);
  // 草稿随时可导出用于自我审阅
  assert.equal(gate.canDownloadDraft, true);
});

test("confirmed revision with no blocking checks unlocks the formal PDF", () => {
  const gate = deliveryGate(state(3, 3), preview([], [check("warn", "unconfirmed_fact")]));
  assert.equal(gate.canConfirm, true);
  assert.equal(gate.canDownloadFinal, true);
  assert.equal(gate.warns.length, 1);
});

test("placeholder residue blocks even the draft export", () => {
  const gate = deliveryGate(state(3, null), preview([check("block", "placeholder_residue")], [check("block", "placeholder_residue")]));
  assert.equal(gate.draftBlocks.length, 1);
  assert.equal(gate.canConfirm, false);
  assert.equal(gate.canDownloadFinal, false);
});

test("nothing is downloadable before the document loads", () => {
  const gate = deliveryGate(null, null);
  assert.equal(gate.canConfirm, false);
  assert.equal(gate.canDownloadFinal, false);
  assert.equal(gate.canDownloadDraft, false);
});
