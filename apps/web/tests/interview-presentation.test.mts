import test from "node:test";
import assert from "node:assert/strict";

import { interviewPresentation } from "../app/interview-presentation.ts";

const session = {
  status: "ACTIVE",
  next_question: "第二题：如何验证方案？",
  turns: [
    { round_number: 1, question: "第一题：介绍项目。", answer: "我负责需求和验证。" },
    { round_number: 2, question: "第二题：如何验证方案？", answer: null },
  ],
};

test("scored answer remains visible until explicit next action", () => {
  const view = interviewPresentation(session, true);
  assert.equal(view.question, "第一题：介绍项目。");
  assert.equal(view.answer, "我负责需求和验证。");
  assert.equal(view.footerLabel, "进入下一题");
  assert.equal(view.canAnswer, false);
});

test("explicit next action reveals pending server question", () => {
  const view = interviewPresentation(session, false);
  assert.equal(view.question, "第二题：如何验证方案？");
  assert.equal(view.footerLabel, "提交回答");
  assert.equal(view.canAnswer, true);
});

test("five answered turns end at review", () => {
  const complete = { status: "COMPLETED", next_question: null, turns: Array.from({ length: 5 }, (_, index) => ({ round_number: index + 1, question: `题 ${index + 1}`, answer: `答 ${index + 1}` })) };
  const view = interviewPresentation(complete, false);
  assert.equal(view.footerLabel, "查看面试复盘");
  assert.equal(view.canAnswer, false);
  assert.equal(view.answeredCount, 5);
});
