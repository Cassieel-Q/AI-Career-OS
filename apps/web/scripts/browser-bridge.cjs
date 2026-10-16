/**
 * AI Career OS · 受控浏览器桥（本地 only）
 *
 * 用途：为「网申填表」提供一个**用户显式启动**的本地浏览器会话，
 * 支持读取表单字段、按用户确认的计划填写字段。
 *
 * 硬性约束：
 * - 只监听 127.0.0.1，不对外暴露；
 * - **永不点击任何提交按钮**，不处理密码 / 验证码 / 隐藏域；
 * - 只做「读」与「填」，不做登录、不改站点权限、不绕过任何反自动化限制。
 *
 * 运行：node apps/web/scripts/browser-bridge.cjs   （或 start-browser-bridge.cmd）
 */
"use strict";

const crypto = require("crypto");
const fs = require("fs");
const os = require("os");
const path = require("path");
const http = require("http");

let PORT = Number(process.env.BROWSER_BRIDGE_PORT || 8770);

let playwright;
try {
  playwright = require("playwright");
} catch (err) {
  console.error("[bridge] 无法加载 playwright：" + err.message);
  process.exit(2);
}

// ---------------------------------------------------------------- 鉴权与来源校验
//
// 浏览器桥能读取用户已打开的招聘页面并代填表单，因此必须防止本机其它网页
// 或局域网里的进程随意调用：
//   1. 只监听 127.0.0.1；
//   2. 每次调用都校验连接来源是回环地址；
//   3. 除 /health 外一律要求 `Authorization: Bearer <token>`；
//   4. 带 Origin 头的请求必须来自白名单（默认本机前端）。

const TOKEN = (process.env.BROWSER_BRIDGE_TOKEN || crypto.randomBytes(32).toString("hex")).trim();

const DEFAULT_ALLOWED_ORIGINS = [
  "http://127.0.0.1:3000",
  "http://localhost:3000",
  "http://127.0.0.1:3001",
  "http://localhost:3001",
];
const ALLOWED_ORIGINS = new Set(
  (process.env.BROWSER_BRIDGE_ALLOWED_ORIGINS || DEFAULT_ALLOWED_ORIGINS.join(","))
    .split(",")
    .map((s) => s.trim())
    .filter(Boolean)
);
// 后端 / 脚本等非浏览器调用不带 Origin，允许通过。
const ALLOW_NO_ORIGIN = process.env.BROWSER_BRIDGE_ALLOW_NO_ORIGIN !== "0";

function tokenFilePath() {
  if (process.env.AI_CAREER_BRIDGE_TOKEN_FILE) return path.resolve(process.env.AI_CAREER_BRIDGE_TOKEN_FILE);
  const dataDir = process.env.AI_CAREER_DATA_DIR || (process.env.LOCALAPPDATA ? path.join(process.env.LOCALAPPDATA, "AICareerOS") : "");
  if (dataDir) return path.join(dataDir, "browser-bridge.token");
  return path.join(os.tmpdir(), "ai-career-os-browser-bridge.token");
}

function persistToken() {
  const target = tokenFilePath();
  try {
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, TOKEN, { encoding: "utf-8", mode: 0o600 });
    console.log("[bridge] 令牌文件 → " + target);
  } catch (err) {
    console.warn("[bridge] 无法写入令牌文件（后端需设置 AI_CAREER_BRIDGE_TOKEN）：" + err.message);
  }
}

function isLoopback(addr) {
  if (!addr) return false;
  const a = String(addr);
  return a === "127.0.0.1" || a === "::1" || a === "::ffff:127.0.0.1" || a === "localhost";
}

function constantTimeEqual(a, b) {
  const ba = Buffer.from(String(a));
  const bb = Buffer.from(String(b));
  if (ba.length !== bb.length) return false;
  return crypto.timingSafeEqual(ba, bb);
}

/**
 * 统一安全闸门。返回 null 表示放行，否则返回 { status, error }。
 */
