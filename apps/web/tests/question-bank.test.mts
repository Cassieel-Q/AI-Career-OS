import assert from "node:assert/strict";
import { test } from "node:test";
import {
  explainQuestion,
  generateQuestionBank,
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

// ---------------------------------------------------------------------------
// 第六阶段：每道题都必须能回答六个必答问题
// ---------------------------------------------------------------------------

const fullItem = {
  id: "q2",
  bank_id: "b1",
  category: "PROJECT_DEEP_DIVE",
  difficulty: "HARD",
  interviewer_style: null,
  question_text: "请结合经历说明你如何满足「3 年以上 B 端产品经验」？",
  source: "MODEL",
  evidence_refs: [],
  jd_requirement_refs: ["3 年以上 B 端产品经验"],
  experience_refs: ["bullet-1"],
  why_asked: "对应 JD 要求，判断能否落地。",
  expected_evidence: ["在 Acme 实习期间搭建了产品评估看板"],
  followup_paths: ["能举一个具体例子吗？"],
  sample_answer: null,
  risk_flags: [],
  sort_order: 0,
  reference_answer: null,
};

test("explainQuestion answers why/jd/experience/facts/followups", () => {
  const view = explainQuestion(fullItem);
  assert.equal(view.why, "对应 JD 要求，判断能否落地。");
  assert.deepEqual(view.jdRefs, ["3 年以上 B 端产品经验"]);
  assert.deepEqual(view.experienceRefs, ["bullet-1"]);
  assert.deepEqual(view.allowedFacts, ["在 Acme 实习期间搭建了产品评估看板"]);
  assert.match(view.notToInvent, /不要编造/);
  assert.deepEqual(view.followups, ["能举一个具体例子吗？"]);
});

test("explainQuestion flags when there is no verified experience", () => {
  const view = explainQuestion({ ...fullItem, experience_refs: [], expected_evidence: [] });
  assert.match(view.notToInvent, /没有带证据的已确认经历/);
});

test("generateQuestionBank posts to the generate endpoint", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ id: "b1", items: [] }), { status: 201, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await generateQuestionBank("p1", { mission_id: "m1", target_resume_id: "r1" });
    assert.match(requests[0].url, /profiles\/p1\/question-banks\/generate$/);
    const body = JSON.parse(String(requests[0].init?.body));
    assert.equal(body.mission_id, "m1");
    assert.equal(body.target_resume_id, "r1");
  } finally {
    globalThis.fetch = original;
  }
});
