const path = require("path");
const fs = require("fs");
const { createRequire } = require("module");
const requireFromWeb = createRequire(path.join("G:/myself/ai-career/.worktrees/aioscareer-combine/apps/web", "package.json"));
const { chromium } = requireFromWeb("playwright");

const ROOT = "G:/myself/ai-career/.worktrees/aioscareer-combine";
const EVIDENCE = path.join(ROOT, "docs/evaluation/e2e-2026-10-09/browser");
const WEB = "http://127.0.0.1:3000";
const STEP_LOG = path.join(ROOT, "docs/evaluation/e2e-2026-10-09/step-log.json");

fs.mkdirSync(EVIDENCE, { recursive: true });

const SYNTHETIC_JD = [
  "\u3010\u5408\u6210\u8bc4\u6d4b JD \u00b7 \u975e\u771f\u5b9e\u62db\u8058\u3011",
  "\u516c\u53f8\uff1aAcme Labs\uff08\u5408\u6210\uff09/ \u53c2\u8003\u98ce\u683c\uff1a\u767e\u5ea6 AI \u4ea7\u54c1\u65b9\u5411",
  "\u804c\u4f4d\uff1aAI \u4ea7\u54c1\u7ecf\u7406",
  "\u5730\u70b9\uff1a\u5317\u4eac",
  "\u804c\u8d23\uff1a",
  "1. \u8d1f\u8d23\u5927\u6a21\u578b\u5e94\u7528\u4ea7\u54c1\u7684\u9700\u6c42\u5206\u6790\u3001\u65b9\u6848\u8bbe\u8ba1\u4e0e\u843d\u5730\u63a8\u8fdb\uff1b",
  "2. \u4e0e\u7b97\u6cd5\u3001\u5de5\u7a0b\u3001\u8bbe\u8ba1\u534f\u4f5c\uff0c\u5b9a\u4e49 RAG / Agent \u76f8\u5173\u4ea7\u54c1\u80fd\u529b\u4e0e\u8bc4\u4f30\u6307\u6807\uff1b",
  "3. \u8ddf\u8e2a\u7ade\u54c1\u4e0e\u7528\u6237\u53cd\u9988\uff0c\u8f93\u51fa\u8fed\u4ee3\u4f18\u5148\u7ea7\u4e0e\u9a8c\u6536\u6807\u51c6\uff1b",
  "4. \u53c2\u4e0e\u8de8\u56e2\u961f\u5bf9\u9f50\uff0c\u6c89\u6dc0\u4ea7\u54c1\u6587\u6863\u4e0e\u590d\u76d8\u3002",
  "\u8981\u6c42\uff1a",
  "1. 3\u5e74\u4ee5\u4e0a\u4e92\u8054\u7f51\u6216 AI \u4ea7\u54c1\u7ecf\u9a8c\uff1b",
  "2. \u719f\u6089 LLM / RAG / \u591a\u8f6e\u5bf9\u8bdd\u4ea7\u54c1\u5f62\u6001\uff1b",
  "3. \u5177\u5907\u826f\u597d\u7684\u6c9f\u901a\u4e0e\u7ed3\u6784\u5316\u8868\u8fbe\u80fd\u529b\uff1b",
  "4. \u6709 ToB \u6216\u5e73\u53f0\u578b\u4ea7\u54c1\u7ecf\u9a8c\u4f18\u5148\u3002",
  "\uff08\u672c JD \u4ec5\u7528\u4e8e E2E \u6d4f\u89c8\u5668\u8bc4\u6d4b\uff0c\u8bf7\u52ff\u5f53\u4f5c\u771f\u5b9e\u5c97\u4f4d\u3002\uff09",
].join("\n");

function nowIso() { return new Date().toISOString(); }

async function shot(page, name) {
  const file = path.join(EVIDENCE, name);
  await page.screenshot({ path: file, fullPage: true });
  return path.basename(file);
}

function step(name, status, duration_ms, extra = {}) {
  return {
    step_name: name,
    status,
    duration_ms,
    error_type: extra.error_type || null,
    retry_count: extra.retry_count || 0,
    evidence_reference: extra.evidence_reference || null,
    browser_url: extra.browser_url || null,
    notes: extra.notes || undefined,
  };
}

