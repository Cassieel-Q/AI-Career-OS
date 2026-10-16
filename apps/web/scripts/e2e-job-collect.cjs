/**
 * 岗位广场「一键采集」真实 E2E。
 *
 * 用真实浏览器打开 AI Career OS 的 /jobs 页面，真实点击按钮完成：
 *   1) 多关键词 + 城市 + 实习/全职 + 来源筛选 → 开始采集 → 查看进度与统计
 *   2) 勾选结果 → 批量导入岗位库
 *   3) 「采集当前招聘网页」：职位详情页成功解析 / 列表页明确提示不支持
 *
 * 运行前需已启动：后端(8100)、前端(3000)、受控浏览器桥(8770)。
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
const BRIDGE = process.env.AIOS_BRIDGE || "http://127.0.0.1:8770";
const OUT = path.resolve(__dirname, "../../../docs/screenshots/job-collect");

const results = [];
function check(name, ok, detail) {
  results.push({ name, ok, detail });
  console.log(`${ok ? "PASS" : "FAIL"} ${name}${detail ? " — " + detail : ""}`);
}

async function bridgeCall(method, p, body) {
  const tokenFile = path.join(process.env.LOCALAPPDATA || "", "AICareerOS", "browser-bridge.token");
  const token = fs.existsSync(tokenFile) ? fs.readFileSync(tokenFile, "utf8").trim() : "";
  const res = await fetch(BRIDGE + p, {
    method,
    headers: { "Content-Type": "application/json", Authorization: "Bearer " + token },
    body: body ? JSON.stringify(body) : undefined,
  });
  return res.json();
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });

  // 0) 准备档案
  const draft = await (await fetch(API + "/api/v1/profiles/draft", { method: "POST" })).json();
  const profileId = draft.profile_id || draft.id;
  check("创建/复用本地档案", Boolean(profileId), String(profileId).slice(0, 8));

  const browser = await playwright.chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 1100 } });
  const page = await context.newPage();
  page.setDefaultTimeout(90000);
  page.setDefaultNavigationTimeout(120000);
  page.on("pageerror", (err) => console.log("[pageerror]", err.message));

  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.evaluate((pid) => {
    localStorage.setItem("ai-career-os-dogfood-profile-id", pid);
  }, profileId);
  await page.reload({ waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);

  // ---------------------------------------------------------------- 1) 多关键词采集
  const keywordInput = page.locator('input[placeholder="输入后回车添加，例如：AI 产品经理"]');
  for (const kw of ["product manager", "AI 产品经理"]) {
    await keywordInput.fill(kw);
    await keywordInput.press("Enter");
  }
  const chips = await page.locator(".app-chip-row .app-chip").allInnerTexts();
  check("多关键词已添加为 chips", chips.filter((t) => t.includes("product manager") || t.includes("AI 产品经理")).length >= 2, chips.slice(0, 4).join(" | "));

  await page.locator('select').first().selectOption("ANY");
  // 勾选 Greenhouse 来源并填写真实招聘板标识
  await page.locator('.app-chip-row button:has-text("Greenhouse")').click();
  await page.locator('input[placeholder*="Greenhouse 招聘板标识"]').fill("stripe,airbnb");

  await page.screenshot({ path: path.join(OUT, "01-collect-form.png"), fullPage: true });

  await page.locator('button:has-text("开始采集")').click();
  await page.waitForSelector("text=2 · 采集结果", { timeout: 120000 });
  await page.waitForTimeout(1200);

  const statRow = await page.locator(".app-stat-row").innerText();
  const progress = await page.locator(".app-progress-list").innerText();
  check("采集返回分来源报告", /来源成功/.test(statRow), statRow.replace(/\n/g, " "));
  check("采集进度逐来源可见", progress.includes("remoteok") && progress.includes("greenhouse"), progress.split("\n")[0]);

  const rowCount = await page.locator('section[aria-label="采集结果"] tbody tr').count();
  check("采集结果表格有真实岗位行", rowCount > 0, `${rowCount} 行`);
  await page.screenshot({ path: path.join(OUT, "02-collect-results.png"), fullPage: true });

  // JD 预览可展开
  await page.locator('section[aria-label="采集结果"] tbody tr').first().locator('button:has-text("展开")').click();
  const jdText = await page.locator(".jd-preview").first().innerText();
  check("JD 预览可展开且有正文", jdText.length > 30, `${jdText.length} 字`);

  // ---------------------------------------------------------------- 2) 批量导入
  await page.locator('button:has-text("批量导入选中岗位")').click();
  await page.waitForTimeout(3500);
  const libraryText = await page.locator('section[aria-label="岗位库"] h2').innerText();
  check("批量导入后岗位库有记录", /（[1-9]/.test(libraryText), libraryText);
  await page.screenshot({ path: path.join(OUT, "03-library-after-import.png"), fullPage: true });

  // 岗位库该行出现「匹配分析 / 生成岗位定向简历」
  const firstRow = page.locator('section[aria-label="岗位库"] tbody tr').first();
  const rowText = await firstRow.innerText();
  check("岗位库每行直达匹配分析/定向简历", rowText.includes("匹配分析") && rowText.includes("生成岗位定向简历"), rowText.replace(/\n/g, " ").slice(0, 80));

  // ---------------------------------------------------------------- 3) 采集当前招聘网页（详情页）
  await bridgeCall("POST", "/session/open", { url: WEB + "/job-detail-test.html" });
  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2500);
  const bridgeBadge = await page.locator('section[aria-label="采集当前招聘网页"] .app-badge').first().innerText();
  check("页面显示浏览器桥已连接", bridgeBadge.includes("已连接"), bridgeBadge);

  await page.locator('button:has-text("采集当前网页")').click();
  await page.waitForSelector("text=预览（确认后再入库）", { timeout: 60000 });
  const previewInputs = await page.locator(".app-card.nested .app-filter-row input").evaluateAll((els) => els.map((e) => e.value));
  check("网页采集解析出企业/岗位/地点", previewInputs[0] === "星河科技" && previewInputs[1] === "AI 产品经理" && previewInputs[2].includes("北京"), previewInputs.join(" | "));
  const jdBox = await page.locator(".app-card.nested textarea").inputValue();
  check("网页采集解析出 JD 正文", jdBox.includes("RAG") || jdBox.includes("大模型"), `${jdBox.length} 字`);
  await page.screenshot({ path: path.join(OUT, "04-browser-capture-preview.png"), fullPage: true });

  await page.locator('button:has-text("确认并保存到岗位库")').click();
  await page.waitForTimeout(3000);
  const libAfter = await page.locator('section[aria-label="岗位库"] h2').innerText();
  check("网页采集结果入库", /（[1-9]/.test(libAfter), libAfter);
  await page.screenshot({ path: path.join(OUT, "05-after-capture-save.png"), fullPage: true });

  // ---------------------------------------------------------------- 4) 列表页明确不支持
  await bridgeCall("POST", "/session/open", { url: WEB + "/job-listing-test.html" });
  await page.goto(WEB + "/jobs", { waitUntil: "domcontentloaded" });
  await page.waitForTimeout(2000);
  await page.locator('button:has-text("采集当前网页")').click();
  await page.waitForSelector(".app-inline-error", { timeout: 60000 });
  const bodyText = await page.locator("main.app-page").innerText();
  check("列表页明确提示仅支持单职位导入", bodyText.includes("列表页"), bodyText.split("\n").find((l) => l.includes("列表页")) || "");
  await page.screenshot({ path: path.join(OUT, "06-listing-unsupported.png"), fullPage: true });

  await browser.close();

  const failed = results.filter((r) => !r.ok);
  fs.writeFileSync(
    path.join(OUT, "e2e-result.json"),
    JSON.stringify({ ran_at: new Date().toISOString(), total: results.length, passed: results.length - failed.length, failed: failed.length, results }, null, 2),
    "utf8",
  );
  console.log(`\n合计 ${results.length} 项，通过 ${results.length - failed.length}，失败 ${failed.length}`);
  process.exit(failed.length ? 1 : 0);
})().catch((err) => {
  console.error("E2E 异常：" + err.stack);
  process.exit(1);
});
