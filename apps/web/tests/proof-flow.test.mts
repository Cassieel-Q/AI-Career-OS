import assert from "node:assert/strict";
import test from "node:test";

import { createTargetJob, generateProofGuidance, submitProofArtifact } from "../app/proof-flow.ts";

function response(payload: unknown, status = 200): Response {
  return new Response(JSON.stringify(payload), { status, headers: { "Content-Type": "application/json" } });
}

test("target job request preserves one-JD flow and source URL", async () => {
  let request: RequestInfo | URL | undefined;
  const result = await createTargetJob("profile-1", "  Build an AI product  ", "https://example.com/job", "http://api", async (input, init) => {
    request = input;
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), { raw_text: "  Build an AI product  ", source_url: "https://example.com/job" });
    return response({ id: "job-1", profile_id: "profile-1", raw_text: "  Build an AI product  ", source_url: "https://example.com/job", content_hash: "hash", status: "READY", created_at: "now", updated_at: "now" });
  });
  assert.equal(String(request), "http://api/api/v1/profiles/profile-1/target-jobs");
  assert.equal(result.id, "job-1");
});

test("provider/API errors remain visible to the flow", async () => {
  await assert.rejects(
    () => submitProofArtifact("action-1", { action_id: "action-1", artifact_type: "REPORT", artifact_text: "proof" }, "http://api", async () => response({ detail: "artifact conflict" }, 409)),
    /artifact conflict/,
  );
});

test("proof guidance requests direct AI coaching without an artifact payload", async () => {
  let request: RequestInfo | URL | undefined;
  const result = await generateProofGuidance("claim-1", "PROJECT_WRITEUP", "http://api", async (input, init) => {
    request = input;
    assert.equal(init?.method, "POST");
    assert.equal(init?.body, undefined);
    return response({
      claim_id: "claim-1",
      action_type: "PROJECT_WRITEUP",
      title: "项目补齐指南",
      summary: "补齐背景、动作和结果。",
      questions: [],
      steps: ["补写项目背景"],
      learning: ["实验设计"],
      expected_outputs: ["项目说明"],
      generated_by: "llm",
    });
  });
  assert.equal(String(request), "http://api/api/v1/resume-claims/claim-1/proof-guidance?action_type=PROJECT_WRITEUP");
  assert.equal(result.generated_by, "llm");
  assert.deepEqual(result.steps, ["补写项目背景"]);
});
