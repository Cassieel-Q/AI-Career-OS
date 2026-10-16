/**
 * Overnight Sprint M1：岗位广场「任务化一键采集」真实浏览器 E2E。
 *
 * 真实点击页面按钮完成：
 *   1) 多关键词 + 来源 → 开始采集（任务接口，轮询进度）
 *   2) 统计条区分「抓到 / 新增 / 已存在 / 待确认 / 可保存」
 *   3) 来源自检（真实请求该来源的健康接口）
 *   4) 勾选 → 批量导入 → 数据真的进岗位库
 *   5) 直接点「匹配分析」进入Mission JD 分析
 *   6) 用户取消采集 → 任务状态变为「已取消」
 *
 * 前置：后端 8100、前端 3000、浏览器桥 8770 已启动。
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
const OUT = path.resolve(__dirname, "../../../docs/screenshots/overnight-m1");
const STORAGE_KEY = "ai-career-os-dogfood-profile-id";

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });

  const draft = await (await fetch(API + "/api/v1/profiles/draft", { method: "POST" })).json();
  const profileId = draft.profile_id || draft.id;
  check("创建本地档案", Boolean(profileId), String(profileId).slice(0, 8));

  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1500, height: 1080 } });
  const page = await context.newPage();
  page.setDefaultTimeout(120000);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.evaluate(({ key, pid }) => localStorage.setItem(key, pid), { key: STORAGE_KEY, pid: profileId });
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);

  // ---------------------------------------------------------------- 1) 采集任务
  const keywordInput = page.locator('input[placeholder="输入后回车添加，例如：AI 产品经理"]');
  for (const kw of ["product manager", "AI 产品经理"]) {
    await keywordInput.fill(kw);
    await keywordInput.press("Enter");
  }
  // 默认来源里已勾选 remoteok，这里再补 remotive
  await page.locator('.app-chip-row button:has-text("Remotive")').first().click();
  await page.screenshot({ path: path.join(OUT, "01-collect-form.png"), fullPage: false });

  await page.locator('button.primary:has-text("开始采集")').click();
  await page.waitForSelector('section[aria-label="采集结果"]', { timeout: 120000 }).catch(() => {});
  await page.waitForTimeout(1500);
  const statText = await page.locator(".app-stat-row").first().innerText().catch(() => "");
  check("统计条区分抓到与新增", /抓到/.test(statText) && /新增/.test(statText) && /可保存/.test(statText), statText.replace(/\n/g, " ").slice(0, 140));
  await page.screenshot({ path: path.join(OUT, "02-collect-result.png"), fullPage: false });

  const rows = page.locator('section[aria-label="采集结果"] tbody tr');
  const rowCount = await rows.count();
  check("采集结果表格有真实行", rowCount > 0, `${rowCount} 行`);

  // ---------------------------------------------------------------- 2) 批量保存
  await page.locator('button.primary:has-text("批量导入选中岗位")').click();
  await page.waitForTimeout(3500);
  const infoText = await page.locator(".app-row .app-muted").first().innerText().catch(() => "");
  const savedMatch = /新增保存 (\d+) 条/.exec(await page.locator("body").innerText());
  check("批量导入真的写入岗位库", Boolean(savedMatch) && Number(savedMatch[1]) > 0, savedMatch ? `新增保存 ${savedMatch[1]} 条` : "未出现保存结果提示");
  await page.screenshot({ path: path.join(OUT, "03-batch-saved.png"), fullPage: false });

  const libraryCount = await page.locator('section[aria-label="岗位库"] tbody tr').count().catch(() => 0);
  check("岗位库出现刚保存的岗位", libraryCount > 0, `${libraryCount} 条`);

  // ---------------------------------------------------------------- 3) 来源自检
  const healthBtn = page.locator('button:text-is("自检")').first();
  await healthBtn.click();
  await page.waitForTimeout(6000);
  const healthText = await page.locator("body").innerText();
  check("来源自检返回真实结果", /自检结果 ·/.test(healthText), (/自检结果 · [^\n]+/.exec(healthText) || [""])[0].slice(0, 80));
  await page.screenshot({ path: path.join(OUT, "04-source-health.png"), fullPage: false });

  // ---------------------------------------------------------------- 4) 进入 JD 分析（对已入库的行直接打开）
  const beforeUrl = page.url();
  const matchBtn = page.locator('section[aria-label="采集结果"] tbody tr button:has-text("匹配分析")').first();
  await matchBtn.click();
  await page.waitForTimeout(25000);
  const afterUrl = page.url();
  check("匹配分析进入 Mission 页", afterUrl !== beforeUrl && /missions/.test(afterUrl), afterUrl.slice(0, 90));
  await page.screenshot({ path: path.join(OUT, "05-mission-entry.png"), fullPage: false });

  // ---------------------------------------------------------------- 5) 取消采集
  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await page.locator('.app-chip-row button:has-text("Greenhouse")').first().click();
  await page.locator('input[placeholder*="Greenhouse 招聘板标识"]').fill("stripe,airbnb,figma,databricks,reddit,roblox");
  await page.locator('button.primary:has-text("开始采集")').click();
  await page.waitForTimeout(1200);
  await page.locator('button:has-text("取消采集")').click();
  await page.waitForTimeout(9000);
  const cancelText = await page.locator("body").innerText();
  check("用户取消后任务状态为已取消", /任务状态：已取消/.test(cancelText), (/任务状态：[^\s]+/.exec(cancelText) || [""])[0]);
  await page.screenshot({ path: path.join(OUT, "06-cancelled.png"), fullPage: false });

  const failed = results.filter((item) => !item.ok);
  fs.writeFileSync(
    path.join(OUT, "e2e-result.json"),
    JSON.stringify({ ran_at: new Date().toISOString(), total: results.length, passed: results.length - failed.length, failed: failed.length, results }, null, 2),
    "utf8",
  );
  console.log(`\n${results.length - failed.length}/${results.length} 通过`);
  await browser.close();
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error("E2E 崩溃：", err);
  process.exit(3);
});