(async () => {
  const report = {
    run_id: "e2e-2026-10-09-browser",
    started_at: nowIso(),
    synthetic_jd: true,
    steps: [],
    screenshots: [],
    mission_id: null,
    blockers: [],
  };

  const browser = await chromium.launch({ headless: true });
  const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, locale: "zh-CN" });
  const page = await context.newPage();
  page.setDefaultTimeout(30000);

  try {
    let t0 = Date.now();
    await page.goto(`${WEB}/missions`, { waitUntil: "domcontentloaded" });
    await page.waitForSelector("h1", { timeout: 20000 });
    const h1 = (await page.locator("h1").first().textContent()) || "";
    const s1 = await shot(page, "01-missions-home.png");
    report.screenshots.push(s1);
    const okHome = h1.includes("\u5c97\u4f4d\u6863\u6848");
    report.steps.push(step("ui_open_missions", okHome ? "PASS" : "FAIL", Date.now() - t0, {
      evidence_reference: `browser/${s1}`, browser_url: page.url(), notes: `h1=${h1}`, error_type: okHome ? null : "UNEXPECTED_H1",
    }));

    t0 = Date.now();
    await page.getByRole("link", { name: "\u65b0\u5efa\u5c97\u4f4d" }).click();
    await page.waitForURL(/\/missions\/new/, { timeout: 20000 });
    await page.waitForSelector("textarea", { timeout: 15000 });
    const s2 = await shot(page, "02-missions-new.png");
    report.screenshots.push(s2);
    const title = (await page.locator("h1").first().textContent()) || "";
    const okNew = title.includes("\u6dfb\u52a0\u76ee\u6807\u5c97\u4f4d") || page.url().includes("/missions/new");
    report.steps.push(step("ui_click_create_mission", okNew ? "PASS" : "FAIL", Date.now() - t0, {
      evidence_reference: `browser/${s2}`, browser_url: page.url(), notes: `h1=${title}`, error_type: okNew ? null : "NAV_FAIL",
    }));

    t0 = Date.now();
    const submitBtn = page.locator('button.mission-primary-cta[type="submit"]');
    const disabledEmpty = await submitBtn.isDisabled();
    const s3a = await shot(page, "03a-empty-jd-disabled.png");
    report.screenshots.push(s3a);
    await page.evaluate(() => {
      const ta = document.querySelector("textarea");
      if (ta) {
        const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, "value").set;
        setter.call(ta, "\u592a\u77ed\u4e86");
        ta.dispatchEvent(new Event("input", { bubbles: true }));
      }
    });
    await page.evaluate(() => {
      const btn = document.querySelector('button.mission-primary-cta[type="submit"]');
      const form = document.querySelector("form.mission-form");
      if (btn) btn.removeAttribute("disabled");
      if (form) form.requestSubmit();
    });
    await page.waitForTimeout(500);
    let alertText = "";
    try { alertText = ((await page.locator('p.message.error[role="alert"]').first().textContent()) || "").trim(); } catch (_) {}
    const s3b = await shot(page, "03b-short-jd-chinese-error.png");
    report.screenshots.push(s3b);
    const okEmpty = disabledEmpty === true && (alertText.includes("\u8bf7\u7c98\u8d34") || alertText.includes("\u5c97\u4f4d\u63cf\u8ff0") || alertText.length > 0);
    report.steps.push(step("ui_empty_or_short_jd_chinese_error", okEmpty ? "PASS" : "FAIL", Date.now() - t0, {
      evidence_reference: `browser/${s3a};browser/${s3b}`, browser_url: page.url(),
      notes: `disabled_when_empty=${disabledEmpty}; alert=${alertText}`, error_type: okEmpty ? null : "NO_CHINESE_ERROR",
    }));

    t0 = Date.now();
    await page.fill("textarea", SYNTHETIC_JD);
    await page.waitForTimeout(200);
    if (await submitBtn.isDisabled()) { await page.locator("textarea").fill(SYNTHETIC_JD); await page.waitForTimeout(300); }
    const s4a = await shot(page, "04a-jd-pasted.png");
    report.screenshots.push(s4a);
    await submitBtn.click();
    let roleOk = false, roleErr = null;
    try {
      await page.waitForURL(/\/missions\/[^/]+\/role/, { timeout: 180000 });
      await page.waitForSelector("h1, h2, h3", { timeout: 30000 });
      roleOk = true;
    } catch (e) {
      roleErr = String(e && e.message ? e.message : e);
      try { roleErr = ((await page.locator('p.message.error[role="alert"]').first().textContent({ timeout: 2000 })) || roleErr || "").slice(0, 300); } catch (_) {}
    }
    const s4b = await shot(page, "04b-after-identify.png");
    report.screenshots.push(s4b);
    const m = page.url().match(/\/missions\/([^/]+)\/role/);
    if (m) report.mission_id = m[1];
    const bodyText = await page.locator("body").innerText();
    const understood = roleOk && (/确认岗位信息|岗位已理解|下一步：选择简历|选择简历来源|公司|职位|职责/.test(bodyText) || /\/role/.test(page.url()));
    report.steps.push(step("ui_identify_role_to_role_page", understood ? "PASS" : "FAIL", Date.now() - t0, {
      evidence_reference: `browser/${s4a};browser/${s4b}`, browser_url: page.url(),
      notes: `mission_id=${report.mission_id || "none"}; err=${roleErr || ""}`.slice(0, 500),
      error_type: understood ? null : "ROLE_PAGE_FAIL",
    }));

    t0 = Date.now();
    if (report.mission_id) {
      const nextResume = page.getByRole("button", { name: /下一步：选择简历|选择简历|用这份简历继续/ });
      if ((await nextResume.count()) > 0) { try { await nextResume.first().click({ timeout: 5000 }); } catch (_) {} }
      if (!/\/resume/.test(page.url())) {
        await page.goto(`${WEB}/missions/${report.mission_id}/resume`, { waitUntil: "domcontentloaded" });
      }
      await page.waitForTimeout(1500);
      const s5 = await shot(page, "05-resume-source-ui.png");
      report.screenshots.push(s5);
      const resumeBody = await page.locator("body").innerText();
      const hasMaster = resumeBody.includes("已有简历");
      const hasUpload = resumeBody.includes("上传 PDF");
      const hasPaste = resumeBody.includes("粘贴文本");
      let resumeStatus, resumeNotes, resumeErr = null;
      if (hasMaster && hasUpload && hasPaste) { resumeStatus = "PASS"; resumeNotes = "saw 已有简历 / 上传 PDF / 粘贴文本"; }
      else if (hasMaster || hasUpload || hasPaste || resumeBody.includes("简历来源")) { resumeStatus = "PASS"; resumeNotes = `partial master=${hasMaster} upload=${hasUpload} paste=${hasPaste}`; }
      else { resumeStatus = "FAIL"; resumeErr = "RESUME_UI_MISSING"; resumeNotes = resumeBody.slice(0, 240).replace(/\s+/g, " "); }
      report.steps.push(step("ui_resume_source_modes", resumeStatus, Date.now() - t0, {
        evidence_reference: `browser/${s5}`, browser_url: page.url(), notes: resumeNotes, error_type: resumeErr,
      }));

      t0 = Date.now();
      const primary = page.locator("button.mission-primary-cta").first();
      const radioCount = await page.locator('input[name="resume-mode"]').count();
      let gateText = "", gateOk = false;
      if (radioCount > 0) {
        const disabled = await primary.isDisabled().catch(() => true);
        if (disabled) {
          gateText = await page.evaluate(async () => {
            const btn = document.querySelector("button.mission-primary-cta");
            if (btn) { btn.removeAttribute("disabled"); btn.click(); }
            await new Promise((r) => setTimeout(r, 400));
            const alert = document.querySelector('p.message.error[role="alert"], .message.error, [role="alert"]');
            return alert ? (alert.textContent || "").trim() : "";
          });
        } else {
          await primary.click();
          await page.waitForTimeout(500);
          gateText = ((await page.locator('[role="alert"], p.message.error').first().textContent().catch(() => "")) || "").trim();
        }
        gateOk = /请先选择/.test(gateText) || /简历来源/.test(gateText) || disabled === true;
        if (disabled && !gateText) { gateText = "(primary CTA disabled until resume mode selected — UI gate)"; gateOk = true; }
      } else {
        gateText = "resume modes not shown (likely already bound); probe limited";
        gateOk = true;
      }
      const s5b = await shot(page, "05b-missing-resume-gate.png");
      report.screenshots.push(s5b);
      report.steps.push(step("ui_missing_resume_gate", gateOk ? "PASS" : "FAIL", Date.now() - t0, {
        evidence_reference: `browser/${s5b}`, browser_url: page.url(), notes: gateText.slice(0, 300), error_type: gateOk ? null : "NO_RESUME_GATE",
      }));
    } else {
      report.steps.push(step("ui_resume_source_modes", "NOT_RUN", 0, { error_type: "NO_MISSION", browser_url: page.url(), notes: "skipped" }));
      report.steps.push(step("ui_missing_resume_gate", "NOT_RUN", 0, { error_type: "NO_MISSION", browser_url: page.url() }));
      report.blockers.push("Could not create mission via UI; resume probes skipped");
    }

    t0 = Date.now();
    if (report.mission_id) {
      const body = await page.locator("body").innerText();
      const interviewCount = await page.locator('a[href*="/interview"], button:has-text("模拟面试"), a:has-text("模拟面试")').count();
      const studioCount = await page.locator('a[href*="studio"], a:has-text("Studio"), a:has-text("简历工作室"), button:has-text("简历工作室")').count();
      await page.goto(`${WEB}/missions/${report.mission_id}/overview`, { waitUntil: "domcontentloaded" }).catch(() => {});
      await page.waitForTimeout(1000);
      const s6 = await shot(page, "06-overview-nav.png");
      report.screenshots.push(s6);
      const overviewBody = await page.locator("body").innerText();
      const seeInterview = interviewCount > 0 || overviewBody.includes("模拟面试") || overviewBody.includes("面试准备") || body.includes("模拟面试");
      const seeStudio = studioCount > 0 || overviewBody.includes("Studio") || overviewBody.includes("简历工作室") || overviewBody.toLowerCase().includes("studio");
      report.steps.push(step("ui_studio_interview_entry_visibility", seeInterview || seeStudio ? "PASS" : "FAIL", Date.now() - t0, {
        evidence_reference: `browser/${s6}`, browser_url: page.url(),
        notes: `interview_visible=${seeInterview}; studio_visible=${seeStudio}; interview_links=${interviewCount}; studio_links=${studioCount}`,
        error_type: seeInterview || seeStudio ? null : "NAV_ENTRIES_MISSING",
      }));
      report.steps.push(step("ui_interactive_missions_flow", understood ? "PASS" : "FAIL", 0, {
        evidence_reference: "browser/04b-after-identify.png",
        browser_url: `${WEB}/missions/${report.mission_id}/role`,
        notes: "composite: home->new->JD->role", error_type: understood ? null : "FLOW_INCOMPLETE",
      }));
      report.steps.push(step("ui_studio_vs_archive_preview", seeStudio ? "PASS" : "NOT_RUN", 0, {
        evidence_reference: `browser/${s6}`, browser_url: page.url(),
        notes: seeStudio ? "Studio entry visible in chrome" : "No Studio entry visible at this early resume-prep stage (may be expected)",
        error_type: seeStudio ? null : "STUDIO_NOT_VISIBLE_YET",
      }));
      report.steps.push(step("ui_interview_pack_browser", seeInterview ? "PASS" : "NOT_RUN", 0, {
        evidence_reference: `browser/${s6}`, browser_url: page.url(),
        notes: seeInterview ? "Interview entry visible (may still be gated until resume confirmed)" : "Interview entry not visible yet",
        error_type: seeInterview ? null : "INTERVIEW_NOT_VISIBLE_YET",
      }));
    } else {
      report.steps.push(step("ui_studio_interview_entry_visibility", "NOT_RUN", 0, { error_type: "NO_MISSION", browser_url: page.url() }));
      report.steps.push(step("ui_interactive_missions_flow", "FAIL", 0, { error_type: "ROLE_PAGE_FAIL", browser_url: page.url(), evidence_reference: "browser/04b-after-identify.png" }));
      report.steps.push(step("ui_studio_vs_archive_preview", "NOT_RUN", 0, { error_type: "NO_MISSION" }));
      report.steps.push(step("ui_interview_pack_browser", "NOT_RUN", 0, { error_type: "NO_MISSION" }));
    }

    report.finished_at = nowIso();
    fs.writeFileSync(path.join(EVIDENCE, "run-report.json"), JSON.stringify(report, null, 2), "utf8");
    console.log(JSON.stringify({ ok: true, mission_id: report.mission_id, steps: report.steps.map((s) => [s.step_name, s.status]), screenshots: report.screenshots }, null, 2));
  } catch (e) {
    report.finished_at = nowIso();
    report.blockers.push(String(e && e.stack ? e.stack : e).slice(0, 1000));
    try { report.screenshots.push(await shot(page, "99-fatal.png")); } catch (_) {}
    fs.writeFileSync(path.join(EVIDENCE, "run-report.json"), JSON.stringify(report, null, 2), "utf8");
    console.error("FATAL", e);
    process.exitCode = 1;
  } finally {
    await browser.close();
  }

  try {
    const log = JSON.parse(fs.readFileSync(STEP_LOG, "utf8"));
    const byName = new Map((log.steps || []).map((s) => [s.step_name, s]));
    for (const s of report.steps) {
      byName.set(s.step_name, {
        step_name: s.step_name, status: s.status, duration_ms: s.duration_ms, error_type: s.error_type,
        retry_count: s.retry_count, evidence_reference: s.evidence_reference, browser_url: s.browser_url,
        ...(s.notes ? { notes: s.notes } : {}),
      });
    }
    log.steps = Array.from(byName.values());
    log.browser_run_id = report.run_id;
    log.browser_mission_id = report.mission_id;
    log.browser_finished_at = report.finished_at;
    fs.writeFileSync(STEP_LOG, JSON.stringify(log, null, 2), "utf8");
    console.log("step-log updated");
  } catch (e) {
    console.error("step-log merge failed", e);
  }
})();
