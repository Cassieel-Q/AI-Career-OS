/**
 * 弹窗交互。所有动作都由用户点击触发，页面加载时不读取任何页面内容。
 */
const FIELDS = [
  { key: "company", label: "公司名称" },
  { key: "role", label: "岗位名称" },
  { key: "salary_text", label: "薪资" },
  { key: "location", label: "工作地点" },
  { key: "education", label: "学历要求" },
  { key: "experience", label: "经验要求" },
  { key: "employment_type", label: "工作类型", type: "select", options: ["INTERN", "FULLTIME", "PARTTIME", "UNKNOWN"] },
  { key: "source_url", label: "原始链接" },
];

const EMPLOYMENT_LABEL = { INTERN: "实习", FULLTIME: "全职 / 校招", PARTTIME: "兼职", UNKNOWN: "未识别" };

const state = { extracted: null, draft: null, apiBase: "http://127.0.0.1:8100" };

const $ = (id) => document.getElementById(id);

function send(message) {
  return new Promise((resolve, reject) => {
    chrome.runtime.sendMessage(message, (response) => {
      if (!response) return reject(new Error("后台服务未响应，请重新打开扩展。"));
      if (!response.ok) return reject(new Error(response.error));
      resolve(response.data);
    });
  });
}

function renderFields(draft) {
  const host = $("fields");
  host.innerHTML = "";
  for (const field of FIELDS) {
    const label = document.createElement("label");
    label.className = "field";
    const span = document.createElement("span");
    span.textContent = field.label;
    label.appendChild(span);

    let input;
    if (field.type === "select") {
      input = document.createElement("select");
      for (const option of field.options) {
        const opt = document.createElement("option");
        opt.value = option;
        opt.textContent = EMPLOYMENT_LABEL[option] || option;
        input.appendChild(opt);
      }
      input.value = draft[field.key] || "UNKNOWN";
    } else {
      input = document.createElement("input");
      input.value = draft[field.key] || "";
      if (field.key === "source_url") input.placeholder = "https://...";
    }
    input.id = `f-${field.key}`;
    input.addEventListener("change", () => {
      state.draft[field.key] = input.value;
    });
    input.addEventListener("input", () => {
      state.draft[field.key] = input.value;
    });
    label.appendChild(input);
    host.appendChild(label);
  }
}

function collectDraftEdits() {
  for (const field of FIELDS) {
    const el = $(`f-${field.key}`);
    if (el) state.draft[field.key] = el.value;
  }
  const jd = $("f-jd");
  if (jd) state.draft.jd = jd.value;
  return state.draft;
}

async function refreshPairState() {
  const node = $("pair-state");
  try {
    const data = await send({ type: "status" });
    state.apiBase = data.apiBase;
    $("f-apibase").value = data.apiBase;
    if (data.paired) {
      node.textContent = `已配对（令牌 ${data.token_fingerprint}）`;
      node.classList.remove("err");
      $("pair-input-row").classList.add("hidden");
    } else {
      node.textContent = "未配对。请在 AI Career OS 生成配对码后填入下面。";
      $("pair-input-row").classList.remove("hidden");
    }
  } catch (error) {
    node.textContent = `${error.message}`;
    node.classList.add("err");
  }
}