function guard(req, route) {
  if (!isLoopback(req.socket && req.socket.remoteAddress)) {
    return { status: 403, error: "浏览器桥只接受本机回环地址调用。" };
  }
  const origin = req.headers.origin;
  if (origin && !ALLOWED_ORIGINS.has(String(origin).replace(/\/$/, ""))) {
    return { status: 403, error: "请求来源不在白名单内。" };
  }
  if (!origin && !ALLOW_NO_ORIGIN) {
    return { status: 403, error: "缺少 Origin 头。" };
  }
  // /health 只暴露"是否可用"，不含页面内容，放行以便前端展示状态。
  if (route === "GET /health" || req.method === "OPTIONS") return null;
  const header = String(req.headers.authorization || "");
  const presented = header.startsWith("Bearer ") ? header.slice(7).trim() : "";
  if (!presented || !constantTimeEqual(presented, TOKEN)) {
    return { status: 401, error: "未授权：缺少或不匹配的浏览器桥令牌。" };
  }
  return null;
}

/** @type {import('playwright').BrowserContext|null} */
let context = null;
/** @type {import('playwright').Page|null} */
let page = null;

// ---------------------------------------------------------------- 页面脚本

const EXTRACT_SCRIPT = `(() => {
  const out = [];
  const all = Array.from(document.querySelectorAll('input, textarea, select'));
  let idx = 0;
  const seenRadioGroups = new Set();
  const visible = (el) => {
    const s = window.getComputedStyle(el);
    if (s.display === 'none' || s.visibility === 'hidden') return false;
    const r = el.getBoundingClientRect();
    return r.width > 0 && r.height > 0;
  };
  const labelOf = (el, type) => {
    let text = '';
    const groupLike = type === 'radio' || type === 'checkbox';
    // 单选框/复选框：优先找「字段标题」而不是选项自身的文案。
    if (groupLike) {
      const fieldset = el.closest('fieldset');
      if (fieldset && fieldset.querySelector('legend')) text = fieldset.querySelector('legend').innerText;
      if (!text) {
        // 选项通常包在自己的 <label> 里，需要向上找「字段标题」（不超过 3 层）。
        let node = el.parentElement;
        for (let i = 0; i < 3 && node && !text; i++) {
          const first = node.firstElementChild;
          if (first && !first.contains(el) && first.innerText && first.innerText.trim().length <= 24) {
            text = first.innerText;
          }
          node = node.parentElement;
        }
      }
    }
    if (!text && el.id) {
      try {
        const l = document.querySelector('label[for="' + CSS.escape(el.id) + '"]');
        if (l) text = l.innerText;
      } catch (e) {}
    }
    if (!text && !groupLike) {
      const wrap = el.closest('label');
      if (wrap) text = wrap.innerText;
    }
    if (!text) {
      // 相邻的前一个兄弟作为标题（常见：<div>姓名</div><input>）
      let prev = el.previousElementSibling;
      if (prev && prev.innerText && prev.innerText.trim().length <= 24) text = prev.innerText;
    }
    if (!text) text = el.getAttribute('aria-label') || el.getAttribute('placeholder') || '';
    return (text || '').replace(/\\s+/g, ' ').trim().slice(0, 80);
  };

  for (const el of all) {
    const tag = el.tagName.toLowerCase();
    let type = tag === 'textarea' ? 'textarea' : tag === 'select' ? 'select' : ((el.getAttribute('type') || 'text').toLowerCase());
    if (!visible(el)) continue;
    if (el.disabled || el.readOnly) type = type + '';
    const disabled = !!el.disabled;

    const name = el.getAttribute('name') || '';
    const id = el.getAttribute('id') || '';

    if (type === 'radio') {
      if (seenRadioGroups.has(name)) continue;
      seenRadioGroups.add(name);
    }

    const selector = '[data-aios-field="' + idx + '"]';
    el.setAttribute('data-aios-field', String(idx));

    const item = {
      index: idx,
      tag,
      type,
      control: type,
      name,
      id,
      label: labelOf(el, type),
      placeholder: el.getAttribute('placeholder') || '',
      required: el.hasAttribute('required'),
      disabled,
      selector,
      options: [],
      value: el.value || ''
    };

    if (type === 'select') {
      item.options = Array.from(el.options).map((o) => o.text.trim()).filter((t) => t.length > 0);
    }
    if (type === 'radio') {
      const group = Array.from(document.querySelectorAll('input[type=radio]')).filter((r) => r.name === name);
      item.options = group.map((r) => (r.getAttribute('data-label') || r.value || '')).filter(Boolean);
    }
    if (type === 'checkbox') {
      item.options = ['勾选'];
    }

    out.push(item);
    idx += 1;
  }
  return { fields: out, pageUrl: location.href, pageTitle: document.title };
})()`;

