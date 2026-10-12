import test from "node:test";
import assert from "node:assert/strict";

import { describeJdAnalysisDegradation } from "../app/mission-state.ts";

test("解析正常时不算降级", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: null,
    warnings: [],
    whatMatters: { core_capabilities: ["需求分析", "数据驱动"] },
  });
  assert.equal(result.degraded, false);
  assert.equal(result.message, "");
});

test("带 analysis_error 即视为降级", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: { type: "partial_jd_analysis", reason: "what_matters_or_intel_degraded" },
    warnings: [],
    whatMatters: { core_capabilities: ["需求分析"] },
  });
  assert.equal(result.degraded, true);
  assert.ok(result.message.length > 0);
});

test("warnings 含 jd_analysis_unavailable 时提示「没有跑完」", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: null,
    warnings: ["jd_analysis_unavailable", "company_intel_unavailable"],
    whatMatters: {},
  });
  assert.equal(result.degraded, true);
  assert.match(result.message, /没有跑完/);
});

test("身份未识别时优先提示手动补全公司岗位", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: null,
    warnings: ["jd_identity_unresolved", "jd_analysis_unavailable"],
    whatMatters: {},
  });
  assert.equal(result.degraded, true);
  assert.match(result.message, /公司和岗位/);
});

test("what_matters 没有 core_capabilities 也算降级", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: null,
    warnings: [],
    whatMatters: { core_capabilities: [] },
  });
  assert.equal(result.degraded, true);
});

test("what_matters 为 null 时按空处理，不抛异常", () => {
  const result = describeJdAnalysisDegradation({
    analysisError: null,
    warnings: null,
    whatMatters: null,
  });
  assert.equal(result.degraded, true);
});
