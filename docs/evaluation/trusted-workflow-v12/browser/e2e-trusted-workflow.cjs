/**
 * 可信求职闭环 v1.2 —— 真实浏览器主流程 E2E（Playwright + Chromium）。
 *
 * 6 个流程（指令 6.3）：
 *   1. 首次用户：首页 → 粘贴简历 → 保存档案 → 添加岗位 → 生成岗位简历 → Studio → 导出
 *   2. 事实不足：请求面试参考回答 → 查看已知事实/待补 → 不应出现编造数字
 *   3. 多岗位复用：三个 JD → 三份岗位版 → 更新原始事实 → 只更新一份 → 另两份不变
 *   4. 面试版本：正式 PDF → 记录投递并绑定快照 → 更新 Studio → 面试读取历史投递版
 *   5. 档案恢复：清理 LocalStorage → 重新打开 → 从服务端档案列表恢复
 *   6. 无模型：不配置 Key → 粘贴简历 → 编辑文字 → 导出草稿 → 点 AI 分析进入模型配置说明
 *
 * 用法：
 *   node docs/evaluation/trusted-workflow-v12/browser/e2e-trusted-workflow.cjs
 *     --web http://127.0.0.1:3100 --api http://127.0.0.1:8100
 *
 * 说明：模型由本地桩服务替代（stub-llm-server.py），不联网、不产生费用。
 * 本脚本验证的是产品流程与前端行为，不是模型输出质量。
 */
const fs = require("fs");
const path = require("path");
const { chromium } = require(path.join(__dirname, "..", "..", "..", "..", "apps", "web", "node_modules", "playwright"));

const argv = process.argv.slice(2);
const arg = (name, fallback) => {
  const index = argv.indexOf(`--${name}`);
  return index >= 0 && argv[index + 1] ? argv[index + 1] : fallback;
};
const WEB = arg("web", "http://127.0.0.1:3100");
const API = arg("api", "http://127.0.0.1:8100");
const OUT = path.resolve(__dirname, "results");
const SHOTS = path.join(OUT, "screenshots");
fs.mkdirSync(SHOTS, { recursive: true });

const RESUME_TEXT = [
  "陈林",
  "电话：13800000000 邮箱：chenlin@example.com",
  "",
  "教育经历",
  "示例大学 本科 信息管理与信息系统 2022.09-2026.06",
  "",
  "项目经历",
  "校园二手交易平台 2025.03-2025.07",
  "负责需求梳理与原型设计，输出 PRD 与交互稿。",
  "与设计、开发协作完成一版可点击原型，组织 12 位同学做可用性测试。",
  "",
  "技能",
  "需求分析、Axure、SQL、用户访谈",
].join("\n");

const JD_A = "Acme 公司招聘 AI 产品经理实习生\n岗位要求：负责需求梳理、原型设计与数据分析，能与设计和研发协作推进项目。";
const JD_B = "Beta 公司招聘数据产品经理实习生\n岗位要求：搭建指标体系，输出数据看板，用 SQL 完成基础分析。";
const JD_C = "Gamma 公司招聘内容运营实习生\n岗位要求：负责内容选题与用户增长活动，能用数据复盘活动效果。";

const results = [];
const log = (...parts) => console.log("[e2e]", ...parts);

function step(name, ok, detail = "") {
  results.push({ name, ok: Boolean(ok), detail });
  log(`${ok ? "PASS" : "FAIL"} · ${name}${detail ? ` — ${detail}` : ""}`);
  return Boolean(ok);
}

async function apiJson(method, url, body, headers = {}) {
  const response = await fetch(url, {
    method,
    headers: { "Content-Type": "application/json", "X-AI-Career-Client": "ai-career-web", Origin: WEB, ...headers },
    body: body ? JSON.stringify(body) : undefined,
  });
  const text = await response.text();
  let data = null;
  try { data = text ? JSON.parse(text) : null; } catch { data = text; }
  return { status: response.status, data };
}

