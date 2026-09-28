import assert from "node:assert/strict";
import test from "node:test";

import {
  createMarketProfileRequest,
  getMarketProfileRequest,
  getRequirementEvidenceRequest,
  marketRequirementFrequency,
} from "../app/market-profile.ts";

const profile = {
  id: "market-1",
  target_role_id: "target-1",
  sample_count: 5,
  sample_fingerprint: "fingerprint",
  status: "VALID" as const,
  generated_at: "2026-09-19T00:00:00Z",
  updated_at: "2026-09-19T00:00:00Z",
  requirements: [{
    id: "req-1",
    name: "Python",
    category: "SKILL" as const,
    occurrence_count: 4,
    frequency_ratio: 0.8,
    source_jd_ids: ["jd-1", "jd-2", "jd-3", "jd-4"],
    evidence: [{ id: "ev-1", job_description_id: "jd-1", source_url: null, evidence_text: "Python" }],
  }],
  capabilities: [{
    id: "req-1",
    name: "Technical capability",
    summary: "由 Python 综合，覆盖 4 / 5 条 JD。",
    occurrence_count: 4,
    frequency_ratio: 0.8,
    source_jd_ids: ["jd-1", "jd-2", "jd-3", "jd-4"],
    atomic_requirement_ids: ["req-1"],
    atomic_requirements: [],
    evidence: [{ id: "ev-1", job_description_id: "jd-1", source_url: null, evidence_text: "Python" }],
  }],
};

function response(body: unknown, status = 200) {
  return new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
}

test("market profile requests use the target-role contract and preserve readiness errors", async () => {
  const calls: Array<{ url: string; method: string }> = [];
  const request = async (input: RequestInfo | URL, init?: RequestInit) => {
    calls.push({ url: String(input), method: String(init?.method) });
    return response(profile);
  };
  assert.deepEqual(await getMarketProfileRequest("target-1", "http://api.test", request), profile);
  assert.deepEqual(await createMarketProfileRequest("target-1", "http://api.test", request), profile);
  assert.deepEqual(calls, [
    { url: "http://api.test/api/v1/target-roles/target-1/market-profile", method: "GET" },
    { url: "http://api.test/api/v1/target-roles/target-1/market-profile", method: "POST" },
  ]);
  assert.equal(marketRequirementFrequency(profile.requirements[0]), "4 / 4 JDs (80%)");
});

test("missing market profile is an empty state while other errors remain visible", async () => {
  const missing = await getMarketProfileRequest("target-1", "http://api.test", async () => response({ detail: "市场画像尚未生成" }, 404));
  assert.equal(missing, null);
  await assert.rejects(
    getMarketProfileRequest("target-1", "http://api.test", async () => response({ detail: "provider failed" }, 502)),
    /provider failed/,
  );
});

test("focused evidence endpoint does not request raw JD collections", async () => {
  let called = "";
  const evidence = await getRequirementEvidenceRequest("req-1", "http://api.test", async (input) => {
    called = String(input);
    return response(profile.requirements[0].evidence);
  });
  assert.deepEqual(evidence, profile.requirements[0].evidence);
  assert.equal(called, "http://api.test/api/v1/market-requirements/req-1/evidence");
});
