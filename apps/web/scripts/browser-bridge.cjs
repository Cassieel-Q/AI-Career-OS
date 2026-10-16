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

const http = require("http");

let PORT = Number(process.env.BROWSER_BRIDGE_PORT || 8770);

let playwright;
try {
  playwright = require("playwright");
} catch (err) {
  console.error("[bridge] 无法加载 playwright：" + err.message);
  process.exit(2);
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

function send(res, status, payload) {
  const body = JSON.stringify(payload === undefined ? null : payload);
  res.writeHead(status, {
    "Content-Type": "application/json; charset=utf-8",
    "Content-Length": Buffer.byteLength(body),
    "Access-Control-Allow-Origin": "*",
  });
  res.end(body);
}

const server = http.createServer(async (req, res) => {
  const url = new URL(req.url, "http://127.0.0.1");
  const route = `${req.method} ${url.pathname}`;
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
      return send(res, 200, data);
    }
    return send(res, 404, { error: `未知路由 ${route}` });
  } catch (err) {
    return send(res, 500, { error: (err && err.message) || String(err) });
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
    console.log(`[bridge] 受控浏览器桥已就绪 → http://127.0.0.1:${port}`);
    console.log("[bridge] 仅本机可访问；只读表单 / 只填表单，永不提交。");
  });
}

listen(PORT, 0);

process.on("SIGINT", async () => {
  try {
    if (context) await context.close();
  } catch (e) {}
  process.exit(0);
});
