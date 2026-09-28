import assert from "node:assert/strict";
import test from "node:test";

import { getDashboardRequest } from "../app/dashboard.ts";

test("dashboard helper reads the aggregate endpoint", async () => {
  let called = "";
  const result = await getDashboardRequest("profile-1", "http://api.test", async (input) => {
    called = String(input);
    return new Response(JSON.stringify({ target_role: null, jd_sample_count: 0, market_ready: false, top_requirements: [], top_gaps: [], confirmed_priorities: [], current_week: null, upcoming_tasks: [], progress_ratio: 0, roadmap_id: null, replan_available: false }), { status: 200 });
  });
  assert.equal(called, "http://api.test/api/v1/profiles/profile-1/dashboard");
  assert.equal(result.market_ready, false);
});
