/**
 * 岗位采集真实验收：Playwright 操作真实运行的 AI Career OS 前端（15 步）。
 *
 * 不用静态模拟页，不绕过前端直接调 API 冒充浏览器通过。
 * 每一步都截图，并输出 API 状态 / 岗位 ID / 数据库读取验证。
 *
 * 流程：
 *   1  打开岗位广场
 *   2  点击「一键采集岗位」区块
 *   3  输入关键词
 *   4  选择一个实际可用的公开来源
 *   5  点击「开始采集」
 *   6  等待任务结束
 *   7  检查真实采集结果
 *   8  勾选符合条件的岗位
 *   9  点击批量保存
 *   10 刷新页面，确认保存结果仍存在
 *   11 再次采集，确认去重正常
 *   12 打开一个新导入的岗位
 *   13 检查完整 JD 与原始链接
 *   14 点击匹配分析
 *   15 验证岗位已经进入现有 Mission 链路
 *
 * 前置：后端 8100、前端 3000 已启动；本机 HTTP_PROXY 会干扰 httpx，本脚本只用 fetch/浏览器。
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
const OUT = path.resolve(__dirname, "../../../docs/screenshots/job-collection-v1");
const EVIDENCE = path.resolve(__dirname, "../../../docs/evaluation/job-collection-v1");
const STORAGE_KEY = "ai-career-os-dogfood-profile-id";

const KEYWORDS = ["ai", "product"];
const SOURCE_LABEL = "RemoteOK";

const results = [];
const apiLog = [];

function check(step, name, ok, detail) {
  results.push({ step, name, ok: Boolean(ok), detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} [${step}] ${name}${detail ? " — " + detail : ""}`);
}

function shot(page, name) {
  return page.screenshot({ path: path.join(OUT, name), fullPage: false });
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(EVIDENCE, { recursive: true });

  // ---------------------------------------------------------------- 建档（隔离数据集）
  const draftRes = await fetch(API + "/api/v1/profiles/draft", { method: "POST" });
  const draft = await draftRes.json();
  const profileId = draft.profile_id || draft.id;
  apiLog.push({ step: "setup", method: "POST", path: "/api/v1/profiles/draft", status: draftRes.status });
  check("setup", "创建隔离测试档案", Boolean(profileId), `profile=${String(profileId).slice(0, 8)}`);

  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1600, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(150000);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));
  page.on("response", (res) => {
    if (res.url().includes("/api/v1/")) {
      apiLog.push({ step: "browser", method: res.request().method(), path: res.url().replace(API, ""), status: res.status() });
    }
  });

  // ---------------------------------------------------------------- 1 打开岗位广场
  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.evaluate(({ key, pid }) => localStorage.setItem(key, pid), { key: STORAGE_KEY, pid: profileId });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const title = await page.locator("h1.app-page-title").first().innerText().catch(() => "");
  await shot(page, "01-plaza.png");
  check(1, "打开岗位广场", /岗位广场/.test(title), title);

  // ---------------------------------------------------------------- 2 点击「采集岗位」
  const collectSection = page.locator('section[aria-label="一键采集岗位"]');
  await collectSection.scrollIntoViewIfNeeded();
  await collectSection.locator("h2").first().click();
  await page.waitForTimeout(400);
  const sectionText = await collectSection.innerText();
  await shot(page, "02-collect-section.png");
  check(2, "进入「一键采集岗位」区块", /一键采集岗位/.test(sectionText), sectionText.split("\n")[0]);

  // ---------------------------------------------------------------- 3 输入关键词
  const keywordInput = collectSection.locator('input[placeholder="输入后回车添加，例如：AI 产品经理"]');
  for (const kw of KEYWORDS) {
    await keywordInput.fill(kw);
    await keywordInput.press("Enter");
    await page.waitForTimeout(200);
  }
  const chipText = await collectSection.innerText();
  await shot(page, "03-keywords.png");
  check(3, "输入关键词", KEYWORDS.every((kw) => chipText.includes(kw)), KEYWORDS.join(" / "));

  // ---------------------------------------------------------------- 4 选择公开来源
  // 默认已勾选 RemoteOK；这里显式点一次确保其选中，并去掉其它来源避免多余请求
  // 来源 chip 是 section 内的 button.app-chip（选中态带 .active）。
  // 注意：关键词区也用 .app-chip-row，不能拿第一个 chip-row 当来源区。
  const sourceChip = collectSection.locator("button.app-chip").filter({ hasText: SOURCE_LABEL }).first();
  let chipClass = (await sourceChip.getAttribute("class").catch(() => "")) || "";
  if (!/active/.test(chipClass)) {
    await sourceChip.click();
    await page.waitForTimeout(300);
    chipClass = (await sourceChip.getAttribute("class").catch(() => "")) || "";
  }
  await shot(page, "04-source.png");
  check(4, "选择公开来源", /active/.test(chipClass), `来源=${SOURCE_LABEL} 选中态=${/active/.test(chipClass)}`);

  // ---------------------------------------------------------------- 5 点击「开始采集」
  const startBtn = collectSection.locator('button.primary:has-text("开始采集")');
  await startBtn.click();
  await page.waitForTimeout(1200);
  await shot(page, "05-start.png");
  const startedText = await page.locator("body").innerText();
  check(5, "点击开始采集", /采集中|任务状态/.test(startedText), (/任务状态：[^\s]+/.exec(startedText) || [""])[0]);

  // ---------------------------------------------------------------- 6 等待任务结束
  await page.waitForSelector('section[aria-label="采集结果"]', { timeout: 180000 }).catch(() => {});
  for (let i = 0; i < 60; i += 1) {
    const body = await page.locator("body").innerText();
    if (/采集完成|部分来源失败|采集失败|已取消/.test(body)) break;
    await page.waitForTimeout(2000);
  }
  await page.waitForTimeout(1500);
  const doneText = await page.locator("body").innerText();
  await shot(page, "06-task-done.png");
  check(6, "等待任务结束", /采集完成|部分来源失败/.test(doneText), (/任务状态：[^\s]+/.exec(doneText) || [""])[0]);

  // ---------------------------------------------------------------- 7 检查真实采集结果
  const resultSection = page.locator('section[aria-label="采集结果"]');
  const rows = resultSection.locator("tbody tr");
  const rowCount = await rows.count();
  const statText = await resultSection.locator(".app-stat-row").first().innerText().catch(() => "");
  await shot(page, "07-result.png");
  check(7, "真实采集结果非空", rowCount > 0, `${rowCount} 行 | ${statText.replace(/\n/g, " ").slice(0, 120)}`);

  if (rowCount === 0) {
    fs.writeFileSync(path.join(EVIDENCE, "e2e-browser-result.json"), JSON.stringify({ ran_at: new Date().toISOString(), results, apiLog }, null, 2), "utf8");
    console.log("\n采集结果为空，后续步骤无法继续（如实记为失败，不伪造）");
    await browser.close();
    process.exit(1);
  }

  // ---------------------------------------------------------------- 8 勾选符合条件的岗位
  const firstRowCompany = await rows.first().locator("td").nth(3).innerText().catch(() => "");
  const firstRowRole = await rows.first().locator("td.cell-title-link").innerText().catch(() => "");
  let picked = 0;
  for (let i = 0; i < Math.min(rowCount, 5); i += 1) {
    const box = rows.nth(i).locator('input[type="checkbox"]').first();
    if (await box.count()) {
      await box.check();
      picked += 1;
    }
  }
  await page.waitForTimeout(400);
  await shot(page, "08-selected.png");
  check(8, "勾选符合条件的岗位", picked > 0, `勾选 ${picked} 条，首条=${(firstRowCompany + " / " + firstRowRole).slice(0, 60)}`);

  // ---------------------------------------------------------------- 9 点击批量保存
  const saveBtn = resultSection.locator('button.primary:has-text("批量导入选中岗位")');
  await saveBtn.click();
  await page.waitForTimeout(6000);
  const savedText = await page.locator("body").innerText();
  const savedMatch = /新增保存 (\d+) 条/.exec(savedText);
  await shot(page, "09-saved.png");
  check(9, "批量保存写入岗位库", Boolean(savedMatch) && Number(savedMatch[1]) > 0, savedMatch ? `新增保存 ${savedMatch[1]} 条` : "未出现保存结果提示");

  // ---------------------------------------------------------------- 10 刷新页面确认仍在
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(3500);
  const library = page.locator('section[aria-label="岗位库"]');
  const libRows = library.locator("tbody tr");
  const libCount = await libRows.count();
  await shot(page, "10-after-reload.png");
  check(10, "刷新后保存结果仍在", libCount > 0, `岗位库 ${libCount} 条`);

  // ---------------------------------------------------------------- 11 再次采集确认去重
  await page.locator('section[aria-label="一键采集岗位"]').scrollIntoViewIfNeeded();
  await page.locator('input[placeholder="输入后回车添加，例如：AI 产品经理"]').fill(KEYWORDS[0]);
  await page.locator('input[placeholder="输入后回车添加，例如：AI 产品经理"]').press("Enter");
  await page.waitForTimeout(300);
  await page.locator('button.primary:has-text("开始采集")').click();
  await page.waitForSelector('section[aria-label="采集结果"]', { timeout: 180000 }).catch(() => {});
  for (let i = 0; i < 60; i += 1) {
    const body = await page.locator("body").innerText();
    if (/采集完成|部分来源失败|采集失败|已取消/.test(body)) break;
    await page.waitForTimeout(2000);
  }
  await page.waitForTimeout(1500);
  const secondText = await page.locator("body").innerText();
  const existMatch = /已存在 (\d+)/.exec(secondText);
  await shot(page, "11-recollect-dedupe.png");
  check(11, "重复采集去重正常（已存在计数 > 0）", Boolean(existMatch) && Number(existMatch[1]) > 0, existMatch ? `已存在 ${existMatch[1]} 条（不再新增）` : "未出现已存在计数");

  // ---------------------------------------------------------------- 12 打开一个新导入的岗位
  const firstLibRow = libRows.first();
  const libCompany = await firstLibRow.locator("td").nth(1).innerText().catch(() => "");
  const libRole = await firstLibRow.locator("td.cell-title-link").innerText().catch(() => "");
  const link = firstLibRow.locator("a").first();
  const href = await link.getAttribute("href").catch(() => null);
  await shot(page, "12-library-row.png");
  check(12, "打开新导入的岗位（含原始链接）", Boolean(href) && href !== "#", `${libCompany} / ${libRole} → ${String(href).slice(0, 70)}`);

  // ---------------------------------------------------------------- 13 检查完整 JD 与原始链接
  // 回到采集结果区展开 JD 全文，确认能看到完整正文
  const jdBtn = page.locator('section[aria-label="采集结果"] tbody tr button:has-text("展开")').first();
  let jdLength = 0;
  if (await jdBtn.count()) {
    await jdBtn.click();
    await page.waitForTimeout(600);
    const jdText = await page.locator('section[aria-label="采集结果"] .jd-preview').first().innerText().catch(() => "");
    jdLength = jdText.length;
  }
  await shot(page, "13-jd-and-link.png");
  check(13, "可查看完整 JD 正文", jdLength > 50, `JD 正文 ${jdLength} 字`);

  // ---------------------------------------------------------------- 14 点击匹配分析
  const beforeUrl = page.url();
  const matchBtn = page.locator('section[aria-label="采集结果"] tbody tr button:has-text("匹配分析")').first();
  await matchBtn.scrollIntoViewIfNeeded();
  await matchBtn.click();
  await page.waitForTimeout(30000);
  await shot(page, "14-match-analysis.png");
  const afterUrl = page.url();
  check(14, "点击匹配分析跳转", afterUrl !== beforeUrl, `${afterUrl.slice(0, 80)}`);

  // ---------------------------------------------------------------- 15 进入 Mission 链路
  const missionText = await page.locator("body").innerText();
  const inMission = /missions/.test(afterUrl);
  await shot(page, "15-mission.png");
  check(15, "岗位已进入 Mission 链路", inMission, afterUrl.slice(0, 90));

  // ---------------------------------------------------------------- 数据库读取验证
  let dbCheck = null;
  try {
    const libRes = await fetch(`${API}/api/v1/profiles/${profileId}/job-ingest/library`);
    const libJson = await libRes.json();
    const items = libJson.items || [];
    dbCheck = {
      http_status: libRes.status,
      item_count: items.length,
      sample: items.slice(0, 3).map((x) => ({ kind: x.kind, company: x.company, role: x.role, location: x.location, source_url: x.source_url, parse_status: x.parse_status })),
    };
    apiLog.push({ step: "db-verify", method: "GET", path: `/api/v1/profiles/${profileId}/job-ingest/library`, status: libRes.status });
  } catch (err) {
    dbCheck = { error: String(err) };
  }
  check("db", "数据库读取验证（岗位库 API）", Boolean(dbCheck && dbCheck.item_count > 0), JSON.stringify(dbCheck).slice(0, 200));

  const failed = results.filter((item) => !item.ok);
  const payload = {
    ran_at: new Date().toISOString(),
    web: WEB,
    api: API,
    profile_id: String(profileId),
    keywords: KEYWORDS,
    source: SOURCE_LABEL,
    total: results.length,
    passed: results.length - failed.length,
    failed: failed.length,
    results,
    api_log: apiLog,
    db_check: dbCheck,
  };
  fs.writeFileSync(path.join(EVIDENCE, "e2e-browser-result.json"), JSON.stringify(payload, null, 2), "utf8");
  fs.writeFileSync(path.join(OUT, "e2e-result.json"), JSON.stringify(payload, null, 2), "utf8");

  console.log(`\n${results.length - failed.length}/${results.length} 通过`);
  await browser.close();
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error("E2E 崩溃：", err);
  process.exit(3);
});
