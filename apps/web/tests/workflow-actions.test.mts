import assert from "node:assert/strict";
import test from "node:test";

import { runSingleFlight } from "../app/workflow-actions.ts";

test("concurrent workflow generation clicks share one request and allow a later retry", async () => {
  const state: { current: Promise<boolean> | null } = { current: null };
  let calls = 0;
  const operation = async () => {
    calls += 1;
    await new Promise((resolve) => setTimeout(resolve, 5));
    return true;
  };

  const first = runSingleFlight(state, operation);
  const second = runSingleFlight(state, operation);
  assert.equal(first, second);
  assert.equal(await first, true);
  assert.equal(calls, 1);
  assert.equal(await runSingleFlight(state, operation), true);
  assert.equal(calls, 2);
});

test("a generation transition performs one POST then refreshes before navigation", async () => {
  const state: { current: Promise<boolean> | null } = { current: null };
  const events: string[] = [];
  const action = () => runSingleFlight(state, async () => {
    events.push("POST");
    events.push("refresh");
    return true;
  });

  assert.equal(await Promise.all([action(), action()]).then((values) => values.every(Boolean)), true);
  assert.deepEqual(events, ["POST", "refresh"]);
});