function fillInPage(payload) {
  const NEVER = ['password', 'hidden', 'submit', 'button', 'captcha', 'file'];
  const results = [];
  const setNative = (el, value) => {
    const proto = Object.getPrototypeOf(el);
    const desc = Object.getOwnPropertyDescriptor(proto, 'value');
    if (desc && desc.set) {
      desc.set.call(el, value);
    } else {
      el.value = value;
    }
  };
  const fire = (el) => {
    el.dispatchEvent(new Event('input', { bubbles: true }));
    el.dispatchEvent(new Event('change', { bubbles: true }));
    el.dispatchEvent(new Event('blur', { bubbles: true }));
  };
  for (const a of payload.assignments) {
    let el = null;
    try {
      el = document.querySelector(a.selector);
    } catch (e) {
      el = null;
    }
    if (!el && a.name) el = document.querySelector('[name="' + a.name + '"]');
    const control = (a.control || 'text').toLowerCase();
    if (NEVER.includes(control)) {
      results.push({ selector: a.selector, label: a.label, ok: false, reason: '该控件类型永不自动填写' });
      continue;
    }
    if (!el) {
      results.push({ selector: a.selector, label: a.label, ok: false, reason: '页面上找不到该字段（可能已重新渲染）' });
      continue;
    }
    if (el.disabled) {
      results.push({ selector: a.selector, label: a.label, ok: false, reason: '字段为禁用状态' });
      continue;
    }
    try {
      if (control === 'select') {
        const opt = Array.from(el.options).find((o) => o.text.trim() === a.value || o.value === a.value || o.text.trim().includes(a.value) || a.value.includes(o.text.trim()));
        if (!opt) {
          results.push({ selector: a.selector, label: a.label, ok: false, reason: '下拉项中没有匹配到的值' });
          continue;
        }
        el.value = opt.value;
        fire(el);
      } else if (control === 'radio') {
        const group = Array.from(document.querySelectorAll('input[type=radio]')).filter((r) => r.name === el.name);
        const target = group.find((r) => (r.getAttribute('data-label') || r.value || '') === a.value || (r.parentElement && r.parentElement.innerText.trim() === a.value));
        if (!target) {
          results.push({ selector: a.selector, label: a.label, ok: false, reason: '单选项中没有匹配项，需人工选择' });
          continue;
        }
        target.click();
        fire(target);
      } else if (control === 'checkbox') {
        if (!el.checked) el.click();
        fire(el);
      } else if (control === 'date' || control === 'month') {
        const iso = String(a.value).replace(/[年./]/g, '-').replace(/月/g, '-').replace(/-+$/, '');
        const m = iso.match(/^(\d{4})-?(\d{1,2})?/);
        if (!m) {
          results.push({ selector: a.selector, label: a.label, ok: false, reason: '日期格式无法标准化' });
          continue;
        }
        const yyyy = m[1];
        const mm = (m[2] || '01').padStart(2, '0');
        el.value = control === 'month' ? yyyy + '-' + mm : yyyy + '-' + mm + '-01';
        fire(el);
      } else {
        setNative(el, a.value);
        fire(el);
      }
      const applied = control === 'radio' || control === 'checkbox' ? true : String(el.value || '').length > 0;
      results.push({ selector: a.selector, label: a.label, ok: applied, reason: applied ? '' : '写入后字段仍为空' });
    } catch (e) {
      results.push({ selector: a.selector, label: a.label, ok: false, reason: '填写异常：' + (e && e.message ? e.message : String(e)) });
    }
  }
  return { results, pageUrl: location.href, pageTitle: document.title };
}

/**
 * 「采集当前招聘网页」：只读取页面上**已经可见**的内容。
 *
 * 优先解析页面自带的 schema.org JobPosting 结构化数据（招聘站普遍提供，公开可读），
 * 其次用 DOM 常见类名与标题做启发式兜底；识别不了就标 MISSING / LOW 交用户确认。
 * 不做登录、不破解验证码、不调用任何隐藏接口。
 */
