/**
 * 后台服务（MV3 service worker）。
 *
 * 只做两件事：
 * 1. 用户点击扩展后，把 extract.js 注入**当前活动标签页**读取已经显示的岗位文本；
 * 2. 把读取结果与本机 AI Career OS 通信（所有写请求都带配对令牌）。
 *
 * 不做的事：不读 Cookie / 密码 / 聊天记录，不请求 webRequest 权限，
 * 不模拟点击，不自动提交任何表单，不向任何外部服务器上传岗位数据。
 */
const DEFAULT_API_BASE = "http://127.0.0.1:8100";

async function readSettings() {
  const stored = await chrome.storage.local.get(["aiCareerApiBase", "aiCareerToken"]);
  return {
    apiBase: (stored.aiCareerApiBase || DEFAULT_API_BASE).replace(/\/+$/, ""),
    token: stored.aiCareerToken || "",
  };
}

async function writeSettings(patch) {
  await chrome.storage.local.set(patch);
}

async function activeTabId() {
  const [tab] = await chrome.tabs.query({ active: true, currentWindow: true });
  if (!tab || !tab.id) throw new Error("没有找到当前标签页。");
  if (!/^https?:/.test(tab.url || "")) throw new Error("当前页面不是网页，无法读取。");
  return tab.id;
}

/** 用户点击后才注入：activeTab 权限会在点击扩展图标时临时授予。 */
async function extractFromActiveTab() {
  const tabId = await activeTabId();
  const results = await chrome.scripting.executeScript({
    target: { tabId },
    files: ["extract.js"],
  });
  const first = results && results[0];
  // 页面内脚本报错：把真实错误带出来，不让它变成「没有返回内容」
  if (first && first.error) {
    const detail = first.error && first.error.message ? first.error.message : String(first.error);
    throw new Error(`页面脚本执行出错：${String(detail).slice(0, 200)}`);
  }
  const value = first && first.result;
  if (!value) {
    const raw = JSON.stringify(results || []).slice(0, 200);
    throw new Error(
      `页面没有返回可读内容（注入结果：${raw}）。请先刷新页面（F5）再点一次；还是失败就把这条发出来。`,
    );
  }
  return value;
}

async function callApi(path, options = {}) {
  const { apiBase, token } = await readSettings();
  const headers = Object.assign({ "Content-Type": "application/json" }, options.headers || {});
  if (token && !options.anonymous) headers["X-AI-Career-Token"] = token;
  let response;
  try {
    response = await fetch(`${apiBase}${path}`, { method: options.method || "GET", headers, body: options.body });
  } catch (caught) {
    throw new Error(`连不上本机 AI Career OS（${apiBase}）。请确认已经双击桌面图标启动，或到扩展设置里检查端口。`);
  }
  let payload = null;
  try {
    payload = await response.json();
  } catch (_) {
    /* 非 JSON 响应 */
  }
  if (!response.ok) {
    const detail = payload && payload.detail ? payload.detail : `HTTP ${response.status}`;
    throw new Error(detail);
  }
  return payload;
}

chrome.runtime.onMessage.addListener((message, _sender, sendResponse) => {
  const handlers = {
    async status() {
      const { apiBase } = await readSettings();
      return { apiBase, ...(await callApi("/api/v1/extension/status", { anonymous: true })) };
    },
    extract: extractFromActiveTab,
    async pair() {
      const payload = await callApi("/api/v1/extension/pair/exchange", {
        method: "POST",
        anonymous: true,
        body: JSON.stringify({ code: String(message.code || "").trim() }),
      });
      await writeSettings({ aiCareerToken: payload.token });
      return { token_fingerprint: payload.token_fingerprint };
    },
    async parse() {
      return callApi("/api/v1/extension/job-import/parse", {
        method: "POST",
        body: JSON.stringify({
          source_text: message.source_text,
          source_url: message.source_url,
          source_site: message.source_site,
          provided: message.provided || {},
        }),
      });
    },
    async save() {
      return callApi("/api/v1/extension/job-import/save", {
        method: "POST",
        body: JSON.stringify({
          draft: message.draft,
          update_duplicates: Boolean(message.update_duplicates),
        }),
      });
    },
    async settings() {
      return readSettings();
    },
    async saveSettings() {
      await writeSettings({
        aiCareerApiBase: (message.apiBase || DEFAULT_API_BASE).trim(),
        aiCareerToken: (message.token || "").trim(),
      });
      return readSettings();
    },
    async clearToken() {
      await writeSettings({ aiCareerToken: "" });
      return readSettings();
    },
  };

  const handler = handlers[message && message.type];
  if (!handler) {
    sendResponse({ ok: false, error: `未知指令：${message && message.type}` });
    return false;
  }
  handler().then(
    (data) => sendResponse({ ok: true, data }),
    (error) => sendResponse({ ok: false, error: error instanceof Error ? error.message : String(error) }),
  );
  return true; // 异步响应
});