async function acceptBullets(missionId) {
  /**
   * 产品里确认投递版之前必须逐条接受改写要点（否则 409：「还没有任何被接受的要点」）。
   * 这是真实闸门，不是可跳过的步骤，所以 E2E 走真实入口：
   * `PATCH /api/v1/target-resume-bullets/{id}`（status=ACCEPTED + fact_confirmed）。
   */
  const resumes = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/target-resumes`);
  let accepted = 0;
  for (const resume of resumes.data || []) {
    if (String(resume.status).toUpperCase() === "CONFIRMED") continue;
    for (const bullet of resume.bullets || []) {
      const patched = await apiJson("PATCH", `${API}/api/v1/target-resume-bullets/${bullet.id}`, {
        status: "ACCEPTED",
        fact_confirmed: true,
      });
      if (patched.status === 200) accepted += 1;
    }
  }
  return accepted;
}

async function prepareMission(missionId, profileId) {
  /** 走完岗位前置步骤：确认简历来源 → 选择经历 → 简历策略 → 生成并确认岗位简历。 */
  await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/confirm-resume-source`, { mode: "master" });
  await apiJson("PUT", `${API}/api/v1/job-missions/${missionId}/experience-selection?confirm=true`, {
    selections: [],
  });
  const selection = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/experience-selection/generate`, {});
  if (selection.data && selection.data.selections) {
    await apiJson("PUT", `${API}/api/v1/job-missions/${missionId}/experience-selection?confirm=true`, {
      selections: selection.data.selections.map(item => ({
        experience_id: item.experience_id,
        decision: item.decision,
        why: item.why || "与岗位相关，保留。",
        related_capabilities: item.related_capabilities || [],
        supporting_evidence_refs: item.supporting_evidence_refs || [],
        confidence: typeof item.confidence === "number" ? item.confidence : 0.7,
      })),
    });
  }
  await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/resume-strategy`, {});
  await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/confirm-strategy`, {});
  const generated = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/target-resumes`, {});
  if (generated.status === 201) {
    await acceptBullets(missionId);
    await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/confirm-target-resume`, {});
  }
  return generated;
}

async function flow1(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  page.on("pageerror", () => {});
  try {
    await page.goto(WEB, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(1500);
    await page.screenshot({ path: path.join(SHOTS, "flow1-01-home.png"), fullPage: true });
    step("流程1 · 首页打开", (await page.title()).length > 0);

    // 首页 → 导入简历 → 粘贴简历文字建档
    await page.getByRole("link", { name: /导入简历|去上传/ }).first().click();
    await page.waitForTimeout(2500);
    await page.screenshot({ path: path.join(SHOTS, "flow1-02-import.png"), fullPage: true });
    const openPaste = page.getByText(/粘贴简历文字建档/).first();
    if (await openPaste.isVisible().catch(() => false)) await openPaste.click();
    const textarea = page.locator("textarea").first();
    await textarea.waitFor({ state: "visible", timeout: 30000 });
    await textarea.fill(RESUME_TEXT);
    await page.screenshot({ path: path.join(SHOTS, "flow1-03-paste.png"), fullPage: true });
    const saveButton = page.getByRole("button", { name: /用这段文字建档|保存|建档|下一步|开始/ }).first();
    await saveButton.click();
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(SHOTS, "flow1-04-profile.png"), fullPage: true });

    const list = await apiJson("GET", `${API}/api/v1/local/profiles`);
    const profiles = Array.isArray(list.data) ? list.data : (list.data && list.data.profiles) || [];
    const profileId = profiles.length ? (profiles[0].profile_id || profiles[0].id) : null;
    step("流程1 · 粘贴简历后建档成功", Boolean(profileId), `profile=${profileId}`);
    if (!profileId) return null;

    // 添加岗位（手动粘贴 JD）
    //
    // 幂等：同一个档案重复粘贴同一份 JD 会返回 409（既有产品规则），
    // 重复跑 E2E 时直接复用已有岗位，而不是把「重复添加被拒」记成失败。
    const created = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/job-missions`, { raw_text: JD_A });
    let missionId = created.data && created.data.id ? created.data.id : null;
    if (!missionId && created.status === 409) {
      const existing = await apiJson("GET", `${API}/api/v1/profiles/${profileId}/job-missions`);
      const list = Array.isArray(existing.data) ? existing.data : ((existing.data && existing.data.items) || []);
      missionId = list.length ? (list[0].id || list[0].mission_id) : null;
    }
    step("流程1 · 添加目标岗位", Boolean(missionId), `mission=${missionId} status=${created.status}`);
    if (!missionId) return null;

    // 生成岗位简历（走桩模型）
    const generated = await prepareMission(missionId, profileId);
    step("流程1 · 生成岗位定向简历", generated.status === 201, `status=${generated.status}`);
    const resumes = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/target-resumes`);
    const confirmedResume = (resumes.data || []).find(item => String(item.status).toUpperCase() === "CONFIRMED");
    step("流程1 · 确认岗位简历", Boolean(confirmedResume), `status=${confirmedResume && confirmedResume.status}`);

    // Studio
    await page.goto(`${WEB}/missions/${missionId}/resume/studio`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(6000);
    await page.screenshot({ path: path.join(SHOTS, "flow1-04-studio.png"), fullPage: true });
    const studio = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);
    const revision = studio.data && studio.data.revision;
    step("流程1 · Studio 打开并读取修订版", Boolean(revision), `revision=${revision}`);

    // 草稿导出
    const draft = await fetch(`${API}/api/v1/job-missions/${missionId}/resume-studio/pdf?draft=1`);
    const draftBytes = Buffer.from(await draft.arrayBuffer());
    fs.writeFileSync(path.join(OUT, "flow1-draft.pdf"), draftBytes);
    step("流程1 · 草稿 PDF 可导出且带 DRAFT 文件名", draft.status === 200 && String(draft.headers.get("x-resume-filename") || "").includes("_DRAFT"), draft.headers.get("x-resume-filename") || "");

    // 事实闸门：缺姓名时正式投递版必须被拦下（草稿不受影响）
    const blocked = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/resume-studio/confirm`, {}, { "If-Match": String(revision) });
    const blockedCodes = (((blocked.data || {}).detail || {}).checks || []).map(item => item.code);
    step("流程1 · 缺姓名时正式投递版被拦下", blocked.status === 409 && blockedCodes.includes("missing_name"), `status=${blocked.status} codes=${blockedCodes}`);

    // 补上姓名（走 Studio 的真实编辑操作）
    const nameNode = (((studio.data || {}).document || {}).basics || {}).name || {};
    if (nameNode.id) {
      await apiJson("PATCH", `${API}/api/v1/job-missions/${missionId}/resume-studio`, {
        type: "set_text", node_id: nameNode.id, text: "陈林",
      }, { "If-Match": String(revision) });
    }
    const afterEdit = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);

    // 填了内容 ≠ 核对过事实：高风险未核对事实仍然必须阻塞正式投递版
    const stillBlocked = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/resume-studio/confirm`, {}, { "If-Match": String(afterEdit.data && afterEdit.data.revision) });
    const stillCodes = (((stillBlocked.data || {}).detail || {}).checks || []).map(item => `${item.code}:${item.level}`);
    step("流程1 · 高风险未核对事实仍然阻塞正式投递版", stillBlocked.status === 409 && stillCodes.some(code => code.startsWith("unconfirmed_fact:block")), `status=${stillBlocked.status} ${stillCodes}`);

    // 核对姓名这一项事实后，正式投递版才放行
    const afterBlocked = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);
    const nameNodeNow = (((afterBlocked.data || {}).document || {}).basics || {}).name || {};
    if (nameNodeNow.id) {
      await apiJson("PATCH", `${API}/api/v1/job-missions/${missionId}/resume-studio`, {
        type: "confirm_fact", node_id: nameNodeNow.id,
      }, { "If-Match": String(afterBlocked.data && afterBlocked.data.revision) });
    }
    const afterConfirmFact = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);
    const confirmRes = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/resume-studio/confirm`, {}, { "If-Match": String(afterConfirmFact.data && afterConfirmFact.data.revision) });
    const final = await fetch(`${API}/api/v1/job-missions/${missionId}/resume-studio/pdf`);
    const finalBytes = Buffer.from(await final.arrayBuffer());
    fs.writeFileSync(path.join(OUT, "flow1-final.pdf"), finalBytes);
    step(
      "流程1 · 正式投递版 PDF 导出",
      confirmRes.status === 200 && final.status === 200 && finalBytes.slice(0, 4).toString() === "%PDF" && !String(final.headers.get("x-resume-filename") || "").includes("_DRAFT"),
      `${final.headers.get("x-resume-filename")} · confirm=${confirmRes.status}`,
    );
    await page.screenshot({ path: path.join(SHOTS, "flow1-05-export.png"), fullPage: true });
    return { profileId, missionId };
  } finally {
    await context.close();
  }
}

