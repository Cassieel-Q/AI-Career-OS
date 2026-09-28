import test from "node:test";
import assert from "node:assert/strict";
import { buildExportFileName, resolveExportProfileId } from "../app/export-resume-checks.ts";

import { CORE_MISSION_TABS, MISSION_TABS, missionTabLabel } from "../app/missions.ts";
import { CORE_RESUME_SUGGESTION_LIMIT, coreResumeNextStep, coreInterviewCopy } from "../app/mission-state.ts";
import { buildTargetResumeExportHtml } from "../app/export-target-resume.ts";

test("core flow exposes only ordinary user stages", () => {
  assert.deepEqual(CORE_MISSION_TABS, ["role", "resume", "interview", "outcome"]);
  assert.deepEqual(MISSION_TABS, CORE_MISSION_TABS);
  assert.equal(missionTabLabel("role"), "目标岗位");
  assert.equal(missionTabLabel("resume"), "简历优化");
  assert.equal(missionTabLabel("interview"), "模拟面试");
  assert.equal(missionTabLabel("outcome"), "面试记录");
  assert.equal(CORE_RESUME_SUGGESTION_LIMIT, 4);
});

test("confirmed resume goes directly to mock interview", () => {
  assert.deepEqual(coreResumeNextStep({ targetConfirmed: true }), { kind: "interview", label: "下一步：进入模拟面试" });
  assert.deepEqual(coreResumeNextStep({ targetConfirmed: false }), { kind: "resume", label: "确认优化建议" });
});

test("core interview copy has no technical workflow terms", () => {
  const copy = coreInterviewCopy({ hasFinalResume: true, hasQuestions: true });
  assert.match(copy.title, /模拟面试/);
  assert.doesNotMatch(`${copy.title} ${copy.description} ${copy.primaryLabel}`, /压力测试|补强|Evidence|Claim|Gap|Provider|CURATED|RAG/i);
});

test("export preserves the requested education-first section order", () => {
  const html = buildTargetResumeExportHtml({
    company: "百度",
    role: "AI 产品经理",
    seniority: "校招",
    targetResume: {
      section_order: ["education", "experience", "project", "skills"],
      recommended_experience_order: ["e1", "p1"],
      bullets: [
        { id: "b1", source_experience_id: "e1", suggested_text: "实习成果", status: "ACCEPTED", sort_order: 0 },
        { id: "b2", source_experience_id: "p1", suggested_text: "项目成果", status: "ACCEPTED", sort_order: 1 },
      ],
    },
    profile: {
      full_name: "候选人",
      education: [{ institution: "某大学", degree: "硕士", field_of_study: "信息管理", dates: "2023-2026" }],
      experiences: [
        { id: "e1", title: "产品实习", organization: "公司", dates: "2025", experience_type: "INTERNSHIP" },
        { id: "p1", title: "AI 项目", organization: "个人", dates: "2024", experience_type: "PROJECT" },
      ],
      skills: [{ name: "Python" }],
    },
  });
  assert.ok(html.indexOf("某大学") < html.indexOf("产品实习"));
  assert.ok(html.indexOf("产品实习") < html.indexOf("AI 项目"));
  assert.ok(html.indexOf("AI 项目") < html.indexOf("Python"));
});

test("export resolves bound profile and keeps campus work separate from projects", () => {
  const mission = { profile_id: "master", resume_source: { bound_profile_id: "bound" } };
  assert.equal(resolveExportProfileId(mission).profileId, "bound");
  const html = buildTargetResumeExportHtml({
    company: "百度",
    role: "产品经理",
    targetResume: { bullets: [
      { source_experience_id: "campus", status: "ACCEPTED", suggested_text: "组织学生会活动" },
      { source_experience_id: "project", status: "ACCEPTED", suggested_text: "完成评测项目" },
    ] },
    profile: { full_name: "潘佳琪", phone: "138", email: "p@example.com", experiences: [
      { id: "campus", title: "学生会副部长", experience_type: "CAMPUS" },
      { id: "project", title: "评测项目", experience_type: "PROJECT" },
    ], skills: ["MS Excel", "Excel", "python"] },
  });
  assert.match(html, /校园经历/);
  assert.match(html, /项目/);
  assert.doesNotMatch(html, /ENTRY_LEVEL/);
  assert.equal(buildExportFileName({ name: "潘佳琪", company: "百度", role: "产品经理", extension: "pdf" }), "潘佳琪-百度-产品经理.pdf");
});

test("export keeps synthetic project drafts out until facts are confirmed", () => {
  const html = buildTargetResumeExportHtml({
    company: "百度",
    role: "物理 AI 产品经理",
    targetResume: {
      bullets: [{
        source_experience_id: null,
        suggested_text: "设计智能硬件评测闭环并整理验证方案",
        status: "ACCEPTED",
        risk_flags: ["SYNTHETIC_PROJECT"],
      }],
    },
    profile: { full_name: "候选人", experiences: [] },
  });
  assert.doesNotMatch(html, /项目草案/);
  assert.doesNotMatch(html, /设计智能硬件评测闭环/);
});
