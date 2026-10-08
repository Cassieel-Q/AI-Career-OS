import test from "node:test";
import assert from "node:assert/strict";

import { factConfirmationPatch, resumeDecisionProgress, isChosenRewrite } from "../app/resume-decision.ts";

test("confirming a fact does not silently accept its rewrite", () => {
  assert.deepEqual(factConfirmationPatch(), { fact_confirmed: true, status: "SUGGESTED" });
});

test("real decision progress counts accepted, edited and unadopted items", () => {
  assert.deepEqual(resumeDecisionProgress([
    { status: "ACCEPTED" }, { status: "EDITED" }, { status: "REJECTED" }, { status: "SUGGESTED" },
  ]), { decided: 3, total: 4 });
});

test("an edited alternative is a chosen rewrite", () => {
  assert.equal(isChosenRewrite("EDITED"), true);
  assert.equal(isChosenRewrite("REJECTED"), false);
});
