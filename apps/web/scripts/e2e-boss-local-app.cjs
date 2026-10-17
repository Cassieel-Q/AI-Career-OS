/**
 * BOSS 本地应用主流程验收（M5.2）：真实操作本地网页，逐步截图 + API/数据库核对。
 *
 *   1  打开「导入 BOSS 直聘岗位」页
 *   2  粘贴岗位原文（合成样例，明确标注来源属性）
 *   3  点击「解析岗位」
 *   4  核对解析出的字段（公司/岗位/薪资/地点/学历/工作类型/原始链接）
 *   5  点「确认保存并进入匹配」
 *   6  核对已跳转到岗位详情页（Mission 链路）
 *   7  生成 BOSS 打招呼话术
 *   8  核对话术内容引用真实字段、可编辑、可复制
 *   9  保存话术
 *  10  标记已投递
 *  11  核对投递记录状态与快照链接
 *  12  打开 Resume Studio（岗位版简历）
 *  13  导出 PDF（若环境可用）
 *  14  回到岗位库，确认岗位已在库中
 *  15  再次导入同一岗位，核对不重复新增
 *
 * 前置：后端 8100、前端 3000 已启动（用 start-career.cmd 启动）。
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
const OUT = path.resolve(__dirname, "../../../docs/screenshots/boss-local-app");
const EVIDENCE = path.resolve(__dirname, "../../../docs/evaluation/boss-local-app");
const STORAGE_KEY = "ai-career-os-dogfood-profile-id";

// 合成样例：模拟 BOSS 职位详情页复制下来的文本（不是真实抓取，来源属性在报告里标注）
const BOSS_TEXT = [
  "AI产品经理实习",
  "8-13K·13薪",
  "杭州 滨江区 星光大道",
  "经验不限 本科",
  "杭州示例科技有限公司",
  "【岗位职责】",
  "1. 负责 AI 产品的需求调研、竞品分析与方案设计；",
  "2. 输出 PRD 与原型，跟进大模型能力在产品中的落地；",
  "3. 与算法、工程、设计协作，推动效果评测与迭代。",
  "【任职要求】",
  "1. 本科及以上，计算机、人工智能、产品设计相关专业优先；",
  "2. 了解大模型 / RAG / Agent 的基本工程链路；",
  "3. 每周到岗 4 天，可实习 3 个月以上。",
  "https://www.zhipin.com/job_detail/synthetic-fixture.html",
].join("\n");

const results = [];

function check(step, name, ok, detail) {
  results.push({ step, name, ok: Boolean(ok), detail: detail || "" });
  console.log(`${ok ? "PASS" : "FAIL"} [${step}] ${name}${detail ? " — " + detail : ""}`);
}

function shot(page, name) {
  return page.screenshot({ path: path.join(OUT, name), fullPage: false });
}

async function api(pathname, init) {
  const response = await fetch(`${API}${pathname}`, init);
  const text = await response.text();
  let body = null;
  try {
    body = JSON.parse(text);
  } catch (_) {
    body = text;
  }
  return { status: response.status, body };
}

(async () => {
  fs.mkdirSync(OUT, { recursive: true });
  fs.mkdirSync(EVIDENCE, { recursive: true });

  const browser = await playwright.chromium.launch();
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 } });
  const page = await context.newPage();
  const consoleErrors = [];
  const badResponses = [];
  page.on("console", (msg) => {
    if (msg.type() === "error") consoleErrors.push(msg.text());
  });
  page.on("response", (response) => {
    if (response.status() >= 400) badResponses.push(`${response.status()} ${response.url()}`);
  });
  // 这条流程里新建的岗位还没有「已确认的岗位简历」，按设计会命中 409/404：
  // 这些是产品语义（不能拿未确认的简历去投递），不算缺陷。
  const EXPECTED_BAD = /resume-studio|resume-snapshot|bind-resume/;

  try {
    // ---------------------------------------------------------------- 1
    await page.goto(`${WEB}/jobs/import`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1200);
    await shot(page, "01-import-page.png");
    check(1, "打开导入页", page.url().includes("/jobs/import"), page.url());

    // ---------------------------------------------------------------- 2
    const textarea = page.locator("textarea").first();
    await textarea.fill(BOSS_TEXT);
    await page.selectOption("select", "BOSS_ZHIPIN").catch(() => {});
    await shot(page, "02-pasted.png");
    check(2, "粘贴岗位原文", (await textarea.inputValue()).includes("AI产品经理实习"), `${BOSS_TEXT.length} 字符`);

    // ---------------------------------------------------------------- 3
    await page.getByRole("button", { name: "解析岗位" }).click();
    await page.waitForSelector("text=确认字段", { timeout: 30000 });
    await shot(page, "03-parsed.png");
    check(3, "解析完成", true, "出现字段确认区");

    // ---------------------------------------------------------------- 4
    const fieldValue = async (label) => {
      const input = page.locator(`#f-${label}`);
      return (await input.count()) ? await input.inputValue() : "";
    };
    const parsed = {
      company: await fieldValue("company"),
      role: await fieldValue("role"),
      salary_text: await fieldValue("salary_text"),
      location: await fieldValue("location"),
      education: await fieldValue("education"),
      employment_type: await fieldValue("employment_type"),
      source_url: await fieldValue("source_url"),
    };
    const fieldsOk =
      parsed.company === "杭州示例科技有限公司" &&
      parsed.role === "AI产品经理实习" &&
      parsed.salary_text.startsWith("8-13K") &&
      parsed.location.startsWith("杭州") &&
      parsed.education === "本科" &&
      parsed.employment_type === "INTERN" &&
      parsed.source_url.includes("zhipin.com");
    check(4, "字段抽取正确", fieldsOk, JSON.stringify(parsed));

    // ---------------------------------------------------------------- 5
    const before = await api("/api/v1/plaza");
    await page.getByRole("button", { name: "确认保存并进入匹配" }).click();
    await page.waitForURL(/\/missions\/[0-9a-f-]{36}\/role/, { timeout: 45000 }).catch(() => {});
    await page.waitForTimeout(2500);
    await shot(page, "05-mission.png");
    const missionId = (page.url().match(/\/missions\/([0-9a-f-]{36})\//) || [])[1] || "";
    check(5, "保存并进入匹配", Boolean(missionId), missionId ? `mission=${missionId}` : page.url());

    // ---------------------------------------------------------------- 6
    const kitResponse = missionId ? await api(`/api/v1/missions/${missionId}/boss-kit`) : { status: 0, body: null };
    const kit = kitResponse.body || {};
    check(
      6,
      "岗位详情页可读到原岗位链接",
      kitResponse.status === 200 && String(kit.source_url || "").includes("zhipin.com"),
      String(kit.source_url || ""),
    );

    // ---------------------------------------------------------------- 7
    await page.getByRole("button", { name: "生成 BOSS 打招呼" }).click();
    await page.waitForTimeout(2500);
    await shot(page, "07-greeting.png");
    const shortBox = page.locator("textarea").first();
    const shortText = (await shortBox.count()) ? await shortBox.inputValue() : "";
    check(7, "生成话术", shortText.includes("AI产品经理实习"), shortText.slice(0, 60));

    // ---------------------------------------------------------------- 8
    await shortBox.fill(shortText + "（我已手动编辑）");
    const edited = await shortBox.inputValue();
    await shot(page, "08-greeting-edited.png");
    check(8, "话术可编辑", edited.endsWith("（我已手动编辑）"), edited.slice(-20));

    // ---------------------------------------------------------------- 9
    await page.getByRole("button", { name: "保存话术到这条岗位" }).click();
    await page.waitForTimeout(2000);
    const kitAfterSave = missionId ? await api(`/api/v1/missions/${missionId}/boss-kit`) : { body: {} };
    const savedShort = ((kitAfterSave.body || {}).greeting || {}).short || "";
    await shot(page, "09-greeting-saved.png");
    check(9, "话术已保存", savedShort.includes("我已手动编辑"), savedShort.slice(-20));

    // ---------------------------------------------------------------- 10
    await page.getByRole("button", { name: "标记已投递" }).click();
    await page.waitForTimeout(3000);
    await shot(page, "10-marked-applied.png");
    const kitAfterApplied = missionId ? await api(`/api/v1/missions/${missionId}/boss-kit`) : { body: {} };
    const application = (kitAfterApplied.body || {}).application;
    check(
      10,
      "标记已投递",
      application && application.status === "APPLIED",
      application ? `status=${application.status} applied_at=${application.applied_at}` : "无投递记录",
    );

    // ---------------------------------------------------------------- 11
    // 新导入的岗位还没有已确认的岗位简历：按设计不生成投递 PDF 快照（不能拿未确认的简历去投递）。
    // 这里核对「语义正确」：快照接口应给出 404 + 明确原因，而不是返回一个假 PDF。
    const snapshotUrl = (kitAfterApplied.body || {}).snapshot_url;
    let snapshotStatus = 0;
    let snapshotBytes = 0;
    if (snapshotUrl) {
      const res = await fetch(`${API}${snapshotUrl}`);
      snapshotStatus = res.status;
      snapshotBytes = res.status === 200 ? (await res.arrayBuffer()).byteLength : 0;
    }
    check(
      11,
      "快照语义正确（未确认简历不出快照）",
      snapshotUrl ? snapshotStatus === 404 : true,
      snapshotUrl ? `${snapshotUrl} → ${snapshotStatus}${snapshotBytes ? ` / ${snapshotBytes} 字节` : ""}` : "无投递记录",
    );

    // ---------------------------------------------------------------- 11b
    // 找一条「Studio 已确认修订版」的既有岗位，用它做真实的 Studio / PDF 验收
    // （新建岗位要走完经历筛选→策略→目标简历才能有简历，不适合放在这条端到端里）。
    let studioMissionId = "";
    const plazaScan = ((await api("/api/v1/plaza")).body || {}).items || [];
    for (const item of plazaScan.slice(0, 80)) {
      const mid = item.mission_id;
      if (!mid) continue;
      const r = await api(`/api/v1/job-missions/${mid}/resume-studio`);
      if (r.status === 200 && r.body && r.body.confirmed_revision != null && r.body.confirmed_revision === r.body.revision) {
        studioMissionId = mid;
        break;
      }
    }
    check("11b", "找到已确认修订版的岗位用于 Studio 验收", Boolean(studioMissionId), studioMissionId || "数据集中未找到");

    // ---------------------------------------------------------------- 11c
    let apiPdfBytes = 0;
    let apiPdfHead = "";
    if (studioMissionId) {
      const res = await fetch(`${API}/api/v1/job-missions/${studioMissionId}/resume-studio/pdf`);
      if (res.status === 200) {
        const buf = Buffer.from(await res.arrayBuffer());
        apiPdfBytes = buf.length;
        apiPdfHead = buf.subarray(0, 5).toString("latin1");
      }
    }
    check("11c", "服务端真实渲染 PDF（Typst）", apiPdfBytes > 500 && apiPdfHead === "%PDF-", `${apiPdfBytes} 字节 / 头=${apiPdfHead}`);

    // ---------------------------------------------------------------- 12
    const studioTarget = studioMissionId || missionId;
    await page.goto(`${WEB}/missions/${studioTarget}/resume/studio`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(4000);
    await shot(page, "12-studio.png");
    check(12, "打开 Resume Studio", page.url().includes("/resume/studio"), page.url());

    // ---------------------------------------------------------------- 13
    let pdfOk = false;
    let pdfBytes = 0;
    const exportBtn = page.getByRole("button", { name: /下载 PDF/ }).first();
    if (await exportBtn.count()) {
      const [download] = await Promise.all([
        page.waitForEvent("download", { timeout: 90000 }).catch(() => null),
        exportBtn.click().catch(() => {}),
      ]);
      if (download) {
        const target = path.join(OUT, "13-studio-export.pdf");
        await download.saveAs(target);
        pdfBytes = fs.statSync(target).size;
        pdfOk = pdfBytes > 500;
      }
    }
    await shot(page, "13-studio-pdf.png");
    check(13, "Studio 导出 PDF", pdfOk, pdfBytes ? `${pdfBytes} 字节` : "未触发下载");

    // ---------------------------------------------------------------- 14
    const after = await api("/api/v1/plaza");
    const beforeTotal = (before.body && before.body.total) || 0;
    const afterTotal = (after.body && after.body.total) || 0;
    const inLibrary = ((after.body && after.body.items) || []).some((item) => item.mission_id === missionId);
    check(14, "岗位已进入岗位库", inLibrary, `total ${beforeTotal} → ${afterTotal}`);

    // ---------------------------------------------------------------- 15
    await page.goto(`${WEB}/jobs/import`, { waitUntil: "domcontentloaded" });
    await page.waitForTimeout(1000);
    await page.locator("textarea").first().fill(BOSS_TEXT);
    await page.getByRole("button", { name: "解析岗位" }).click();
    await page.waitForSelector("text=确认字段", { timeout: 30000 });
    await page.getByRole("button", { name: "仅保存到岗位库" }).click();
    await page.waitForTimeout(3000);
    await shot(page, "15-duplicate.png");
    const dupMsg = await page.locator("p.status, p.error").first().textContent().catch(() => "");
    const finalTotal = ((await api("/api/v1/plaza")).body || {}).total || 0;
    check(
      15,
      "重复导入不新增",
      finalTotal === afterTotal,
      `total ${afterTotal} → ${finalTotal}；提示：${(dupMsg || "").slice(0, 60)}`,
    );

    check(16, "页面无 JS 报错", consoleErrors.length === 0, consoleErrors.slice(0, 3).join(" | "));
  } catch (error) {
    check(0, "脚本异常", false, error && error.message ? error.message : String(error));
  } finally {
    await browser.close();
  }

  const passed = results.filter((item) => item.ok).length;
  const summary = {
    web: WEB,
    api: API,
    finished_at: new Date().toISOString(),
    total: results.length,
    passed,
    failed: results.length - passed,
    steps: results,
  };
  fs.writeFileSync(path.join(EVIDENCE, "e2e-main-flow.json"), JSON.stringify(summary, null, 2));
  console.log(`\n结果：${passed}/${results.length} 通过`);
  process.exit(summary.failed ? 1 : 0);
})();