const EXTRACT_JOB_SCRIPT = `(() => {
  const norm = (s) => (s || '').replace(/\\s+/g, ' ').trim();
  const textOf = (el) => (el && el.innerText ? norm(el.innerText) : '');
  const pick = (selectors) => {
    for (const sel of selectors) {
      try {
        const el = document.querySelector(sel);
        const t = textOf(el);
        if (t) return t;
      } catch (e) {}
    }
    return '';
  };

  const bodyText = norm(document.body ? document.body.innerText : '').slice(0, 8000);
  const lower = bodyText.toLowerCase();
  const BLOCK_MARKERS = [
    'captcha', 'verify you are human', 'are you a robot', 'please sign in', 'sign in to continue',
    'login required', 'access denied', '请完成安全验证', '请先登录', '登录后查看', '请登录后'
  ];
  if (BLOCK_MARKERS.some((m) => lower.includes(m))) {
    return {
      status: 'BLOCKED',
      page_url: location.href,
      page_title: document.title,
      note: '当前页面需要登录或验证码才能查看，浏览器桥不做任何绕过。请手动复制岗位正文或改用粘贴导入。'
    };
  }

  // ---- 1) schema.org JobPosting（JSON-LD）
  let ld = null;
  const scripts = Array.from(document.querySelectorAll('script[type="application/ld+json"]'));
  for (const s of scripts) {
    let parsed = null;
    try { parsed = JSON.parse(s.textContent || ''); } catch (e) { continue; }
    const stack = Array.isArray(parsed) ? parsed.slice() : [parsed];
    while (stack.length) {
      const node = stack.pop();
      if (!node || typeof node !== 'object') continue;
      if (Array.isArray(node['@graph'])) { stack.push.apply(stack, node['@graph']); continue; }
      const types = node['@type'];
      const list = Array.isArray(types) ? types : [types];
      if (list.map((t) => String(t || '').toLowerCase()).includes('jobposting')) { ld = node; break; }
      for (const key of Object.keys(node)) {
        const value = node[key];
        if (value && typeof value === 'object') stack.push(value);
      }
    }
    if (ld) break;
  }

  const htmlToText = (raw) => {
    if (!raw) return '';
    const div = document.createElement('div');
    div.innerHTML = String(raw);
    return norm(div.innerText || div.textContent || '');
  };

  const confidence = {};
  let company = '';
  let role = '';
  let location = '';
  let jd = '';
  let posted_at = null;
  let employment_type = null;
  let apply_url = '';
  let source = 'jsonld';

  if (ld) {
    role = norm(ld.title || '');
    const org = ld.hiringOrganization || {};
    company = norm(typeof org === 'string' ? org : (org.name || ''));
    const loc = ld.jobLocation || ld.jobLocationType || null;
    if (Array.isArray(loc) && loc.length) {
      const first = loc[0] || {};
      const addr = first.address || {};
      location = norm(addr.addressLocality || addr.addressRegion || addr.addressCountry || '');
    } else if (loc && typeof loc === 'object') {
      const addr = loc.address || {};
      location = norm(addr.addressLocality || addr.addressRegion || addr.addressCountry || '');
    } else if (typeof loc === 'string') {
      location = norm(loc === 'TELECOMMUTE' ? 'Remote' : loc);
    }
    jd = htmlToText(ld.description || '');
    posted_at = ld.datePosted || ld.validThrough || null;
    employment_type = ld.employmentType || null;
    apply_url = typeof ld.url === 'string' ? ld.url : (ld.directApply === true ? location.href : '');
    confidence.company = company ? 'HIGH' : 'MISSING';
    confidence.role = role ? 'HIGH' : 'MISSING';
    confidence.location = location ? 'HIGH' : 'MISSING';
    confidence.jd = jd.length > 120 ? 'HIGH' : (jd ? 'MEDIUM' : 'MISSING');
  }

  // ---- 2) DOM 启发式兜底（只在结构化数据缺项时补）
  const metaContent = (name) => {
    const el = document.querySelector('meta[property="' + name + '"], meta[name="' + name + '"]');
    return el ? norm(el.getAttribute('content') || '') : '';
  };
  if (!role) {
    role = pick(['h1', '[class*="job-title" i]', '[class*="jobtitle" i]', '[class*="posting-headline" i]', '[data-qa="job-title"]']) || metaContent('og:title');
    confidence.role = role ? 'MEDIUM' : 'MISSING';
  }
  if (!company) {
    company = pick(['[class*="company" i]', '[class*="employer" i]', '[data-qa="company-name"]']) || metaContent('og:site_name');
    if (!company && role) {
      // "AI 产品经理 - 某某公司" / "AI 产品经理 at 某某公司"
      const m = role.split(/\\s+[—–|@]|\\s+at\\s+|\\s+·\\s+/);
      if (m.length > 1) {
        company = norm(m[m.length - 1]);
        confidence.company = company ? 'LOW' : 'MISSING';
      }
      role = norm(m[0]);
    } else {
      confidence.company = company ? 'MEDIUM' : 'MISSING';
    }
  }
  if (!location) {
    location = pick(['[class*="location" i]', '[class*="job-location" i]', '[class*="workplace" i]', '[data-qa="job-location"]']);
    confidence.location = location ? 'MEDIUM' : 'MISSING';
  }
  if (!jd) {
    const blocks = Array.from(document.querySelectorAll('[class*="description" i], [class*="job-detail" i], [id*="description" i], main, article, [role="main"]'));
    let best = '';
    for (const el of blocks) {
      const t = textOf(el);
      if (t.length > best.length) best = t;
    }
    jd = best || bodyText;
    confidence.jd = jd.length > 120 ? 'MEDIUM' : (jd ? 'LOW' : 'MISSING');
    if (jd === bodyText) confidence.jd = 'LOW';
    source = 'dom';
  }

  // ---- 3) 列表页判定：JD 很短但页面上有大量岗位链接 → 只支持单职位页
  const jobLinks = Array.from(document.querySelectorAll('a[href]')).filter((a) =>
    /\\/(jobs?|careers?|postings?|positions?|vacanc(y|ies))\\/[A-Za-z0-9_-]+/i.test(a.getAttribute('href') || '')
  );
  if (jd.length < 300 && jobLinks.length >= 3) {
    return {
      status: 'LISTING_UNSUPPORTED',
      page_url: location.href,
      page_title: document.title,
      note: '这是一个岗位**列表页**，无法可靠地区分你要哪一个职位。请点进单个职位详情页后再采集；也可以复制选中文本或粘贴链接手动导入。'
    };
  }
  if (!jd && !role) {
    return {
      status: 'EMPTY',
      page_url: location.href,
      page_title: document.title,
      note: '当前页面没有读到可识别的岗位内容。请点进单个职位详情页再试，或复制岗位正文粘贴导入。'
    };
  }

  return {
    status: 'OK',
    page_url: location.href,
    page_title: document.title,
    company, role, location, jd,
    posted_at, employment_type, apply_url,
    tags: [],
    confidence,
    extraction: source,
    note: source === 'jsonld'
      ? '已从页面自带的 JobPosting 结构化数据读取。'
      : '页面没有结构化岗位数据，已按可见文本推断，请逐项核对后再保存。'
  };
})()`;

