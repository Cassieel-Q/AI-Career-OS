import assert from "node:assert/strict";
import test from "node:test";

import {
  addJobDescriptionToCollection,
  canAddJobDescription,
  createJobDescriptionRequest,
  deleteJobDescriptionRequest,
  getJobDescriptionsRequest,
  jobDescriptionReadiness,
  jobDescriptionWorkflowState,
  normalizeJobDescriptionSourceUrl,
  removeJobDescriptionFromCollection,
  updateJobDescriptionInCollection,
  updateJobDescriptionRequest,
} from "../app/job-descriptions.ts";
import type { JobDescriptionRead } from "../app/job-descriptions.ts";
import type { TargetRoleRead } from "../app/target-role.ts";


const target: TargetRoleRead = {
  id: "target-1",
  profile_id: "profile-1",
  role_code: "AI_PRODUCT_MANAGER",
  role_name: "AI Product Manager",
  role_profile_version: "v1",
  role_exploration_id: "exploration-1",
  selected_at: "2026-09-18T00:00:00Z",
  updated_at: "2026-09-18T00:00:00Z",
};

function jd(id: string, rawText = `JD ${id}`): JobDescriptionRead {
  return {
    id,
    target_role_id: target.id,
    raw_text: rawText,
    source_url: null,
    created_at: "2026-09-18T00:00:00Z",
    updated_at: "2026-09-18T00:00:00Z",
  };
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(body === null ? null : JSON.stringify(body), {
    status,
    headers: body === null ? undefined : { "Content-Type": "application/json" },
  });
}

test("no current target role clears and disables the JD workflow", () => {
  assert.deepEqual(jobDescriptionWorkflowState(null, [jd("old")]), {
    available: false,
    targetRoleId: null,
    targetRoleName: null,
    records: [],
  });
  assert.equal(jobDescriptionWorkflowState(target, []).available, true);
});

test("readiness and maximum use saved record count", () => {
  assert.deepEqual(jobDescriptionReadiness(0), { ready: false, remaining: 3 });
  assert.deepEqual(jobDescriptionReadiness(2), { ready: false, remaining: 1 });
  assert.deepEqual(jobDescriptionReadiness(3), { ready: true, remaining: 0 });
  assert.equal(canAddJobDescription(9), true);
  assert.equal(canAddJobDescription(10), false);
});

test("blank source URLs normalize to null", () => {
  assert.equal(normalizeJobDescriptionSourceUrl(undefined), undefined);
  assert.equal(normalizeJobDescriptionSourceUrl(null), null);
  assert.equal(normalizeJobDescriptionSourceUrl(" \n"), null);
  assert.equal(normalizeJobDescriptionSourceUrl(" https://example.com/a "), "https://example.com/a");
});

test("GET and POST use the exact target collection contract", async () => {
  const calls: Array<{ input: string; init?: RequestInit }> = [];
  const request = async (input: string | URL | Request, init?: RequestInit) => {
    calls.push({ input: String(input), init });
    return jsonResponse(init?.method === "POST" ? jd("one", "Raw JD") : [] , init?.method === "POST" ? 201 : 200);
  };
  assert.deepEqual(await getJobDescriptionsRequest(target.id, "http://api.test", request), []);
  await createJobDescriptionRequest(target.id, { raw_text: "Raw JD", source_url: " " }, "http://api.test", request);
  assert.equal(calls[0].input, "http://api.test/api/v1/target-roles/target-1/job-descriptions");
  assert.equal(calls[0].init?.method, "GET");
  assert.equal(calls[1].init?.method, "POST");
  assert.equal(calls[1].init?.body, JSON.stringify({ raw_text: "Raw JD", source_url: null }));
});

test("PATCH preserves omission and sends explicit null for clearing", async () => {
  const bodies: string[] = [];
  const request = async (_input: string | URL | Request, init?: RequestInit) => {
    bodies.push(String(init?.body));
    return jsonResponse(jd("one", "Changed"));
  };
  await updateJobDescriptionRequest("one", { raw_text: "Changed" }, "http://api.test", request);
  await updateJobDescriptionRequest("one", { source_url: null }, "http://api.test", request);
  await updateJobDescriptionRequest("one", { source_url: "  " }, "http://api.test", request);
  assert.deepEqual(bodies, [
    JSON.stringify({ raw_text: "Changed" }),
    JSON.stringify({ source_url: null }),
    JSON.stringify({ source_url: null }),
  ]);
});

test("DELETE requires a 204 response and safe errors stay user-facing", async () => {
  const calls: string[] = [];
  await deleteJobDescriptionRequest("one", "http://api.test", async (input) => {
    calls.push(String(input));
    return jsonResponse(null, 204);
  });
  assert.deepEqual(calls, ["http://api.test/api/v1/job-descriptions/one"]);
  await assert.rejects(
    createJobDescriptionRequest(target.id, { raw_text: "Duplicate", source_url: null }, "http://api.test", async () =>
      jsonResponse({ detail: "This exact job description is already saved" }, 409),
    ),
    /already saved/,
  );
});

test("collection helpers add, edit and delete without mutating prior state", () => {
  const empty: JobDescriptionRead[] = [];
  const one = addJobDescriptionToCollection(empty, jd("one"));
  const edited = updateJobDescriptionInCollection(one, jd("one", "Edited"));
  const deleted = removeJobDescriptionFromCollection(edited, "one");
  assert.deepEqual(empty, []);
  assert.equal(one[0].raw_text, "JD one");
  assert.equal(edited[0].raw_text, "Edited");
  assert.deepEqual(deleted, []);
});
