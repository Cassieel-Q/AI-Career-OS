/**
 * 48 小时冲刺交付截图：真实本地运行时的浏览器实拍（非静态 mock）。
 * 用法：node scripts/capture-48h.cjs
 */
"use strict";

const fs = require("fs");
const path = require("path");
const { chromium } = require("playwright");

const WEB = process.env.WEB_BASE || "http://127.0.0.1:3000";
const OUT = process.env.SHOT_DIR || path.resolve(__dirname, "../../../docs/screenshots/resumeforge-48h");

const PAGES = [
  { name: "01-jobs-intake", url: `${WEB}/jobs` },
  { name: "02-webform", url: `${WEB}/webform` },
  { name: "03-settings", url: `${WEB}/settings` },
  { name: "04-webform-test-page", url: `${WEB}/webform-test.html` },
];

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const report = [];
  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (err) => errors.push(String(err)));
  page.on("console", (msg) => {
    if (msg.type() === "error") errors.push(msg.text());
  });

  for (const item of PAGES) {
    const started = Date.now();
    try {
      const response = await page.goto(item.url, { waitUntil: "domcontentloaded", timeout: 45000 });
      await page.waitForTimeout(2500);
      const file = path.join(OUT, `${item.name}.png`);
      await page.screenshot({ path: file, fullPage: false });
      report.push({
        name: item.name,
        url: item.url,
        status: response ? response.status() : null,
        title: await page.title(),
        file: path.relative(process.cwd(), file),
        ms: Date.now() - started,
      });
      console.log(`[ok] ${item.name} HTTP ${response ? response.status() : "?"} → ${file}`);
    } catch (error) {
      report.push({ name: item.name, url: item.url, status: null, error: error.message });
      console.log(`[err] ${item.name} → ${error.message}`);
    }
  }

  fs.writeFileSync(
    path.join(OUT, "report.json"),
    JSON.stringify({ capturedAt: new Date().toISOString(), webBase: WEB, pages: report, consoleErrors: errors }, null, 2),
    "utf8",
  );

  await browser.close();
  const ok = report.filter((item) => item.status === 200).length;
  console.log(`\n===== 截图结果：${ok}/${PAGES.length} 个页面 HTTP 200 =====`);
  if (errors.length) {
    console.log("页面控制台错误：");
    errors.slice(0, 10).forEach((item) => console.log("  -", item));
  }
  process.exit(ok === PAGES.length ? 0 : 1);
})().catch((error) => {
  console.error(error);
  process.exit(1);
});
