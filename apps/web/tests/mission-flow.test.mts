import test from "node:test";
import assert from "node:assert/strict";

import { bindMissionResumeText, createDraftProfile, createMission, ingestResumeText, missionHref, updateMissionIdentity, updateResumeBullet } from "../app/missions.ts";
import { alignedExperienceWhy } from "../app/experience-utils.ts";
import { deriveResumeFlowStep, humanizeMissionError } from "../app/mission-state.ts";

function response(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { "content-type": "application/json" } });
}

test("mission creation sends only the raw JD and optional source URL", async () => {
  let captured: { url: string; init?: RequestInit } | null = null;
  const mission = await createMission("profile-1", "Baidu AI PM evaluation JD", "https://example.test/jd", "http://api", async (input, init) => {
    captured = { url: String(input), init };
    return response({ id: "mission-1" });
  });

  assert.equal(mission.id, "mission-1");
  assert.equal(captured?.url, "http://api/api/v1/profiles/profile-1/job-missions");
  assert.equal(captured?.init?.method, "POST");
  assert.deepEqual(JSON.parse(String(captured?.init?.body)), { raw_text: "Baidu AI PM evaluation JD", source_url: "https://example.test/jd" });
});

test("draft profile bootstrap hits the empty-profile endpoint", async () => {
  let capturedUrl = "";
  const profile = await createDraftProfile("http://api", async (input, init) => {
    capturedUrl = String(input);
    assert.equal(init?.method, "POST");
    return response({ profile_id: "profile-draft", experiences: [] });
  });
  assert.equal(capturedUrl, "http://api/api/v1/profiles/draft");
  assert.equal(profile.profile_id, "profile-draft");
});

test("paste resume path reuses profile ingest text API", async () => {
  let capturedUrl = "";
  const profile = await ingestResumeText("profile-1", "x".repeat(80), "http://api", async (input, init) => {
    capturedUrl = String(input);
    assert.equal(init?.method, "POST");
    assert.deepEqual(JSON.parse(String(init?.body)), { raw_text: "x".repeat(80) });
    return response({ profile_id: "profile-1", experiences: [{ id: "e1", title: "PM" }] });
  });
  assert.equal(capturedUrl, "http://api/api/v1/profiles/profile-1/resumes/text");
  assert.equal(profile.experiences.length, 1);
});

test("resume generation is gated until a resume is bound", () => {
  assert.equal(deriveResumeFlowStep({
    resumeBound: false,
    experienceCount: 3,
    selectionCount: 3,
    hasStrategy: true,
    hasTargetResume: false,
    targetConfirmed: false,
    hasRedTeam: false,
    highRiskCount: 0,
  }), "source");
});

test("company intel failure copy stays user-facing", () => {
  assert.doesNotMatch(
    humanizeMissionError("Mission intelligence returned an unusable response", "company_intel"),
    /Mission intelligence|provider|schema/i,
  );
});

test("mission links keep route identity and bullet edits use the mission-safe API boundary", async () => {
  assert.equal(missionHref("mission 1", "resume"), "/missions/mission%201/resume");
  let capturedUrl = "";
  await updateResumeBullet("bullet-1", { status: "ACCEPTED" }, "http://api", async (input, init) => {
    capturedUrl = String(input);
    assert.equal(init?.method, "PATCH");
    return response({ id: "bullet-1", status: "ACCEPTED" });
  });
  assert.equal(capturedUrl, "http://api/api/v1/target-resume-bullets/bullet-1");
});

test("mission identity confirmation uses a scoped PATCH", async () => {
  let capturedUrl = "";
  await updateMissionIdentity("mission-1", { company: "Baidu", role: "AI PM", role_family: "AI_PRODUCT", seniority: "INTERN", location: null }, "http://api", async (input, init) => {
    capturedUrl = String(input);
    assert.equal(init?.method, "PATCH");
    assert.deepEqual(JSON.parse(String(init?.body)), { company: "Baidu", role: "AI PM", role_family: "AI_PRODUCT", seniority: "INTERN", location: null });
    return response({ id: "mission-1" });
  });
  assert.equal(capturedUrl, "http://api/api/v1/job-missions/mission-1/identity");
});

test("mission paste bind uses mission-scoped resumes/text API (not profile ingest)", async () => {
  let capturedUrl = "";
  let capturedBody: unknown = null;
  await bindMissionResumeText("mission-1", "x".repeat(80), { updateMaster: false }, "http://api", async (input, init) => {
    capturedUrl = String(input);
    capturedBody = init?.body ? JSON.parse(String(init.body)) : null;
    return new Response(JSON.stringify({
      mission: { id: "mission-1", profile_id: "profile-1", resume_source: { mode: "paste", bound_at: "t", isolation: "mission_local", bound_profile_id: "local-1" } },
      profile_id: "profile-1",
      bound_profile_id: "local-1",
      isolation: "mission_local",
      updated_master: false,
      experiences: [{ id: "e1" }],
    }), { status: 200, headers: { "Content-Type": "application/json" } });
  });
  assert.equal(capturedUrl, "http://api/api/v1/job-missions/mission-1/resumes/text");
  assert.equal((capturedBody as { update_master?: boolean }).update_master, false);
  assert.ok(String((capturedBody as { raw_text?: string }).raw_text || "").length >= 40);
});

test("target_resume_inline_edit sends EDITED patch with final_text", async () => {
  let capturedUrl = "";
  let capturedBody = null;
  await updateResumeBullet(
    "bullet-edit-1",
    { final_text: "改写后的可验证要点", status: "EDITED" },
    "http://api",
    async (input, init) => {
      capturedUrl = String(input);
      assert.equal(init?.method, "PATCH");
      capturedBody = JSON.parse(String(init?.body));
      return response({
        id: "bullet-edit-1",
        status: "EDITED",
        final_text: "改写后的可验证要点",
        evidence_refs: ["exp-1"],
        jd_refs: ["jd-1"],
      });
    },
  );
  assert.equal(capturedUrl, "http://api/api/v1/target-resume-bullets/bullet-edit-1");
  assert.deepEqual(capturedBody, { final_text: "改写后的可验证要点", status: "EDITED" });
});

test("alignedExperienceWhy import from experience-utils resolves to a function", () => {
  assert.equal(typeof alignedExperienceWhy, "function");
  const omitWhy = alignedExperienceWhy("OMIT", "与百度·AI产品经理相关，建议保留并突出「班级学习委员」中可验证的成果与职责。", "班级学习委员");
  assert.match(omitWhy, /暂不放入/);
  assert.doesNotMatch(omitWhy, /建议保留/);
});

