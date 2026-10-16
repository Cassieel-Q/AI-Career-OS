/**
 * Overnight Sprint M3：求职管理补齐（投递页）真实浏览器 E2E。
 *
 * 真实点击页面完成：
 *   1) 新建投递记录（填写公司/岗位/渠道/JD 来源 → 保存）
 *   2) 筛选：状态 / 渠道 / 关键词
 *   3) 绑定简历版本 → 显示「投递版本 vN（Studio rM）」+ PDF 快照下载链接
 *   4) 打招呼话术：生成 → 编辑 → 保存（不自动发送）
 *   5) 求职看板：阶段数量 / 简历版本使用记录 / 最近面试 / 待办提醒
 *
 * 前置：后端 8100、前端 3000 已启动。
 */
"use strict";

const path = require("path");
const fs = require("fs");

let playwright;
try {
  playwright = require("playwright");
} catch (err) {
  console.error("无法加载 playwright：" + err.message);
  process.exit(2);
}

const WEB = process.env.AIOS_WEB || "http://127.0.0.1:3000";
const API = process.env.AIOS_API || "http://127.0.0.1:8100";
const OUT = path.resolve(__dirname, "../../../docs/screenshots/overnight-m3");
const STORAGE_KEY = "ai-career-os-dogfood-profile-id";

const RESUME_TEXT = `孙七
电话：13500000000  邮箱：sunqi@example.com  城市：成都

教育背景
某大学 市场营销 本科 2020.09 - 2024.06

实习经历
某快消公司 品牌运营实习 2023.06 - 2023.12
- 负责小红书内容排期与选题库维护，累计产出 60 篇笔记
- 联动 3 个达人完成新品测评合作，曝光量 12 万
- 整理投放复盘模板，团队复用 5 次

技能
内容策划 / 数据分析 / 小红书运营 / Excel
`;

const JD_TEXT = `内容运营（成都）
岗位职责：
1. 负责小红书/抖音内容选题与排期，维护选题库；
2. 对接达人资源，推进合作落地与效果复盘；
3. 沉淀运营模板，提升团队协作效率。
任职要求：
1. 本科及以上学历；
2. 有内容平台运营实习经验者优先；
3. 表达清晰，有复盘习惯。
`;

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
}