// ---------------------------------------------------------------- 浏览器会话

async function ensureContext() {
  if (context) return context;
  // 默认有头（用户可见的本地会话）；自动 E2E 时可用 BROWSER_BRIDGE_HEADLESS=1 无头运行。
  const headless = process.env.BROWSER_BRIDGE_HEADLESS === "1";
  const userDataDir = process.env.BROWSER_BRIDGE_PROFILE
    ? require("path").resolve(process.env.BROWSER_BRIDGE_PROFILE)
    : require("path").join(require("os").tmpdir(), "ai-career-os-browser");
  context = await playwright.chromium.launchPersistentContext(userDataDir, {
    headless,
    viewport: { width: 1280, height: 900 },
    args: ["--no-first-run"],
  });
  context.on("close", () => {
    context = null;
    page = null;
  });
  return context;
}

async function ensurePage() {
  await ensureContext();
  const pages = context.pages();
  if (page && !page.isClosed()) return page;
  page = pages.length ? pages[pages.length - 1] : await context.newPage();
  page.setDefaultTimeout(20000);
  return page;
}

// ---------------------------------------------------------------- HTTP

function readBody(req) {
  return new Promise((resolve) => {
    let raw = "";
    req.on("data", (chunk) => (raw += chunk));
    req.on("end", () => {
      if (!raw) return resolve({});
      try {
        resolve(JSON.parse(raw));
      } catch (e) {
        resolve({});
      }
    });
  });
}

