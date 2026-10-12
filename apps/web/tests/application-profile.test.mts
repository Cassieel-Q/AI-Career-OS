import assert from "node:assert/strict";
import { test } from "node:test";
import {
  APPLICATION_PROFILE_FIELDS,
  compactApplicationProfile,
  readApplicationFillFacts,
  readResumeFacts,
  saveApplicationProfile,
} from "../app/application-profile.ts";

test("all declared fields have an explicit sensitivity decision", () => {
  const sensitive = APPLICATION_PROFILE_FIELDS.filter((f) => f.sensitive).map((f) => f.key);
  const plain = APPLICATION_PROFILE_FIELDS.filter((f) => !f.sensitive).map((f) => f.key);
  assert.deepEqual(sensitive.sort(), ["archive_location", "emergency_contact", "emergency_phone", "family_info", "health_status", "id_number"].sort());
  assert.deepEqual(plain, ["availability"]);
});

test("compactApplicationProfile drops blanks so saving never wipes existing values", () => {
  const result = compactApplicationProfile({ id_number: "  ", health_status: "良好", availability: "", emergency_contact: null });
  assert.deepEqual(result, { health_status: "良好" });
});

test("saving uses PUT on the profile-scoped application-profile endpoint", async () => {
  const requests: { url: string; init?: RequestInit }[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url, init) => {
    requests.push({ url: String(url), init });
    return new Response(JSON.stringify({ health_status: "良好" }), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await saveApplicationProfile("p1", { health_status: "良好" });
    assert.equal(requests[0].init?.method, "PUT");
    assert.match(requests[0].url, /profiles\/p1\/application-profile$/);
    assert.deepEqual(JSON.parse(String(requests[0].init?.body)), { health_status: "良好" });
  } finally {
    globalThis.fetch = original;
  }
});

test("resume facts and application fill facts use distinct endpoints", async () => {
  const urls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url) => {
    urls.push(String(url));
    return new Response(JSON.stringify({}), { status: 200, headers: { "Content-Type": "application/json" } });
  }) as typeof fetch;
  try {
    await readResumeFacts("p1");
    await readApplicationFillFacts("p1");
    assert.match(urls[0], /profiles\/p1\/resume-facts$/);
    assert.match(urls[1], /profiles\/p1\/application-fill-facts$/);
  } finally {
    globalThis.fetch = original;
  }
});