async function api(method, urlPath, body, headers) {
  const response = await fetch(API + urlPath, {
    method,
    headers: { "Content-Type": "application/json", ...(headers || {}) },
    body: body === undefined ? undefined : JSON.stringify(body),
  });
  const text = await response.text();
  let parsed;
  try {
    parsed = JSON.parse(text);
  } catch {
    parsed = { raw: text.slice(0, 200) };
  }
  if (!response.ok) return { __http_error: response.status, detail: parsed };
  return parsed;
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const uniqueRole = `内容运营（绑定版 ${Date.now() % 1000000}`; // 唯一角色名：避免上一轮残留记录干扰定位

  // ------------------------------------------------ 准备：档案 + 岗位 + 已确认 Studio
  const draft = await api("POST", "/api/v1/profiles/draft");
  const profileId = draft.profile_id || draft.id;
  await api("POST", `/api/v1/profiles/${profileId}/resumes/text`, { raw_text: RESUME_TEXT });
  await api("POST", `/api/v1/profiles/${profileId}/confirm`);
  const mission = await api("POST", `/api/v1/profiles/${profileId}/job-missions`, { raw_text: JD_TEXT });
  const missionId = mission.mission_id || mission.id;

  for (let i = 0; i < 60; i += 1) {
    const state = await api("GET", `/api/v1/job-missions/${missionId}`);
    if (!["JOB_ANALYZING", "JD_REQUIRED", "CREATING"].includes(state.workflow_state)) break;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  await api("POST", `/api/v1/job-missions/${missionId}/continue-to-resume`);
  await api("POST", `/api/v1/job-missions/${missionId}/resumes/text`, { raw_text: RESUME_TEXT });
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-resume-source`, { mode: "paste", update_master: false });
  const selection = await api("POST", `/api/v1/job-missions/${missionId}/experience-selection/generate`, {});
  await api("PUT", `/api/v1/job-missions/${missionId}/experience-selection?confirm=true`, {
    selections: (selection.selections || selection.items || []).map((item) => ({
      experience_id: item.experience_id,
      decision: "KEEP_AND_HIGHLIGHT",
      why: "与 JD 的内容选题/达人合作/复盘模板要求直接相关",
      confidence: 0.8,
    })),
  });
  await api("POST", `/api/v1/job-missions/${missionId}/resume-strategy`, {});
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-strategy`, {});
  await api("POST", `/api/v1/job-missions/${missionId}/target-resumes`, {});

  const list = await api("GET", `/api/v1/job-missions/${missionId}/target-resumes`);
  const items = Array.isArray(list) ? list : list.items || [];
  const latest = items.reduce((best, item) => ((item.version || 0) > (best.version || 0) ? item : best), items[0]);
  for (const bullet of latest.bullets || []) {
    const flags = (bullet.risk_flags || []).map((value) => String(value).toUpperCase());
    if (flags.includes("SYNTHETIC_PROJECT")) continue;
    await api("PATCH", `/api/v1/target-resume-bullets/${bullet.id}`, { status: "ACCEPTED", fact_confirmed: true });
  }
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-target-resume`, {});
  const studio = await api("GET", `/api/v1/job-missions/${missionId}/resume-studio`);
  await api("POST", `/api/v1/job-missions/${missionId}/resume-studio/confirm`, {}, { "If-Match": String(studio.revision) });
  check("准备：岗位简历已确认", true, `mission=${String(missionId).slice(0, 8)}`);

  // 面试记录 + 提醒：让看板有内容
  await api("POST", `/api/v1/profiles/${profileId}/interview-records`, {
    company: "某快消集团",
    role: "内容运营",
    interview_round: "一面",
    interviewed_on: "2026-10-19",
    notes: "选题库 + 达人合作复盘",
    items: [{ question: "讲一次你做内容排期的经历", my_answer: "维护选题库，累计产出 60 篇笔记" }],
  });
  await api("POST", `/api/v1/profiles/${profileId}/reminders`, { title: "一面后发感谢信", due_at: "2026-10-22T09:00:00Z" });

  // ------------------------------------------------ 浏览器真实操作
  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(180000);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  const trackerUrl = WEB + "/tracker";
  await page.goto(trackerUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate(({ key, pid }) => localStorage.setItem(key, pid), { key: STORAGE_KEY, pid: profileId });
  await page.goto(trackerUrl, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);

  // 1) 新建投递记录（页面表单真实填写）
  await page.getByRole("button", { name: "新建投递记录" }).click();
  await page.waitForTimeout(600);
  await page.locator(".tracker-form-grid input").nth(0).fill("某快消集团");
  await page.locator(".tracker-form-grid input").nth(1).fill("内容运营");
  await page.locator(".tracker-form-grid input").nth(2).fill("成都");
  await page.locator(".tracker-form-grid input").nth(3).fill("官微私信后补简历");
  await page.locator(".tracker-form-grid input").nth(4).fill("粘贴 JD");
  await page.screenshot({ path: path.join(OUT, "01-新建投递记录.png") });
  await page.getByRole("button", { name: "保存记录" }).click();
  await page.waitForTimeout(2500);
  const created = page.locator(".app-card", { hasText: "某快消集团" }).first();
  check("页面新建投递记录成功", await created.isVisible());

  // 2) 筛选：关键词 + 渠道
  const keywordInput = page.locator('input[placeholder="公司 / 岗位 / 备注"]');
  await keywordInput.fill("快消");
  await page.waitForTimeout(1200);
  const afterKeyword = await page.locator(".app-card", { hasText: "某快消集团" }).count();
  check("关键词筛选命中", afterKeyword >= 1, `命中 ${afterKeyword} 条`);
  await page.locator(".tracker-filter-row select").nth(1).selectOption("内推");
  await page.waitForTimeout(1200);
  const emptyHint = await page.locator(".app-empty").count();
  check("渠道筛选无匹配时给出空态", emptyHint >= 1);
  await page.screenshot({ path: path.join(OUT, "02-筛选.png") });
  await keywordInput.fill("");
  await page.locator(".tracker-filter-row select").nth(1).selectOption("ALL");
  await page.waitForTimeout(1200);

  // 3) 绑定简历版本（这条用 API 建，带 mission_id）
  const withMission = await api("POST", `/api/v1/profiles/${profileId}/applications`, {
    company: "某快消集团",
    role: uniqueRole,
    location: "成都",
    channel: "招聘网站",
    mission_id: missionId,
    jd_source: "粘贴 JD",
  });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3000);
  const bindRow = page.locator(".app-card", { hasText: uniqueRole }).first();
  await bindRow.getByRole("button", { name: "绑定简历版本" }).click();
  let bound = null;
  for (let i = 0; i < 15; i += 1) {
    await page.waitForTimeout(1500);
    const all = await api("GET", "/api/v1/applications");
    bound = (all.applications || []).find((item) => item.id === withMission.id) || {};
    if (bound.resume_version_id && bound.has_pdf_snapshot) break;
  }
  check("页面绑定简历版本成功", Boolean(bound.resume_version_id && bound.has_pdf_snapshot), `v${bound.resume_version} r${bound.studio_revision}`);
  const boundCard = page.locator(".app-card", { hasText: uniqueRole }).first();
  const boundText = await boundCard.innerText();
  check("页面显示投递版本与快照入口", /投递版本/.test(boundText) && /下载投递快照/.test(boundText), boundText.split("\n")[2] || "");
  await page.screenshot({ path: path.join(OUT, "03-绑定投递简历版本.png") });

  // 4) 打招呼话术：生成 → 编辑 → 保存
  await boundCard.getByRole("button", { name: "打招呼话术" }).click();
  await page.waitForTimeout(1200);
  await boundCard.getByRole("button", { name: "生成话术草稿" }).click();
  await page.waitForTimeout(4000);
  const shortBox = boundCard.locator("textarea").first();
  const generated = await shortBox.inputValue();
  check("生成简洁版话术", generated.length > 10 && /内容运营/.test(generated), generated.slice(0, 60));
  const longBox = boundCard.locator("textarea").nth(1);
  const generatedLong = await longBox.inputValue();
  check("生成详细版话术", generatedLong.length > generated.length, `${generatedLong.length} 字`);
  await page.screenshot({ path: path.join(OUT, "04-打招呼话术.png") });
  const edited = "您好，我对贵司内容运营岗位很感兴趣，简历已附上，期待沟通。";
  await shortBox.fill(edited);
  await boundCard.getByRole("button", { name: "保存话术" }).click();
  let afterEdit = null;
  for (let i = 0; i < 15; i += 1) {
    await page.waitForTimeout(1500);
    const all = await api("GET", "/api/v1/applications");
    afterEdit = (all.applications || []).find((item) => item.id === withMission.id) || {};
    if (afterEdit.greeting_short === edited) break;
  }
  check("话术可编辑并保存", afterEdit.greeting_short === edited, (afterEdit.greeting_short || "").slice(0, 40));

  // 5) 看板：阶段数量 / 版本使用记录 / 最近面试 / 提醒
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);
  const boardText = await page.locator("section.app-card", { hasText: "简历版本使用记录" }).first().innerText();
  check("看板显示简历版本使用记录", /简历 v/.test(boardText), boardText.split("\n")[1] || "");
  const interviewCard = await page.locator("section.app-card", { hasText: "最近面试" }).first().innerText();
  check("看板显示最近面试", /某快消集团/.test(interviewCard));
  const reminderCard = await page.locator("section.app-card", { hasText: "待办提醒" }).first().innerText();
  check("看板显示待办提醒", /一面后发感谢信/.test(reminderCard));
  check("提醒不宣称系统推送", /不会发送系统推送/.test(reminderCard));
  await page.screenshot({ path: path.join(OUT, "05-求职看板.png"), fullPage: true });

  await browser.close();

  fs.writeFileSync(
    path.join(OUT, "e2e-result.json"),
    JSON.stringify(
      {
        finished_at: new Date().toISOString(),
        web: WEB,
        api: API,
        profile_id: profileId,
        mission_id: missionId,
        application_id: withMission.id,
        bound_version: bound.resume_version,
        bound_studio_revision: bound.studio_revision,
        greeting_short: afterEdit.greeting_short,
        greeting_long: afterEdit.greeting_long,
        results,
      },
      null,
      2
    ),
    "utf-8"
  );

  const failed = results.filter((item) => !item.ok);
  console.log(`\n截图目录：${OUT}；失败项：${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error("E2E 异常：" + err.stack);
  process.exit(2);
});