function send(res, status, payload, origin) {
  const body = JSON.stringify(payload === undefined ? null : payload);
  const headers = {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    // 只回显白名单里的 Origin，避免任何站点读取响应。
    "Access-Control-Allow-Origin": origin && ALLOWED_ORIGINS.has(origin.replace(/\/$/, "")) ? origin : "null",
    Vary: "Origin",
    "Access-Control-Allow-Headers": "Authorization, Content-Type",
    "Access-Control-Allow-Methods": "GET, POST, OPTIONS",
    "Cache-Control": "no-store",
  };
  res.writeHead(status, headers);
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const route = `${req.method} ${url.pathname}`;
  const origin = req.headers.origin ? String(req.headers.origin) : "";

  if (req.method === "OPTIONS") {
    return send(res, 204, null, origin);
  }

  const denied = guard(req, route);
  if (denied) {
    console.warn(`[bridge] 拒绝 ${route}（来源 ${req.socket.remoteAddress}）：${denied.error}`);
    return send(res, denied.status, { error: denied.error }, origin);
  }

  try {
    if (route === "GET /health") {
      return send(res, 200, {
        ok: true,
        service: "ai-career-os-browser-bridge",
        session: !!context,
        currentUrl: page && !page.isClosed() ? page.url() : null,
      });
    }
    if (route === "POST /session/start") {
      const body = await readBody(req);
      const p = await ensurePage();
      if (body.url) await p.goto(body.url, { waitUntil: "domcontentloaded" });
      return send(res, 200, { ok: true, pageUrl: p.url(), pageTitle: await p.title() });
    }
    if (route === "POST /session/open") {
      const body = await readBody(req);
      if (!body.url) return send(res, 422, { error: "缺少 url" });
      const p = await ensurePage();
      await p.goto(body.url, { waitUntil: "domcontentloaded" });
      return send(res, 200, { ok: true, pageUrl: p.url(), pageTitle: await p.title() });
    }
    if (route === "POST /session/close") {
      if (context) await context.close();
      context = null;
      page = null;
      return send(res, 200, { ok: true });
    }
    if (route === "POST /read") {
      const p = await ensurePage();
      const data = await p.evaluate(EXTRACT_SCRIPT);
      return send(res, 200, data);
    }
    if (route === "POST /fill") {
      const body = await readBody(req);
      const assignments = Array.isArray(body.assignments) ? body.assignments : [];
      const p = await ensurePage();
      const data = await p.evaluate(fillInPage, { assignments });
      return send(res, 200, data, origin);
    }
    if (route === "POST /extract-job") {
      const p = await ensurePage();
      const data = await p.evaluate(EXTRACT_JOB_SCRIPT);
      return send(res, 200, data, origin);
    }
    return send(res, 404, { error: `未知路由 ${route}` }, origin);
  } catch (err) {
    return send(res, 500, { error: (err && err.message) || String(err) }, origin);
  }
});

// 端口占用时自动顺延，避免与其它本地服务冲突。
function listen(port, attempt) {
  server.once("error", (err) => {
    if (err.code === "EADDRINUSE" && attempt < 5) {
      listen(port + 1, attempt + 1);
    } else {
      console.error("[bridge] 启动失败：" + err.message);
      process.exit(1);
    }
  });
  server.listen(port, "127.0.0.1", () => {
    PORT = port;
    persistToken();
    console.log(`[bridge] 受控浏览器桥已就绪 → http://127.0.0.1:${port}`);
    console.log("[bridge] 仅本机回环可访问；需 Bearer 令牌；只读表单 / 只填表单，永不提交。");
    console.log("[bridge] 允许的 Origin：" + Array.from(ALLOWED_ORIGINS).join(", ") + (ALLOW_NO_ORIGIN ? "（以及不带 Origin 的本机调用）" : ""));
  });
}

listen(PORT, 0);

process.on("SIGINT", async () => {
  try {
    if (context) await context.close();
  } catch (e) {}
  process.exit(0);
});
