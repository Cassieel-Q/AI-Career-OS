import assert from "node:assert/strict";
import { buildTargetResumeExportHtml, countExportableBullets, exportEmptyContentFeedback, exportEntryHint, exportPrintWindowFeedback } from "../app/export-target-resume.ts";

const html = buildTargetResumeExportHtml({
  company: "Baidu",
  role: "AI Product Manager Intern",
  seniority: "Intern",
  targetResume: {
    version: 1,
    positioning_statement: "面向百度 AI PM 实习，突出 Agent 产品与证据闭环。",
    recommended_experience_order: ["exp-work", "exp-project"],
    bullets: [
      {
        id: "b1",
        source_experience_id: "exp-work",
        suggested_text: "主导 CareerOS 投递版导出，补齐教育/项目结构。",
        status: "ACCEPTED",
        sort_order: 0,
      },
      {
        id: "b2",
        source_experience_id: "exp-project",
        final_text: "搭建证据门禁，避免简历虚构指标。",
        status: "EDITED",
        sort_order: 1,
      },
      {
        id: "b3",
        source_experience_id: "exp-omit",
        suggested_text: "这条应被 OMIT 掉",
        status: "ACCEPTED",
        sort_order: 2,
      },
      {
        id: "b4",
        source_experience_id: "exp-work",
        suggested_text: "被拒绝的要点",
        status: "REJECTED",
        sort_order: 3,
      },
      {
        id: "b5",
        source_experience_id: "exp-work",
        suggested_text: "未确认的建议要点",
        status: "SUGGESTED",
        sort_order: 4,
      },
    ],
  },
  profile: {
    full_name: "张三",
    email: "zhangsan@example.com",
    phone: "13800000000",
    location: "北京",
    education: [
      {
        institution: "某某大学",
        degree: "本科",
        field_of_study: "计算机",
        dates: "2021-2025",
      },
    ],
    skills: ["Python", { name: "产品设计" }, "SQL"],
    certifications: [{ name: "PMP", issuer: "PMI", date: "2024" }],
  },
  experiences: [
    {
      id: "exp-work",
      title: "产品实习生",
      organization: "Example Tech",
      dates: "2024.06-2024.09",
      experience_type: "INTERNSHIP",
    },
    {
      id: "exp-project",
      title: "Evidence OS",
      organization: "Personal",
      dates: "2025",
      experience_type: "PROJECT",
      description: "fallback desc",
    },
    {
      id: "exp-omit",
      title: "无关经历",
      organization: "Old Co",
      experience_type: "WORK",
    },
  ],
  selections: [
    { experience_id: "exp-work", decision: "KEEP_AND_HIGHLIGHT" },
    { experience_id: "exp-project", decision: "KEEP" },
    { experience_id: "exp-omit", decision: "OMIT" },
  ],
});

assert.match(html, /张三/);
assert.match(html, /zhangsan@example\.com/);
assert.match(html, /<h2>经历<\/h2>/);
assert.match(html, /产品实习生/);
assert.match(html, /主导 CareerOS 投递版导出/);
assert.match(html, /<h2>项目<\/h2>/);
assert.match(html, /Evidence OS/);
assert.match(html, /搭建证据门禁/);
assert.match(html, /<h2>教育<\/h2>/);
assert.match(html, /某某大学/);
assert.match(html, /<h2>技能<\/h2>/);
assert.match(html, /Python/);
assert.match(html, /<h2>证书<\/h2>/);
assert.match(html, /PMP/);
assert.match(html, /@media print/);
assert.doesNotMatch(html, /无关经历/);
assert.doesNotMatch(html, /被拒绝的要点/);
assert.doesNotMatch(html, /未确认的建议要点/);
assert.doesNotMatch(html, /这条应被 OMIT/);

// missing sections skipped
const sparse = buildTargetResumeExportHtml({
  targetResume: {
    id: "tr-sparse",
    positioning_statement: "只有摘要这一段，source 不要求",
    bullets: [],
  } as any,
  company: "UNKNOWN",
  role: "UNKNOWN",
  seniority: "UNKNOWN",
});
// 投递版不导出摘要；UNKNOWN 不渲染
assert.doesNotMatch(sparse, /只有摘要/);
assert.doesNotMatch(sparse, /摘要/);
assert.doesNotMatch(sparse, /UNKNOWN/);
assert.doesNotMatch(sparse, /投递目标/);
assert.doesNotMatch(sparse, /<h2>经历<\/h2>/);
assert.doesNotMatch(sparse, /<h2>教育<\/h2>/);
assert.doesNotMatch(sparse, /<h2>项目<\/h2>/);



const compound = buildTargetResumeExportHtml({
  targetResume: { id: "tr-c", positioning_statement: "", bullets: [] } as any,
  profile: { full_name: "UNKNOWN · UNKNOWN", summary: "x" } as any,
  company: "UNKNOWN",
  role: "UNKNOWN",
});
assert.doesNotMatch(compound, /UNKNOWN/i);
assert.doesNotMatch(compound, /待确认/);



const blocked = exportPrintWindowFeedback(false);
assert.equal(blocked.tone, "error");
assert.match(blocked.message, /弹窗/);

const opened = exportPrintWindowFeedback(true);
assert.equal(opened.tone, "ok");
assert.match(opened.message, /另存为 PDF/);
assert.match(opened.message, /尚未保存文件/);
assert.doesNotMatch(opened.message, /已生成/);


const emptyFeedback = exportEmptyContentFeedback();
assert.equal(emptyFeedback.tone, "error");
assert.match(emptyFeedback.message, /暂无已确认要点/);

const onlySuggested = {
  version: 1,
  bullets: [{
    id: "s1",
    source_experience_id: "exp-work",
    suggested_text: "未确认建议",
    status: "SUGGESTED",
    sort_order: 0,
  }],
} as any;
assert.equal(countExportableBullets(onlySuggested), 0);

const ghostHtml = buildTargetResumeExportHtml({
  company: "Baidu",
  role: "PM",
  targetResume: {
    version: 1,
    bullets: [{
      id: "g1",
      source_experience_id: "ghost-exp-id",
      suggested_text: "幽灵经历要点不应出现",
      status: "ACCEPTED",
      sort_order: 0,
    }],
  } as any,
  experiences: [{ id: "exp-work", title: "真实经历", organization: "Co", experience_type: "WORK" }],
  selections: [{ experience_id: "exp-work", decision: "KEEP" }],
});
assert.doesNotMatch(ghostHtml, /幽灵经历要点不应出现/);
assert.doesNotMatch(ghostHtml, /ghost-exp-id/);
assert.match(ghostHtml, /暂无可用的投递内容/);
assert.equal(countExportableBullets(
  { version: 1, bullets: [{ id: "g1", source_experience_id: "ghost-exp-id", suggested_text: "x", status: "ACCEPTED", sort_order: 0 }] } as any,
  ["exp-work"]
), 0);
assert.match(exportEntryHint(0), /还没有可导出/);
assert.match(exportEntryHint(2), /可导出 2 条/);
assert.match(exportEntryHint(2), /打印另存 PDF/);
assert.doesNotMatch(exportEntryHint(2), /自动下载完成/);

console.log("export-target-resume.test.mts OK");



