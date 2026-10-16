/**
 * Overnight Sprint M2：Resume Studio「一键更新」真实浏览器 E2E。
 *
 * 真实点击页面完成：
 *   1) 用真实接口把 Mission 推进到「有新版已确认改写稿」状态
 *   2) 工作台手工新增一条内容（差异弹窗必须提示它会被替换）
 *   3) 页面出现「发现新版已确认改写稿」→ 点「查看差异并确认」→ 差异弹窗截图
 *   4) 点「先不更新」→ 修订号不变（用户不确认就不动正文）
 *   5) 再打开 → 点「确认更新（生成新修订版）」→ 修订号 +1
 *   6) 换模板 → 正文逐条不变（换模板只换版式）
 *   7) 刷新页面 → 修订号与正文都还在
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
const OUT = path.resolve(__dirname, "../../../docs/screenshots/overnight-m2");
const STORAGE_KEY = "ai-career-os-dogfood-profile-id";

const RESUME_TEXT = `王五
电话：13700000000  邮箱：wangwu@example.com  城市：深圳

教育背景
某大学 软件工程 本科 2020.09 - 2024.06

实习经历
某科技公司 后端开发实习 2023.07 - 2024.01
- 参与订单服务重构，把下单接口平均响应时间从 480ms 降到 210ms
- 搭建灰度发布与回滚流程，覆盖 6 个核心服务
- 补齐单元测试与 CI 卡点，主分支回归缺陷数下降约 40%

项目经历
分布式任务调度器 2022.10 - 2023.04
- 设计基于优先级队列的调度器，支撑每日 30 万次任务执行
- 实现失败重试与幂等控制，重复执行率降到 0.1% 以下

技能
Java / Go / MySQL / Redis / Kafka / Docker
`;

const JD_TEXT = `后端开发工程师（深圳）
岗位职责：
1. 负责交易/订单相关服务的设计与开发，保障接口性能与稳定性；
2. 参与服务重构与性能优化，定位并解决线上问题；
3. 建设发布、监控与回归质量流程，降低故障率；
4. 编写技术文档，配合产品完成需求落地。
任职要求：
1. 本科及以上学历，计算机相关专业；
2. 熟悉 Java 或 Go，理解并发与常用中间件；
3. 有性能优化或分布式系统项目经验者优先；
4. 具备良好的工程习惯，重视测试与代码质量。
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

async function acceptBullets(missionId) {
  const list = await api("GET", `/api/v1/job-missions/${missionId}/target-resumes`);
  const items = Array.isArray(list) ? list : list.items || [];
  const latest = items.reduce((best, item) => ((item.version || 0) > (best.version || 0) ? item : best), items[0]);
  let accepted = 0;
  let skipped = 0;
  for (const bullet of latest.bullets || []) {
    const flags = (bullet.risk_flags || []).map((value) => String(value).toUpperCase());
    if (flags.includes("SYNTHETIC_PROJECT")) {
      skipped += 1;
      continue;
    }
    const result = await api("PATCH", `/api/v1/target-resume-bullets/${bullet.id}`, { status: "ACCEPTED", fact_confirmed: true });
    if (result && !result.__http_error) accepted += 1;
    else skipped += 1;
  }
  return { version: latest.version, accepted, skipped };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });

  // ------------------------------------------------ 用真实接口把 Mission 推到可更新状态
  const draft = await api("POST", "/api/v1/profiles/draft");
  const profileId = draft.profile_id || draft.id;
  check("创建本地档案", Boolean(profileId), String(profileId).slice(0, 8));

  await api("POST", `/api/v1/profiles/${profileId}/resumes/text`, { raw_text: RESUME_TEXT });
  await api("POST", `/api/v1/profiles/${profileId}/confirm`);

  const mission = await api("POST", `/api/v1/profiles/${profileId}/job-missions`, { raw_text: JD_TEXT });
  const missionId = mission.mission_id || mission.id;
  check("创建岗位 Mission", Boolean(missionId), String(missionId).slice(0, 8));

  for (let i = 0; i < 60; i += 1) {
    const state = await api("GET", `/api/v1/job-missions/${missionId}`);
    if (!["JOB_ANALYZING", "JD_REQUIRED", "CREATING"].includes(state.workflow_state)) break;
    await new Promise((resolve) => setTimeout(resolve, 3000));
  }
  await api("POST", `/api/v1/job-missions/${missionId}/continue-to-resume`);
  await api("POST", `/api/v1/job-missions/${missionId}/resumes/text`, { raw_text: RESUME_TEXT });
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-resume-source`, { mode: "paste", update_master: false });

  const selection = await api("POST", `/api/v1/job-missions/${missionId}/experience-selection/generate`, {});
  const selections = (selection.selections || selection.items || []).map((item) => ({
    experience_id: item.experience_id,
    decision: "KEEP_AND_HIGHLIGHT",
    why: "与 JD 的服务重构/性能优化/工程质量要求直接相关",
    confidence: 0.8,
  }));
  await api("PUT", `/api/v1/job-missions/${missionId}/experience-selection?confirm=true`, { selections });
  await api("POST", `/api/v1/job-missions/${missionId}/resume-strategy`, {});
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-strategy`, {});

  await api("POST", `/api/v1/job-missions/${missionId}/target-resumes`, {});
  const v1 = await acceptBullets(missionId);
  check("v1 逐条接受要点", v1.accepted > 0, `accepted=${v1.accepted} skipped=${v1.skipped}`);
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-target-resume`, {});

  const studioBase = `/api/v1/job-missions/${missionId}/resume-studio`;
  let studio = await api("GET", studioBase);
  check("Studio 初始导入", Boolean(studio && studio.revision !== undefined), `revision=${studio.revision}`);

  // 手工新增一条内容：差异弹窗必须提示它会被替换
  const firstEntry = studio.document.sections[0].entries[0];
  const manual = await api(
    "PATCH",
    studioBase,
    { type: "add_bullet", entry_id: firstEntry.id, text: "手工补充：补齐了灰度发布的回滚演练记录。" },
    { "If-Match": String(studio.revision) }
  );
  check("工作台手工新增内容", !manual.__http_error, `revision=${manual.revision}`);

  // 生成 v2 并确认 → 出现「新版已确认改写稿」
  await api("POST", `/api/v1/job-missions/${missionId}/target-resumes`, {});
  const v2 = await acceptBullets(missionId);
  check("v2 逐条接受要点", v2.accepted > 0, `accepted=${v2.accepted} skipped=${v2.skipped}`);
  await api("POST", `/api/v1/job-missions/${missionId}/confirm-target-resume`, {});

  const diff = await api("GET", `${studioBase}/source-diff`);
  check("检测到新版改写稿", diff.update_available === true, `new_source_version=${diff.new_source_version}`);
  check("差异提示人工编辑内容", (diff.manual_edit_count || 0) >= 1, `manual_edit_count=${diff.manual_edit_count}`);
  check("板块级差异有真实条数", (diff.sections || []).some((item) => item.added.length + item.removed.length + item.kept > 0),
    (diff.sections || []).map((item) => `${item.section}:${item.status}`).join(" | "));

  // ------------------------------------------------ 浏览器真实操作
  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1500, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(120000);
  page.setDefaultNavigationTimeout(180000);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  const studioUrl = `${WEB}/missions/${missionId}/resume/studio`;
  await page.goto(studioUrl, { waitUntil: "domcontentloaded" });
  await page.evaluate(({ key, pid }) => localStorage.setItem(key, pid), { key: STORAGE_KEY, pid: profileId });
  await page.goto(studioUrl, { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(4000);

  const banner = page.locator(".rs-source-update");
  await banner.first().waitFor({ state: "visible", timeout: 60000 });
  await page.screenshot({ path: path.join(OUT, "01-发现新版改写稿.png"), fullPage: false });
  check("页面出现新版更新提示", await banner.first().isVisible());

  // 打开差异弹窗
  await page.getByRole("button", { name: "查看差异并确认" }).first().click();
  const modal = page.locator(".rs-diff-modal");
  await modal.waitFor({ state: "visible", timeout: 30000 });
  await page.waitForTimeout(1200);
  await page.screenshot({ path: path.join(OUT, "02-差异确认弹窗.png"), fullPage: false });
  check("差异弹窗打开", await modal.isVisible());

  const modalText = await modal.innerText();
  check("弹窗列出板块差异", /工作与项目经历|实习经历|项目经历/.test(modalText), modalText.slice(0, 80).replace(/\n/g, " "));
  check("弹窗警告人工编辑会被替换", /手工|替换/.test(modalText));

  // 先不更新 → 修订号必须不变
  const revisionBefore = (await api("GET", studioBase)).revision;
  await page.getByRole("button", { name: "先不更新" }).click();
  await page.waitForTimeout(1500);
  const revisionAfterCancel = (await api("GET", studioBase)).revision;
  check("点「先不更新」不动正文", revisionBefore === revisionAfterCancel, `${revisionBefore} → ${revisionAfterCancel}`);
  await page.screenshot({ path: path.join(OUT, "03-取消更新后仍保留原稿.png"), fullPage: false });

  // 再打开 → 确认更新
  await page.getByRole("button", { name: "更新到工作台" }).first().click();
  await modal.waitFor({ state: "visible", timeout: 30000 });
  await page.getByRole("button", { name: "确认更新（生成新修订版）" }).click();
  await page.waitForTimeout(4000);
  const afterReimport = await api("GET", studioBase);
  check("确认更新后修订号 +1", afterReimport.revision === revisionBefore + 1, `${revisionBefore} → ${afterReimport.revision}`);
  await page.screenshot({ path: path.join(OUT, "04-更新完成新修订版.png"), fullPage: false });

  // 换模板：正文必须一条不变
  const textsBefore = [];
  for (const section of afterReimport.document.sections || []) {
    for (const entry of section.entries || []) {
      for (const bullet of entry.bullets || []) if (bullet.text) textsBefore.push(bullet.text);
    }
  }
  const templateSwitched = await api("PATCH", studioBase, { type: "set_template", template_id: "zh-sidebar" }, { "If-Match": String(afterReimport.revision) });
  check("切换模板成功", templateSwitched.template_id === "zh-sidebar", String(templateSwitched.template_id));
  const textsAfter = [];
  for (const section of (templateSwitched.document || {}).sections || []) {
    for (const entry of section.entries || []) {
      for (const bullet of entry.bullets || []) if (bullet.text) textsAfter.push(bullet.text);
    }
  }
  check(
    "换模板不改正文",
    textsBefore.length > 0 && textsBefore.length === textsAfter.length && textsBefore.every((text) => textsAfter.includes(text)),
    `${textsBefore.length} → ${textsAfter.length} 条`
  );
  await page.waitForTimeout(2500);
  await page.screenshot({ path: path.join(OUT, "05-换模板后正文不变.png"), fullPage: false });

  // 刷新恢复
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(4000);
  const reloaded = await api("GET", studioBase);
  check("刷新后修订号保持", reloaded.revision === templateSwitched.revision, `${reloaded.revision}`);
  check("刷新后模板保持", reloaded.template_id === "zh-sidebar", String(reloaded.template_id));
  await page.screenshot({ path: path.join(OUT, "06-刷新后恢复.png"), fullPage: false });

  await browser.close();

  const payload = {
    finished_at: new Date().toISOString(),
    web: WEB,
    api: API,
    mission_id: missionId,
    profile_id: profileId,
    revision_before_update: revisionBefore,
    revision_after_update: afterReimport.revision,
    manual_edit_count: diff.manual_edit_count,
    sections: (diff.sections || []).map((item) => ({ section: item.section, status: item.status, added: item.added.length, removed: item.removed.length, kept: item.kept })),
    results,
  };
  fs.writeFileSync(path.join(OUT, "e2e-result.json"), JSON.stringify(payload, null, 2), "utf-8");

  const failed = results.filter((item) => !item.ok);
  console.log(`\n截图目录：${OUT}；失败项：${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error("E2E 异常：" + err.stack);
  process.exit(2);
});