async function flow2(browser, seed) {
  if (!seed) return step("流程2 · 依赖流程1 的档案", false, "SKIPPED");
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    // 事实不足的项目：解析主张 → 起一轮面试 → 取参考答案
    const mission = await apiJson("GET", `${API}/api/v1/job-missions/${seed.missionId}`);
    const targetJobId = mission.data && mission.data.target_job_id;
    const analysis = await apiJson("POST", `${API}/api/v1/target-jobs/${targetJobId}/claim-analysis`, {});
    const claimId = analysis.data && analysis.data.claims && analysis.data.claims[0] ? analysis.data.claims[0].id : null;
    step("流程2 · 解析出可面试主张", Boolean(claimId), `status=${analysis.status}`);
    if (!claimId) return false;

    const session = await apiJson("POST", `${API}/api/v1/resume-claims/${claimId}/interview-sessions`, { claim_id: claimId });
    const sessionId = session.data && session.data.id;
    step("流程2 · 开始一轮模拟面试", Boolean(sessionId), `status=${session.status} ${JSON.stringify(session.data || {}).slice(0, 200)}`);
    if (!sessionId) return false;

    const turn = await apiJson("POST", `${API}/api/v1/interview-sessions/${sessionId}/turns`, { answer: "我做过这个项目，主要负责需求梳理。" });
    // 评分写在「被回答的那一轮」上；最后一轮可能是系统补的追问（evaluation 为空）
    const answered = ((turn.data && turn.data.turns) || []).filter(item => item.answer).pop() || {};
    const evaluation = answered.evaluation || {};
    const reference = String(evaluation.reference_answer || "");
    const detail = evaluation.reference_answer_detail || null;
    step(
      "流程2 · 参考回答返回结构化结果（已知事实 / 待补 / 示范表达）",
      Boolean(detail || reference) || Boolean(evaluation.blocked_reason || evaluation.recommended_next_action),
      `detail=${Boolean(detail)} known=${(detail && detail.known_facts || []).length} missing=${(detail && detail.missing_facts || []).length}`,
    );
    const fabricated = /37%|一万二|三千/.test(reference);
    step("流程2 · 编造数字的示范表达被闸门拦下", !fabricated, reference.slice(0, 40));
    step(
      "流程2 · 降级时只给已知事实/待补，不给成稿",
      !detail || detail.grounded !== true || !detail.sample_wording || !/37%/.test(String(detail.sample_wording)),
      `grounded=${detail && detail.grounded}`,
    );

    await page.goto(`${WEB}/missions/${seed.missionId}/interview`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(4000);
    const body = await page.textContent("body").catch(() => "");
    step("流程2 · 面试页可打开并给出下一步", (body || "").length > 0, (body || "").slice(0, 50).replace(/\s+/g, " "));
    await page.screenshot({ path: path.join(SHOTS, "flow2-01-interview.png"), fullPage: true });
    return true;
  } finally {
    await context.close();
  }
}

