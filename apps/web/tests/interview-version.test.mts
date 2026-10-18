import assert from "node:assert/strict";
import { test } from "node:test";
import {
  interviewVersionBanner,
  isDelivered,
  NO_DELIVERY_LABEL,
  readDeliveryVersions,
  readInterviewResume,
  type InterviewResume,
} from "../app/interview-version.ts";

const resume = (overrides: Partial<InterviewResume>): InterviewResume => ({
  source: "resume_studio",
  label: NO_DELIVERY_LABEL,
  warning: NO_DELIVERY_LABEL,
  delivered: false,
  application_id: null,
  snapshot_id: null,
  studio_revision: 3,
  delivered_at: null,
  content_hash: "abc",
  has_pdf: false,
  bullets: [{ text: "Built product evaluation dashboards" }],
  versions: [],
  ...overrides,
});

test("delivered snapshot drives the banner and excludes later edits", () => {
  const delivered = resume({
    source: "delivered_snapshot",
    delivered: true,
    label: "使用 2026-10-18 实际投递的版本（Studio 修订 v2）",
    studio_revision: 2,
    has_pdf: true,
    delivered_at: "2026-10-18",
  });
  assert.equal(isDelivered(delivered), true);
  const banner = interviewVersionBanner(delivered);
  assert.equal(banner.tone, "delivered");
  assert.match(banner.title, /实际投递的版本/);
  assert.match(banner.detail, /投递之后新增的内容不会混入/);
});

test("not-yet-delivered states the version is still being prepared", () => {
  const preparing = resume({});
  assert.equal(isDelivered(preparing), false);
  const banner = interviewVersionBanner(preparing);
  assert.equal(banner.tone, "preparing");
  assert.equal(banner.title, NO_DELIVERY_LABEL);
});

test("missing resume is reported instead of silently using latest studio", () => {
  const banner = interviewVersionBanner(null);
  assert.equal(banner.tone, "fallback");
  const empty = interviewVersionBanner(resume({ source: "none", bullets: [] }));
  assert.equal(empty.tone, "fallback");
});

test("delivered application without snapshot warns about the gap", () => {
  const banner = interviewVersionBanner(resume({
    source: "delivered_application",
    delivered: true,
    warning: "这份投递没有保存正文快照，当前展示的是工作台最新版本，可能与投递时略有差异。",
  }));
  assert.equal(banner.tone, "delivered");
  assert.match(banner.detail, /快照/);
});

test("interview resume request can pin one delivery version", async () => {
  const urls: string[] = [];
  const original = globalThis.fetch;
  globalThis.fetch = (async (url) => {
    urls.push(String(url));
    return new Response(JSON.stringify(resume({ delivered: true, source: "delivered_snapshot" })), {
      status: 200,
      headers: { "Content-Type": "application/json" },
    });
  }) as typeof fetch;
  try {
    await readInterviewResume("m");
    await readInterviewResume("m", "app-1");
    await readDeliveryVersions("m");
    assert.match(urls[0], /interview-resume$/);
    assert.match(urls[1], /application_id=app-1$/);
    assert.match(urls[2], /delivery-versions$/);
  } finally { globalThis.fetch = original; }
});
