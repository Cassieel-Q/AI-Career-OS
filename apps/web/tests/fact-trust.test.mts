import test from "node:test";
import assert from "node:assert/strict";

import {
  FACT_STATUS_LABEL,
  attestFact,
  isAttested,
  readAttestedFacts,
  readFacts,
  referenceAnswerSections,
  type FactItem,
} from "../app/fact-trust.ts";

const GROUNDED = {
  grounded: true,
  known_facts: [{ text: "访谈12名同学，完成PRD和Figma原型。", source_kind: "SOURCE_EXTRACTED", quote: "访谈12名同学" }],
  missing_facts: [{ aspect: "可核对结果", question: "最后的产出是什么？" }],
  answer_structure: ["背景", "动作", "结果"],
  sample_wording: "我访谈了12名同学，完成PRD和Figma原型。",
};

test("grounded reference answer exposes the sample wording", () => {
  const sections = referenceAnswerSections(GROUNDED);
  assert.equal(sections.blocked, false);
  assert.equal(sections.wording, "我访谈了12名同学，完成PRD和Figma原型。");
  assert.equal(sections.known.length, 1);
  assert.equal(sections.missing.length, 1);
  assert.equal(sections.structure.length, 3);
});

test("reference answer degrades when the model is not grounded", () => {
  const sections = referenceAnswerSections({ ...GROUNDED, grounded: false });
  assert.equal(sections.blocked, true);
  assert.equal(sections.wording, null);
  assert.equal(sections.known.length, 1, "降级时仍要展示已知事实");
});

test("reference answer degrades when sample wording is missing", () => {
  const sections = referenceAnswerSections({ ...GROUNDED, sample_wording: null });
  assert.equal(sections.blocked, true);
  assert.equal(sections.wording, null);
});

test("unknown reference answer shape degrades instead of rendering a story", () => {
  const sections = referenceAnswerSections(null);
  assert.equal(sections.blocked, true);
  assert.deepEqual(sections.known, []);
  assert.deepEqual(sections.structure, []);
});

test("empty rows are dropped from the structured sections", () => {
  const sections = referenceAnswerSections({
    grounded: false,
    known_facts: [{ text: "   " }, { text: "有内容" }],
    missing_facts: [{ aspect: "" }, { question: "缺什么？" }],
    answer_structure: ["", "背景"],
  });
  assert.equal(sections.known.length, 1);
  assert.equal(sections.missing.length, 1);
  assert.equal(sections.missing[0].aspect, "待补充");
  assert.deepEqual(sections.structure, ["背景"]);
});

test("only an explicit user attestation counts as verified", () => {
  const fact = (status: FactItem["verification_status"]): FactItem => ({
    fact_key: "experience:1",
    title: "校园二手平台",
    original_text: "访谈12名同学",
    suggested_text: null,
    source_kind: "SOURCE_EXTRACTED",
    source_id: "1",
    source_type: "PARSED",
    verification_status: status,
    verified_at: null,
    present_aspects: [],
    missing_aspects: [],
    risk: "MEDIUM",
    note: null,
  });
  assert.equal(isAttested(fact("USER_ATTESTED")), true);
  assert.equal(isAttested(fact("UNREVIEWED")), false);
  assert.equal(isAttested(fact("REJECTED")), false);
  assert.equal(FACT_STATUS_LABEL.USER_ATTESTED, "你已确认属实");
});

function fakeFetch(body: unknown, status = 200) {
  const calls: Array<{ url: string; init?: RequestInit }> = [];
  const send = (async (url: string, init?: RequestInit) => {
    calls.push({ url: String(url), init });
    return {
      ok: status < 400,
      status,
      json: async () => body,
    } as Response;
  }) as unknown as typeof fetch;
  return { calls, send };
}

test("readFacts targets the profile facts endpoint", async () => {
  const payload = { profile_id: "p1", facts: [], attested_count: 0, rejected_count: 0, pending_count: 0 };
  const { calls, send } = fakeFetch(payload);
  const result = await readFacts("p1", send);
  assert.equal(result.profile_id, "p1");
  assert.match(calls[0].url, /\/api\/v1\/profiles\/p1\/facts$/);
});

test("attestFact posts the review decision", async () => {
  const payload = {
    fact_key: "experience:1",
    status: "USER_ATTESTED",
    verification_status: "USER_ATTESTED",
    fact_text: "访谈12名同学",
    source_kind: "SOURCE_EXTRACTED",
    verified_at: "2026-10-18T00:00:00Z",
    applied_to_source: false,
    note: null,
  };
  const { calls, send } = fakeFetch(payload);
  const result = await attestFact("p1", { fact_key: "experience:1", status: "USER_ATTESTED" }, send);
  assert.equal(result.status, "USER_ATTESTED");
  assert.equal(calls[0].init?.method, "POST");
  assert.match(String(calls[0].url), /\/facts\/attest$/);
  assert.equal(JSON.parse(String(calls[0].init?.body)).fact_key, "experience:1");
});

test("attested facts endpoint returns only user-confirmed text", async () => {
  const { calls, send } = fakeFetch({ profile_id: "p1", facts: ["访谈12名同学"] });
  const result = await readAttestedFacts("p1", send);
  assert.deepEqual(result.facts, ["访谈12名同学"]);
  assert.match(calls[0].url, /\/facts\/attested$/);
});

test("fact endpoint failures surface the server detail", async () => {
  const { send } = fakeFetch({ detail: "档案不存在" }, 404);
  await assert.rejects(() => readFacts("missing", send), /档案不存在/);
});
