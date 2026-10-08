import test from "node:test";
import assert from "node:assert/strict";

import { TASK_STAGES, taskProgressRows, withTaskTimeout } from "../app/task-progress.ts";

test("task progress uses real operation boundaries and no invented percentage", () => {
  assert.deepEqual(TASK_STAGES.jd, ["提交岗位描述", "读取识别结果"]);
  assert.deepEqual(TASK_STAGES["resume-optimize"], ["整理经历", "生成岗位策略", "生成岗位定向版本"]);
  assert.deepEqual(taskProgressRows("resume-parse", 2).map((row) => row.status), ["done", "done", "active"]);
  assert.deepEqual(taskProgressRows("jd", 1), [
    { label: "提交岗位描述", status: "done" },
    { label: "读取识别结果", status: "active" },
  ]);
  assert.equal(JSON.stringify(TASK_STAGES).includes("%"), false);
});

test("timeout rejects a hung operation so UI can offer retry", async () => {
  await assert.rejects(
    withTaskTimeout(new Promise<never>(() => {}), 5, "岗位识别"),
    /岗位识别超时.*重试/,
  );
});