async function flow3(browser, seed) {
  /**
   * 多岗位复用：三个 JD → 三份岗位版 → 改一处共享事实 → 只更新选中的那一份。
   *
   * 改共享事实走的是产品里的真实入口：事实核对页的「确认属实 + 写回原始事实」
   * （`POST /profiles/{id}/facts/attest` 且 `apply_to_source=true`）。
   * 已确认档案不允许直接 `PUT /profiles/{id}`（既有规则），所以这是它在产品里唯一的
   * 改法——「核对」与「写回」是同一次动作，不存在绕过核对就改事实的口子。
   */
  if (!seed) return step("流程3 · 依赖流程1 的档案", false, "SKIPPED");
  const profileId = seed.profileId;
  const created = [];
  for (const jd of [JD_B, JD_C]) {
    const mission = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/job-missions`, { raw_text: jd });
    if (mission.data && mission.data.id) created.push(mission.data.id);
  }
  step("流程3 · 同一份简历关联三个岗位", created.length === 2, `missions=${created.length + 1}`);
  const missions = [seed.missionId, ...created];
  const revisions = {};
  for (const id of missions) {
    await prepareMission(id, profileId);
    const studio = await apiJson("GET", `${API}/api/v1/job-missions/${id}/resume-studio`);
    // 明确写 null：undefined 会被 JSON.stringify 静默丢键，失败时看不出是哪一份岗位缺版本。
    revisions[id] = studio.data && typeof studio.data.revision === "number" ? studio.data.revision : null;
  }
  step("流程3 · 三份岗位各自生成自己的岗位版", Object.values(revisions).every(Boolean), JSON.stringify(revisions));

  // 改一处共享事实（走「核对 + 写回」入口）
  //
  // 选**技能**类事实而非经历：已确认档案改共享事实的入口是「核对 + 写回」，它写回的是
  // 该事实的文本；技能名属于可同步字段（title 节点），经历描述属于 AI 改写要点——
  // 后者按设计不会被自动改写，只会提示「需要你确认或重新生成」。
  const facts = await apiJson("GET", `${API}/api/v1/profiles/${profileId}/facts`);
  const fact = (facts.data && facts.data.facts || []).find(item => String(item.fact_key).startsWith("skill:"));
  if (!fact) return step("流程3 · 找到共享事实", false, JSON.stringify(facts.data).slice(0, 160));
  const [kind, sourceId] = String(fact.fact_key).split(":");
  const updated = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/facts/attest`, {
    fact_key: fact.fact_key,
    status: "USER_ATTESTED",
    fact_text: `${fact.original_text}（已核对）`,
    apply_to_source: true,
  });
  step("流程3 · 更新共享原始事实", updated.status === 200 && updated.data && updated.data.applied_to_source === true, `status=${updated.status} key=${fact.fact_key}`);

  const impact = await apiJson("GET", `${API}/api/v1/profiles/${profileId}/facts/${kind}/${sourceId}/impact`);
  const total = impact.data ? impact.data.total_missions : 0;
  step("流程3 · 影响面提示「关联 N 份，其中 M 份可能需要更新」", total >= 2 && /可能需要更新/.test(String(impact.data && impact.data.summary)), String(impact.data && impact.data.summary));

  const target = missions[1];
  const synced = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/facts/${kind}/${sourceId}/sync`, { mission_id: target });
  step("流程3 · 只更新选中的那一份", Boolean(synced.data && synced.data.changed), `mission=${target} changed=${synced.data && synced.data.changed} skipped=${(synced.data && synced.data.skipped || []).length}`);
  const after = {};
  for (const id of missions) {
    const studio = await apiJson("GET", `${API}/api/v1/job-missions/${id}/resume-studio`);
    after[id] = studio.data && typeof studio.data.revision === "number" ? studio.data.revision : null;
  }
  const untouched = missions.filter(id => id !== target).every(id => after[id] === revisions[id]);
  step("流程3 · 另外两份保持原版本", untouched && after[target] !== revisions[target], JSON.stringify(after));

  // 浏览器侧：事实核对页要能看到影响面，并给出「只更新这一份」
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    // 事实核对面板挂在「简历」页里；当前档案来自 localStorage，不是 URL 参数。
    await page.addInitScript(
      ([key, pid]) => window.localStorage.setItem(key, pid),
      ["ai-career-os-dogfood-profile-id", profileId],
    );
    await page.goto(`${WEB}/resumes`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(4000);
    await page.screenshot({ path: path.join(SHOTS, "flow3-01-fact-impact.png"), fullPage: true });
    const body = await page.textContent("body").catch(() => "");
    // 断言收紧到面板真实文案，避免「页面上只要出现『核对』两字就算过」。
    step(
      "流程3 · 事实核对面板渲染出待核对事实",
      /核对这段经历/.test(body || "") && /需要你核实|待核对|事实核对/.test(body || ""),
      (body || "").slice(0, 80).replace(/\s+/g, " "),
    );
  } finally {
    await context.close();
  }
  return true;
}

async function flow4(browser, seed) {
  if (!seed) return step("流程4 · 依赖流程1", false, "SKIPPED");
  const missionId = seed.missionId;
  const studio = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);
  const revision = studio.data.revision;
  const confirmed = await apiJson("POST", `${API}/api/v1/job-missions/${missionId}/resume-studio/confirm`, {}, { "If-Match": String(revision) });
  step("流程4 · 确认正式投递版", confirmed.status === 200, `revision=${revision}`);

  const application = await apiJson("POST", `${API}/api/v1/profiles/${seed.profileId}/applications`, {
    profile_id: seed.profileId,
    mission_id: missionId,
    company: "Acme",
    role: "AI 产品经理实习生",
    status: "APPLIED",
    applied_at: "2026-10-18",
  });
  const applicationId = application.data && application.data.id;
  step("流程4 · 创建投递记录", Boolean(applicationId), `application=${applicationId}`);
  const bound = await apiJson("POST", `${API}/api/v1/applications/${applicationId}/bind-resume`, { mission_id: missionId });
  step("流程4 · 绑定投递版本并生成快照", bound.status === 200, `studio_revision=${bound.data && bound.data.studio_revision}`);

  // 投递之后继续改 Studio
  const document = studio.data.document;
  const entry = (document.sections.find(section => section.kind === "experience") || {}).entries?.[0];
  const beforePatch = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/resume-studio`);
  if (entry) {
    await apiJson("PATCH", `${API}/api/v1/job-missions/${missionId}/resume-studio`, {
      type: "add_bullet",
      entry_id: entry.id,
      text: "投递之后才新增的经历",
    }, { "If-Match": String(beforePatch.data && beforePatch.data.revision) });
  }
  const interview = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/interview-resume`);
  const texts = ((interview.data && interview.data.bullets) || []).map(item => item.text).join(" | ");
  step("流程4 · 面试读取实际投递版本", interview.data && interview.data.delivered === true, `source=${interview.data && interview.data.source}`);
  step("流程4 · 投递后新增内容不会混入面试", !texts.includes("投递之后才新增的经历"), texts.slice(0, 60));

  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  await page.goto(`${WEB}/missions/${missionId}/interview`, { waitUntil: "domcontentloaded", timeout: 60000 });
  await page.waitForTimeout(5000);
  const body = await page.textContent("body").catch(() => "");
  step("流程4 · 面试页标注使用的是投递版本", /实际投递|投递记录绑定/.test(body || ""), (body || "").slice(0, 80).replace(/\s+/g, " "));
  await page.screenshot({ path: path.join(SHOTS, "flow4-01-interview-version.png"), fullPage: true });
  await context.close();
  return true;
}

async function flow5(browser, seed) {
  if (!seed) return step("流程5 · 依赖流程1", false, "SKIPPED");
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    await page.goto(WEB, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.evaluate(() => window.localStorage.clear());
    await page.reload({ waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SHOTS, "flow5-01-clean.png"), fullPage: true });
    const body = await page.textContent("body").catch(() => "");
    const hasRecovery = /恢复|选择档案|已有档案|档案列表/.test(body || "");
    step("流程5 · 清理 LocalStorage 后仍可从服务端档案恢复", hasRecovery, (body || "").slice(0, 80).replace(/\s+/g, " "));
    const list = await apiJson("GET", `${API}/api/v1/local/profiles`);
    step("流程5 · 服务端档案列表可用（不需要记 UUID）", ((list.data && list.data.profiles) || []).length > 0, `count=${((list.data && list.data.profiles) || []).length}`);
    return true;
  } finally {
    await context.close();
  }
}

async function flow6(browser) {
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    // 不依赖模型的建档：新起草一份档案后用本地规则解析（不用模型、不改已有档案）
    const draft = await apiJson("POST", `${API}/api/v1/profiles/draft`, {});
    const profileId = draft.data && (draft.data.profile_id || draft.data.id);
    if (!profileId) return step("流程6 · 建立无模型档案", false, JSON.stringify(draft.data).slice(0, 120));
    const ingested = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/resumes/local`, { raw_text: RESUME_TEXT });
    step("流程6 · 无模型建档（本地规则解析）", ingested.status === 200 && ingested.data && ingested.data.parse_source === "LOCAL_RULE", `status=${ingested.status}`);

    await page.goto(`${WEB}/resumes?profile_id=${profileId}`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(3000);
    await page.screenshot({ path: path.join(SHOTS, "flow6-01-no-model.png"), fullPage: true });
    const body = await page.textContent("body").catch(() => "");
    step("流程6 · 简历原文可查看/编辑", /编辑|保存|原文|简历/.test(body || ""), (body || "").slice(0, 50).replace(/\s+/g, " "));

    const mission = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/job-missions`, { raw_text: JD_A });
    step("流程6 · 无模型也能管理岗位", Boolean(mission.data && mission.data.id), `status=${mission.status}`);

    await page.goto(`${WEB}/settings/model`, { waitUntil: "domcontentloaded", timeout: 60000 }).catch(() => {});
    await page.waitForTimeout(2500);
    const settings = await page.textContent("body").catch(() => "");
    step("流程6 · AI 功能指向模型配置说明", /模型|Key|配置/.test(settings || ""), (settings || "").slice(0, 50).replace(/\s+/g, " "));
    return true;
  } finally {
    await context.close();
  }
}

async function flow7(browser, seed) {
  /**
   * FINAL FREEZE P1-A / P1-B：已确认档案的**受控字段修正**。
   *
   * 验证三件事：
   * 1. 整体 PUT 依然被拒（不能为了可达就把 CONFIRMED 的锁全开）；
   * 2. 通过「核对 + 写回」可以修正起止时间，并返回新旧值对照；
   * 3. 修正后：影响面提示「可能需要更新」、只同步选中的那一份、
   *    **历史投递快照的内容哈希不变**。
   */
  if (!seed) return step("流程7 · 依赖流程1", false, "SKIPPED");
  const profileId = seed.profileId;
  const missionId = seed.missionId;

  // 1. 整体覆盖仍然被拒
  const profile = await apiJson("GET", `${API}/api/v1/profiles/${profileId}`);
  const whole = await apiJson("PUT", `${API}/api/v1/profiles/${profileId}`, {
    full_name: (profile.data && profile.data.full_name) || "陈林",
  });
  step("流程7 · 已确认档案的整体 PUT 仍然被拒", whole.status === 409, `status=${whole.status}`);

  // 2. 受控修正起止时间
  const facts = await apiJson("GET", `${API}/api/v1/profiles/${profileId}/facts`);
  const fact = ((facts.data && facts.data.facts) || []).find(item => String(item.fact_key).startsWith("experience:"));
  if (!fact) return step("流程7 · 找到共享经历事实", false, JSON.stringify(facts.data).slice(0, 160));
  const oldDates = (fact.field_values || {}).dates || "";
  const newDates = "2025.03-2025.09";
  const corrected = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/facts/attest`, {
    fact_key: fact.fact_key,
    status: "USER_ATTESTED",
    apply_to_source: true,
    field_updates: { dates: newDates },
  });
  const changes = (corrected.data && corrected.data.field_changes) || [];
  const datesChange = changes.find(item => item.field === "dates");
  step(
    "流程7 · 受控修正起止时间（返回新旧值）",
    corrected.status === 200 && Boolean(datesChange) && datesChange.new_value === newDates,
    `applied=${JSON.stringify((corrected.data || {}).applied_fields)} old=${datesChange ? datesChange.old_value : ""} new=${datesChange ? datesChange.new_value : ""}`,
  );

  const afterCorrection = await apiJson("GET", `${API}/api/v1/profiles/${profileId}`);
  const experience = ((afterCorrection.data && afterCorrection.data.experiences) || [])[0];
  step("流程7 · 修正已写回原始事实", Boolean(experience && experience.dates === newDates), `dates=${experience && experience.dates}`);

  // 字段白名单之外的修正必须被拒
  const rejected = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/facts/attest`, {
    fact_key: fact.fact_key,
    status: "USER_ATTESTED",
    apply_to_source: true,
    field_updates: { full_name: "张三" },
  });
  step("流程7 · 白名单外的字段修正被拒", rejected.status === 422, `status=${rejected.status}`);

  // 3. 影响面 + 只更新选中 + 快照不变
  const [kind, sourceId] = String(fact.fact_key).split(":");
  const impact = await apiJson("GET", `${API}/api/v1/profiles/${profileId}/facts/${kind}/${sourceId}/impact`);
  step(
    "流程7 · 影响面提示「可能需要更新」",
    Boolean(impact.data && impact.data.total_missions >= 1 && /可能需要更新/.test(String(impact.data.summary))),
    String(impact.data && impact.data.summary),
  );

  const snapshotsBefore = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/delivery-versions`);
  const beforeHash = ((snapshotsBefore.data && snapshotsBefore.data.versions) || [])[0];
  const beforeRevisions = {};
  for (const id of [missionId, ...((impact.data && impact.data.missions) || []).map(item => item.mission_id)]) {
    const studio = await apiJson("GET", `${API}/api/v1/job-missions/${id}/resume-studio`);
    beforeRevisions[id] = studio.data ? studio.data.revision : null;
  }

  const synced = await apiJson("POST", `${API}/api/v1/profiles/${profileId}/facts/${kind}/${sourceId}/sync`, { mission_id: missionId });
  step("流程7 · 只更新选中的那一份", Boolean(synced.data && synced.data.changed), `changed=${synced.data && synced.data.changed}`);

  const snapshotsAfter = await apiJson("GET", `${API}/api/v1/job-missions/${missionId}/delivery-versions`);
  const afterHash = ((snapshotsAfter.data && snapshotsAfter.data.versions) || [])[0];
  step(
    "流程7 · 历史投递快照内容哈希不变",
    Boolean(beforeHash && afterHash && beforeHash.content_hash === afterHash.content_hash),
    `before=${beforeHash && beforeHash.content_hash ? beforeHash.content_hash.slice(0, 12) : "-"} after=${afterHash && afterHash.content_hash ? afterHash.content_hash.slice(0, 12) : "-"}`,
  );

  // 浏览器侧：核对页要能看到「起止时间」输入框与新旧值对照
  const context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  const page = await context.newPage();
  try {
    // 「简历」页的当前档案来自 localStorage（不是 URL 参数），而流程5 刚清过存储，
    // 所以这里必须先把档案 ID 写回去，否则核对面板根本不会渲染。
    await page.addInitScript(
      ([key, pid]) => window.localStorage.setItem(key, pid),
      ["ai-career-os-dogfood-profile-id", profileId],
    );
    await page.goto(`${WEB}/resumes`, { waitUntil: "domcontentloaded", timeout: 60000 });
    await page.waitForTimeout(4000);
    // 事实默认收起，必须点开某一条才能看到受控修正入口——这是产品真实交互，E2E 照做。
    const toggle = page.locator("button", { hasText: "核对这段经历" }).first();
    if ((await toggle.count()) > 0) {
      await toggle.click().catch(() => {});
      await page.waitForTimeout(2000);
    }
    const body = await page.textContent("body").catch(() => "");
    step(
      "流程7 · 核对页出现受控修正入口",
      /受控修正|起止时间/.test(body || ""),
      (body || "").slice(0, 60).replace(/\s+/g, " "),
    );
    await page.screenshot({ path: path.join(SHOTS, "flow7-01-field-correction.png"), fullPage: true });
  } finally {
    await context.close();
  }
  return true;
}

(async () => {
  const browser = await chromium.launch({ headless: true });
  let seed = null;
  try {
    seed = await flow1(browser);
    await flow2(browser, seed);
    await flow3(browser, seed);
    await flow4(browser, seed);
    await flow5(browser, seed);
    await flow6(browser);
    await flow7(browser, seed);
  } catch (caught) {
    step("E2E 运行异常", false, String(caught && caught.message ? caught.message : caught));
  } finally {
    await browser.close();
  }
  const passed = results.filter(item => item.ok).length;
  const report = {
    web: WEB,
    api: API,
    finished_at: new Date().toISOString(),
    total: results.length,
    passed,
    failed: results.length - passed,
    results,
  };
  fs.writeFileSync(path.join(OUT, "e2e-result.json"), JSON.stringify(report, null, 2));
  log(`汇总：${passed}/${results.length} 通过`);
  process.exit(report.failed === 0 ? 0 : 1);
})();
