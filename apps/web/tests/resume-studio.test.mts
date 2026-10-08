import assert from "node:assert/strict";
import { test } from "node:test";
import { applyStudioOperation, downloadStudioPdf, readStudio, renderStudio, StudioApiError } from "../app/resume-studio/api.ts";
import { emptyHistory, findNode, inverseOperation, recordHistory, undoHistory, redoHistory, replayOperation } from "../app/resume-studio/history.ts";
import type { StudioState } from "../app/resume-studio/types.ts";

const node = (id: string, text: string) => ({ id, text, source_kind: "profile", source_id: null, evidence_refs: [], risk_level: "LOW" as const, claim_status: "CONFIRMED" as const });
const state: StudioState = {
  id: "s", mission_id: "m", revision: 4, confirmed_revision: null, language: "zh", template_id: "zh-classic",
  document: { schema_version: 1, basics: { name: node("n", "陈林") }, sections: [] },
};

test("studio client uses one mission document and If-Match revision", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify(state), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await readStudio("mission 1");
    await applyStudioOperation("mission 1", 4, { type: "set_text", node_id: "n", text: "Lin Chen" });
    await renderStudio("mission 1", 4);
    assert.match(requests[0].url, /mission%201\/resume-studio$/);
    assert.equal((requests[1].init?.headers as Record<string, string>)["If-Match"], "4");
    assert.deepEqual(JSON.parse(String(requests[1].init?.body)), { type: "set_text", node_id: "n", text: "Lin Chen" });
    assert.deepEqual(JSON.parse(String(requests[2].init?.body)), { revision: 4 });
  } finally { globalThis.fetch = original; }
});

test("409 error retains latest server state for conflict recovery", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(JSON.stringify({ detail: { message: "stale", latest: state } }), { status: 409 })) as typeof fetch;
  try {
    await assert.rejects(() => applyStudioOperation("m", 3, { type: "set_text", node_id: "n", text: "draft" }), error => {
      assert.ok(error instanceof StudioApiError);
      assert.equal(error.status, 409);
      assert.deepEqual((error.detail as { latest: StudioState }).latest, state);
      return true;
    });
  } finally { globalThis.fetch = original; }
});

test("PDF download keeps the server's safe filename", async () => {
  const original = globalThis.fetch;
  globalThis.fetch = (async () => new Response(new Blob(["%PDF-fake"]), { headers: { "Content-Disposition": "attachment; filename=resume.pdf; filename*=UTF-8''Ada%20Lin-Acme-PM-en.pdf" } })) as typeof fetch;
  try {
    const result = await downloadStudioPdf("m");
    assert.equal(result.filename, "Ada Lin-Acme-PM-en.pdf");
    assert.equal(await result.blob.text(), "%PDF-fake");
  } finally { globalThis.fetch = original; }
});

test("undo and redo create inverse operations against the next revision", () => {
  const forward = { type: "set_text" as const, node_id: "n", text: "Lin Chen" };
  const inverse = inverseOperation(state, forward);
  assert.deepEqual(inverse, { type: "set_text", node_id: "n", text: "陈林" });
  const history = recordHistory(emptyHistory(), { forward, inverse: inverse! });
  const [undo, afterUndo] = undoHistory(history);
  assert.deepEqual(undo, inverse);
  assert.equal(afterUndo.undo.length, 0);
  const [redo, afterRedo] = redoHistory(afterUndo);
  assert.deepEqual(redo, forward);
  assert.equal(afterRedo.redo.length, 0);
  assert.equal(findNode(state.document, "n")?.text, "陈林");
});

test("redo of a newly added item restores its stable id", () => {
  assert.deepEqual(
    replayOperation({ type: "add_bullet", entry_id: "entry", text: "New fact" }, { type: "omit", node_id: "new-id" }),
    { type: "restore", node_id: "new-id" },
  );
});