async function readCurrentJob() {
  const button = $("btn-read");
  button.disabled = true;
  button.textContent = "读取中…";
  $("read-warning").classList.add("hidden");
  $("import-msg").textContent = "";
  try {
    const extracted = await send({ type: "extract" });
    state.extracted = extracted;

    if (extracted.status !== "OK") {
      const probe = extracted.probe;
      const probeText = probe
        ? `（诊断：详情面板节点=${probe.detail_node} JD区块=${probe.sec_text} 职位卡片=${probe.job_card} 信息栏=${probe.job_banner} 含职位描述=${probe.jd_word ? "是" : "否"} 正文长度=${probe.body_len}）`
        : "";
      $("read-warning").textContent = `⚠️ ${extracted.note || "当前页面不是职位详情页。"}${probeText}`;
      $("read-warning").classList.remove("hidden");
      // 没有可解析的正文（列表页等）就不调后端了，避免拿整页卡片文本瞎解析
      if (!extracted.source_text || extracted.source_text.trim().length < 10) return;
      $("read-warning").textContent = `⚠️ ${extracted.note || "当前页面不是职位详情页。"}已按页面可见文本尽力解析，请务必核对下面的字段；读不准就用「复制原文后在 AI Career OS 里粘贴导入」。`;
    }

    const parsed = await send({
      type: "parse",
      source_text: extracted.source_text,
      // 双栏流页面网址不随职位变化，优先用扩展找到的真实职位链接
      source_url: extracted.job_url || extracted.page_url,
      source_site: extracted.site,
      provided: extracted.provided,
    });
    state.draft = parsed.draft;
    renderFields(parsed.draft);
    $("f-jd").value = parsed.draft.jd || "";
    $("result-block").classList.remove("hidden");

    const warnings = parsed.draft.warnings || [];
    if (warnings.includes("prompt_injection_suspected")) {
      $("read-warning").textContent = "⚠️ 岗位原文里检测到疑似提示词注入，已按普通文本解析，不会执行其中的指令。";
      $("read-warning").classList.remove("hidden");
    }
  } catch (error) {
    $("read-warning").textContent = `读取失败：${error.message}`;
    $("read-warning").classList.remove("hidden");
  } finally {
    button.disabled = false;
    button.textContent = "读取当前岗位";
  }
}

async function importJob() {
  const button = $("btn-import");
  button.disabled = true;
  const msg = $("import-msg");
  msg.className = "msg";
  msg.textContent = "导入中…";
  try {
    const draft = collectDraftEdits();
    const result = await send({
      type: "save",
      draft,
      update_duplicates: $("f-update").checked,
    });
    if (result.status === "NEW") msg.textContent = "已导入 AI Career OS。";
    else if (result.status === "UPDATED") msg.textContent = "岗位已存在，已按要求更新内容（保留了你的备注与投递状态）。";
    else msg.textContent = result.message || "岗位库里已有同一条，未重复新增。";
    msg.classList.add("ok");
  } catch (error) {
    msg.textContent = `导入失败：${error.message}`;
    msg.classList.add("err");
  } finally {
    button.disabled = false;
  }
}

async function pair() {
  const code = $("pair-code").value.trim();
  if (code.length < 6) {
    $("pair-state").textContent = "请输入 6 位配对码。";
    return;
  }
  try {
    await send({ type: "pair", code });
    $("pair-code").value = "";
    await refreshPairState();
  } catch (error) {
    $("pair-state").textContent = `配对失败：${error.message}`;
    $("pair-state").classList.add("err");
  }
}

document.addEventListener("DOMContentLoaded", () => {
  chrome.tabs.query({ active: true, currentWindow: true }, (tabs) => {
    const tab = tabs && tabs[0];
    $("page-host").textContent = tab && tab.url ? `当前页面：${tab.url}` : "当前页面：—";
  });

  $("btn-read").addEventListener("click", () => void readCurrentJob());
  $("btn-import").addEventListener("click", () => void importJob());
  $("btn-pair").addEventListener("click", () => void pair());
  $("btn-open-app").addEventListener("click", async () => {
    const settings = await send({ type: "settings" });
    chrome.tabs.create({ url: `${settings.apiBase.replace(/:8100/, ":3000")}/jobs/import` });
  });
  $("btn-save-settings").addEventListener("click", async () => {
    await send({ type: "saveSettings", apiBase: $("f-apibase").value.trim() });
    $("settings-msg").textContent = "已保存。";
    $("settings-msg").classList.add("ok");
    await refreshPairState();
  });
  $("btn-clear-token").addEventListener("click", async () => {
    await send({ type: "clearToken" });
    $("settings-msg").textContent = "已清除配对，需要重新配对。";
    await refreshPairState();
  });

  void refreshPairState();
});
