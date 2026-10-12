import assert from "node:assert/strict";
import { test } from "node:test";
import {
  generateReferenceAnswer,
  isUngroundedAnswer,
  listQuestionBanks,
  createRealQuestion,
  addQuestionItem,
} from "../app/question-bank.ts";

const item = {
  id: "q1", bank_id: "b1", category: "BASIC", difficulty: "MEDIUM", interviewer_style: null,
  question_text: "自我介绍", source: "MODEL", evidence_refs: [], sort_order: 0, reference_answer: null,
};

test("question bank list uses the profile-scoped endpoint", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify([]), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await listQuestionBanks("profile 1");
    assert.match(requests[0].url, /profiles\/profile%201\/question-banks$/);
  } finally {
    globalThis.fetch = original;
  }
});

test("reference answer generation posts to the item endpoint", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ id: "a1", answer_text: "x", grounding: "CONFIRMED", evidence_refs: [] }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await generateReferenceAnswer("q1", true);
    assert.match(requests[0].url, /question-items\/q1\/reference-answer\?force=true$/);
    assert.equal(requests[0].init?.method, "POST");
  } finally {
    globalThis.fetch = original;
  }
});

test("real question intake goes through the profiles endpoint with source flags", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify(item), { status: 201, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await createRealQuestion("p1", { question_text: "讲一个失败项目", category: "PROJECT_DEEP_DIVE", difficulty: "HARD" });
    assert.match(requests[0].url, /profiles\/p1\/question-items\/real$/);
    assert.deepEqual(JSON.parse(String(requests[0].init?.body)), {
      question_text: "讲一个失败项目", category: "PROJECT_DEEP_DIVE", difficulty: "HARD",
    });
  } finally {
    globalThis.fetch = original;
  }
});

test("adding an item posts model source to the bank", async () => {
  const original = globalThis.fetch;
  let body: Record<string, unknown> = {};
  globalThis.fetch = (async (_url, init) => {
    body = JSON.parse(String(init?.body));
    return new Response(JSON.stringify(item), { status: 201, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await addQuestionItem("b1", { question_text: "为什么我们公司", category: "HR_QUESTIONS", source: "MODEL" });
    assert.equal(body.source, "MODEL");
    assert.equal(body.category, "HR_QUESTIONS");
  } finally {
    globalThis.fetch = original;
  }
});

test("ungrounded answers are flagged rather than treated as verified", () => {
  assert.equal(isUngroundedAnswer(null), true);
  assert.equal(isUngroundedAnswer({ id: "a", answer_text: "无法接地", grounding: "UNKNOWN", evidence_refs: [] }), true);
  assert.equal(isUngroundedAnswer({ id: "a", answer_text: "x", grounding: "NEEDS_CONFIRMATION", evidence_refs: [] }), true);
  assert.equal(isUngroundedAnswer({ id: "a", answer_text: "x", grounding: "BULLETS", evidence_refs: ["c1"] }), false);
});
