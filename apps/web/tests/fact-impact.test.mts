import assert from "node:assert/strict";
import { test } from "node:test";
import {
  IMPACT_LABEL,
  impactSummary,
  readFactImpact,
  readFactImpactByKey,
  syncFactToMission,
} from "../app/fact-impact.ts";

test("impact summary falls back to the same wording as the server", () => {
  assert.equal(
    impactSummary({
      source_kind: "experience",
      source_id: "e1",
      source_label: "经历：Product Intern",
      summary: "这项事实关联了 3 份岗位简历，其中 2 份可能需要更新。",
      total_missions: 3,
      needs_update_count: 2,
      missions: [],
      auto_update: false,
    }),
    "这项事实关联了 3 份岗位简历，其中 2 份可能需要更新。",
  );
  assert.equal(
    impactSummary({
      source_kind: "experience",
      source_id: "e1",
      source_label: "",
      summary: "",
      total_missions: 2,
      needs_update_count: 1,
      missions: [],
      auto_update: false,
    }),
    "这项事实关联了 2 份岗位简历，其中 1 份可能需要更新。",
  );
  assert.equal(impactSummary(null), "");
});

test("impact labels distinguish changed, review and untouched", () => {
  assert.equal(IMPACT_LABEL.CHANGED, "需要更新");
  assert.equal(IMPACT_LABEL.REVIEW, "建议复核");
  assert.equal(IMPACT_LABEL.NONE, "暂时无需改动");
});

test("impact reads are GET and sync is an explicit per-mission POST", async () => {
  const calls: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    calls.push({ url: String(url), init });
    return new Response(JSON.stringify({ total_missions: 0, needs_update_count: 0, missions: [], auto_update: false, summary: "" }), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    await readFactImpactByKey("p1", "experience:uuid-1:description:0");
    await readFactImpact("p1", "experience", "uuid-1");
    await syncFactToMission("p1", "experience", "uuid-1", "m9", 3);
    assert.match(calls[0].url, /facts\/impact\?fact_key=experience/);
    assert.match(calls[1].url, /facts\/experience\/uuid-1\/impact$/);
    assert.equal(calls[2].init?.method, "POST");
    assert.match(String(calls[2].url), /\/sync$/);
    assert.deepEqual(JSON.parse(String(calls[2].init?.body)), { mission_id: "m9", expected_revision: 3 });
  } finally { globalThis.fetch = original; }
});
