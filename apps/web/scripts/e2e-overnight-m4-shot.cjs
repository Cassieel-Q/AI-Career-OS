/**
 * M4 视觉证据：本地测试表单「填写前 / 按计划填写后」截图。
 * 值与 webform_acceptance.py 的真实验收一致（同一档案事实）。
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

const OUT = path.resolve(__dirname, "../../../docs/screenshots/overnight-m4");
const FORM_URL = process.env.AIOS_FORM || "http://127.0.0.1:8123/index.html";

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  const browser = await playwright.chromium.launch({ headless: true });
  const page = await browser.newPage({ viewport: { width: 1100, height: 1400 } });
  await page.goto(FORM_URL, { waitUntil: "domcontentloaded" });
  await page.screenshot({ path: path.join(OUT, "01-填写前.png"), fullPage: true });

  // 按 MATCHED 计划填写（与验收脚本一致；密码/验证码/checkbox/文件/禁用控件不动）
  await page.fill("#f-name", "周八");
  await page.fill("#f-phone", "13400000000");
  await page.fill("#f-email", "zhouba@example.com");
  await page.fill("#f-city", "成都");
  await page.selectOption("#f-degree", { label: "本科" });
  await page.fill("#f-grad", "2024-06");
  await page.fill("#f-major", "市场营销");
  await page.screenshot({ path: path.join(OUT, "02-按计划填写后.png"), fullPage: true });

  const state = await page.evaluate(() => ({
    name: document.querySelector("#f-name").value,
    agree: document.querySelector("#f-agree").checked,
    pass: document.querySelector("#f-pass").value,
    captcha: document.querySelector("#f-captcha").value,
    frozen: document.querySelector("#f-frozen").value,
  }));
  console.log(JSON.stringify(state));
  await browser.close();
  process.exit(0);
})().catch((err) => {
  console.error(err.stack);
  process.exit(2);
});
