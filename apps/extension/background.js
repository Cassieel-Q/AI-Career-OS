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

/**
 * 回读通道常量，必须与 extract.js 里的一致。
 * 注意：MV3 的 executeScript({ files }) 不返回脚本结果（result 恒为 null），
 * 所以 v1.3.0 起改成「注入 → 回读」两段式。
 */
const CAPTURE_ATTR = "data-ai-career-capture";
const CAPTURE_KEY = "aiCareerCapture";

/** 清掉上一次的残留，避免读到旧结果。 */
async function clearCapture(tabId) {
  await chrome.storage.local.remove(CAPTURE_KEY);
  try {
    await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        try {
          document.documentElement.removeAttribute("data-ai-career-capture");
        } catch (_) {
          /* ignore */
        }
        try {
          delete window.__AI_CAREER_CAPTURE__;
        } catch (_) {
          /* ignore */
        }
      },
    });
  } catch (_) {
    /* 清不干净不影响下一步 */
  }
}

/**
 * 回读，三条通道依次降级：
 *   通道 1（主）：func 注入调用页面里的 window.__aiCareerExtract —— MV3 只有 func 注入
 *                才有返回值；files 注入的 result 恒为 null。
 *   通道 2：读 documentElement 上的 data 属性 / 隔离世界全局变量。
 *   通道 3：读 chrome.storage.local（extract.js 写入的兜底）。
 */
async function readCapture(tabId) {
  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        const fn = window.__aiCareerExtract;
        if (typeof fn !== "function") return "__NO_EXTRACT_FN__";
        try {
          return JSON.stringify(fn());
        } catch (error) {
          return "__EXTRACT_ERROR__" + (error && error.message ? error.message : String(error));
        }
      },
    });
    const raw = results && results[0] && results[0].result;
    if (typeof raw === "string" && raw.startsWith("__EXTRACT_ERROR__")) {
      throw new Error(`页面内抽取函数报错：${raw.slice("__EXTRACT_ERROR__".length).slice(0, 200)}`);
    }
    if (typeof raw === "string" && raw.length && raw !== "__NO_EXTRACT_FN__") return raw;
  } catch (error) {
    // 只有「页面内函数报错」才直接抛；其它情况继续走降级通道
    if (error instanceof Error && String(error.message).startsWith("页面内抽取函数报错")) throw error;
  }

  try {
    const results = await chrome.scripting.executeScript({
      target: { tabId },
      func: () => {
        try {
          const attr = document.documentElement.getAttribute("data-ai-career-capture");
          if (attr) return attr;
        } catch (_) {
          /* ignore */
        }
        return window.__AI_CAREER_CAPTURE__ || null;
      },
    });
    const first = results && results[0];
    if (first && first.result) return first.result;
  } catch (_) {
    /* 落到 storage 兜底 */
  }

  const stored = await chrome.storage.local.get(CAPTURE_KEY);
  return stored && stored[CAPTURE_KEY] ? stored[CAPTURE_KEY] : null;
}

/** 用户点击后才注入：activeTab 权限会在点击扩展图标时临时授予。 */
async function extractFromActiveTab() {
  const tabId = await activeTabId();
  await clearCapture(tabId);

  let injected = [];
  try {
    injected = await chrome.scripting.executeScript({
      target: { tabId },
      files: ["extract.js"],
    });
  } catch (error) {
    throw new Error(`注入页面脚本失败：${error instanceof Error ? error.message : String(error)}`);
  }

  // 页面内脚本报错：把真实错误带出来，不让它变成「没有返回内容」
  const first = injected && injected[0];
  if (first && first.error) {
    const detail = first.error && first.error.message ? first.error.message : String(first.error);
    throw new Error(`页面脚本执行出错：${String(detail).slice(0, 200)}`);
  }

  const raw = await readCapture(tabId);
  if (!raw) {
    const frameInfo = String(JSON.stringify(injected || [])).slice(0, 160);
    throw new Error(
      `注入成功但页面没写回结果（${frameInfo}）。请确认扩展版本是 v1.3.1；然后按 F5 刷新 BOSS 页面、点开一个职位卡片再读一次。仍失败请把这条发出来。`,
    );
  }

  let value = null;
  try {
    value = JSON.parse(raw);
  } catch (_) {
    throw new Error(`读取结果不是合法 JSON（前 120 字：${String(raw).slice(0, 120)}）。`);
  }
  if (!value) throw new Error("读取结果为空。");
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
    /** 用扩展本地存的令牌真实校验一次（status 接口只反映服务端有没有令牌，不校验我们这份）。 */
    async verifyPair() {
      const { apiBase, token } = await readSettings();
      if (!token) return { ok: false, hasToken: false };
      try {
        const response = await fetch(`${apiBase}/api/v1/extension/ping`, {
          headers: { "X-AI-Career-Token": token },
        });
        return { ok: response.status === 200, hasToken: true, status: response.status };
      } catch (_) {
        return { ok: false, hasToken: true, unreachable: true };
      }
    },
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
      // 默认 true：读一个岗位就导入一个，直接落到工作台，不用再去岗位库点「导入」
      const wantMission = message.import_to_mission === undefined ? true : Boolean(message.import_to_mission);
      const result = await callApi("/api/v1/extension/job-import/save", {
        method: "POST",
        body: JSON.stringify({
          draft: message.draft,
          update_duplicates: Boolean(message.update_duplicates),
          import_to_mission: wantMission,
        }),
      });
      // 自愈：旧版后端会忽略 import_to_mission，只把岗位留在候选草稿里
      // （表现就是「导入成功但工作台看不到」）。这时扩展自己再走一步候选导入，
      // 这样即使本机服务还没重启到新版后端，也能直接进工作台。
      const candidateId = result && result.candidate_id;
      if (wantMission && candidateId && !result.mission_id && !result.mission_error) {
        try {
          const imported = await callApi(`/api/v1/candidate-jobs/${candidateId}/import`, { method: "POST" });
          result.mission_id = imported && imported.mission_id;
          result.mission_reused = imported && imported.reused;
          result.imported_by_extension = true;
        } catch (error) {
          result.mission_error = error instanceof Error ? error.message : String(error);
        }
      }
      return result;
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
