import assert from "node:assert/strict";
import { test } from "node:test";
import {
  missionIdFromPath,
  publishAssistantContext,
  readAssistantContext,
} from "../app/assistant-context.ts";

function withWindow(search: string, pathname: string, seed: Record<string, string> = {}) {
  const store = new Map<string, string>(Object.entries(seed));
  const fakeWindow = {
    location: { search, pathname },
    sessionStorage: {
      getItem: (key: string) => store.get(key) ?? null,
      setItem: (key: string, value: string) => void store.set(key, value),
    },
  };
  (globalThis as { window?: unknown }).window = fakeWindow;
  return store;
}

test("missionIdFromPath extracts the mission uuid", () => {
  assert.equal(
    missionIdFromPath("/missions/11111111-2222-3333-4444-555555555555/interview"),
    "11111111-2222-3333-4444-555555555555",
  );
  assert.equal(missionIdFromPath("/assistant"), null);
});

test("URL params take priority over session storage", () => {
  withWindow(
    "?mission_id=m-url&target_resume_id=r-url",
    "/assistant",
    { "ai-career.activeMissionId": "m-store", "ai-career.activeTargetResumeId": "r-store" },
  );
  const context = readAssistantContext();
  assert.equal(context.missionId, "m-url");
  assert.equal(context.targetResumeId, "r-url");
});

test("falls back to session storage published by the resume studio", () => {
  withWindow("", "/assistant");
  publishAssistantContext("m-1", "r-1");
  const context = readAssistantContext();
  assert.equal(context.missionId, "m-1");
  assert.equal(context.targetResumeId, "r-1");
});

test("page context passes mission and target resume together", () => {
  const store = withWindow("?mission_id=m-only", "/assistant", { "ai-career.activeTargetResumeId": "r-only" });
  const context = readAssistantContext();
  assert.equal(context.missionId, "m-only");
  assert.equal(context.targetResumeId, "r-only");
  assert.equal(store.get("ai-career.activeTargetResumeId"), "r-only");
});
