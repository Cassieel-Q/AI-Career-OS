import test from "node:test";
import assert from "node:assert/strict";

import { ingestResumeLocally, readLocalProfiles } from "../app/local-profile.ts";

type Call = { url: string; init?: RequestInit };

function fakeFetch(body: unknown, status = 200) {
  const calls: Call[] = [];
  const send = (async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return { ok: status < 400, status, json: async () => body } as Response;
  }) as unknown as typeof fetch;
  return { calls, send };
}

test("local profile list goes through the guarded endpoint with the client header", async () => {
  const payload = {
    profiles: [
      {
        profile_id: "p1",
        label: "张三",
        status: "DRAFT",
        experience_count: 2,
        created_at: "2026-10-18T00:00:00Z",
        updated_at: "2026-10-18T00:00:00Z",
      },
    ],
    total: 1,
    truncated: false,
  };
  const { calls, send } = fakeFetch(payload);
  const result = await readLocalProfiles(send);
  assert.equal(result.profiles[0].profile_id, "p1");
  assert.match(calls[0].url, /\/api\/v1\/local\/profiles$/);
  const headers = calls[0].init?.headers as Record<string, string>;
  assert.equal(headers["X-AI-Career-Client"], "ai-career-web");
});

test("local ingest posts raw text and reports parsed counts", async () => {
  const payload = {
    profile_id: "p1",
    parse_source: "LOCAL_RULE",
    parsed_counts: { education: 1, skills: 4, experiences: 2, certifications: 1 },
  };
  const { calls, send } = fakeFetch(payload);
  const result = await ingestResumeLocally("p1", "张三\n教育经历\n复旦大学", send);
  assert.equal(result.parse_source, "LOCAL_RULE");
  assert.equal(result.parsed_counts.experiences, 2);
  assert.match(String(calls[0].url), /\/profiles\/p1\/resumes\/local$/);
  assert.equal(calls[0].init?.method, "POST");
  assert.equal(JSON.parse(String(calls[0].init?.body)).raw_text, "张三\n教育经历\n复旦大学");
});

test("server errors surface the detail message", async () => {
  const { send } = fakeFetch({ detail: "缺少本机客户端标识头，已拒绝该请求。" }, 403);
  await assert.rejects(() => readLocalProfiles(send), /缺少本机客户端标识头/);
});
