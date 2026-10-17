/**
 * 页面内容抽取（在用户点击扩展图标后、由 activeTab 临时授权注入）。
 *
 * 硬边界：
 * 1. 只读取页面上**已经显示出来**的可见文本（innerText），不读 Cookie / localStorage /
 *    输入框（尤其不读 password）/ 聊天内容 / 任何隐藏接口返回；
 * 2. 只做 DOM 读取，不模拟点击、不绕过登录、不改页面；
 * 3. 选择器命中不了时降级为「整页可见文本」，并如实把置信度标成 LOW，
 *    由后端继续解析；绝不因为读不到就编造字段。
 */

/** 只取可见文本：跳过 script/style/隐藏节点与表单控件。 */
function visibleText(el) {
  if (!el) return "";
  const clone = el.cloneNode(true);
  clone.querySelectorAll("script,style,noscript,input,textarea,select,button").forEach((node) => node.remove());
  return (clone.textContent || "").replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").trim();
}

function firstText(selectors) {
  for (const selector of selectors) {
    try {
      const el = document.querySelector(selector);
      const text = visibleText(el);
      if (text) return { text, selector };
    } catch (_) {
      /* 选择器不合法就跳过 */
    }
  }
  return null;
}

/** BOSS 直聘职位详情页：岗位名 / 薪资 / 城市 / 经验 / 学历 常在同一条信息栏里。 */
const FIELD_SELECTORS = {
  role: [
    ".job-banner .name h1",
    ".job-banner .name",
    ".job-primary .name h1",
    ".info-primary .name h1",
    ".job-title",
    ".position-name",
    "h1.job-title",
    "[class*='job-title']",
    ".job-name",
    "h1",
  ],
  salary: [
    ".job-banner .salary",
    ".job-primary .salary",
    ".info-primary .salary",
    ".name .salary",
    ".salary",
    ".job-salary",
    "[class*='salary']",
    "[class*='Salary']",
  ],
  company: [
    ".job-sider .company",
    ".job-sider .company a",
    ".company-info .name",
    ".sider-company .name",
    ".job-company .name",
    ".company-name",
    "[class*='company-name']",
    ".boss-name",
    "[class*='companyName']",
  ],
  location: [
    ".job-banner .location-address",
    ".job-primary .location-address",
    ".job-location",
    "[class*='job-location']",
    ".location-address",
    "[class*='city']",
  ],
  jd: [
    ".job-sec .job-sec-text",
    ".job-sec-text",
    ".job-detail-section",
    ".detail-content",
    "[class*='job-detail']",
    "[class*='jobDetail']",
    "[class*='job-desc']",
  ],
};

function detectSite(hostname) {
  const host = (hostname || location.hostname || "").toLowerCase();
  if (host.includes("zhipin.com")) return "BOSS_ZHIPIN";
  if (host.includes("shixiseng.com")) return "OTHER";
  if (host.includes("liepin.com") || host.includes("lagou.com") || host.includes("51job.com")) return "OTHER";
  return "UNKNOWN";
}

function looksLikeJobPage() {
  const path = (location.pathname || "").toLowerCase();
  const host = (location.hostname || "").toLowerCase();
  if (host.includes("zhipin.com")) {
    return /job_detail|wejob|position|jobcard|job_detail\?/.test(path) || Boolean(document.querySelector("[class*='job-detail'],[class*='jobDetail'],.job-banner"));
  }
  // 其他站点：只要有明显的岗位标题 + JD 区块就算
  return Boolean(firstText(FIELD_SELECTORS.role) && firstText(FIELD_SELECTORS.jd));
}

/** BOSS 的推荐流 / 搜索结果等「列表页」：一页里有很多职位，没法替用户挑。 */
function looksLikeBossListPage() {
  const host = (location.hostname || "").toLowerCase();
  if (!host.includes("zhipin.com")) return false;
  const path = location.pathname || "";
  if (/^\/web\/(geek|student)\/(jobs|recommend|position)/.test(path)) return true;
  if (/job_detail|wejob|position\//.test(path)) return false;
  return Boolean(document.querySelector("[class*='job-card'], [class*='job-list-box'], .job-list, [class*='search-job-result']"));
}

function extractJob() {
  const site = detectSite();
  const isJobPage = looksLikeJobPage();

  // 列表页直接如实告知怎么走，不去猜用户要点哪个职位（猜了就会导入错岗位）
  if (!isJobPage && looksLikeBossListPage()) {
    return {
      status: "NOT_A_JOB_PAGE",
      page_url: location.href,
      page_title: document.title || "",
      site,
      used_selectors: {},
      provided: { company: "", role: "", location: "", salary_text: "", education: "", experience: "" },
      confidence: {},
      source_text: "",
      has_jd_block: false,
      note: "这是 BOSS 的职位「列表页」（推荐/搜索结果）。请点进一个具体职位，等网址变成包含 /job_detail/ 的详情页，再点「读取当前岗位」。",
    };
  }

  const picked = {};
  const confidence = {};
  const usedSelectors = {};
  for (const [field, selectors] of Object.entries(FIELD_SELECTORS)) {
    const hit = firstText(selectors);
    if (hit && hit.text) {
      picked[field] = hit.text;
      usedSelectors[field] = hit.selector;
      confidence[field] = field === "jd" ? "MEDIUM" : "HIGH";
    } else {
      picked[field] = "";
      confidence[field] = "MISSING";
    }
  }

  // 信息栏（城市/经验/学历）在 BOSS 上常被合并成一行，这里按可见文本切一下
  let locationText = picked.location;
  let experienceText = "";
  let educationText = "";
  const banner = document.querySelector(
    ".job-banner .info-primary p, .job-primary .info-primary p, .job-banner .job-tags, " +
      ".job-banner .info-primary, [class*='job-banner'] [class*='info'], .job-primary .info-primary, .job-tags"
  );
  if (banner) {
    const raw = visibleText(banner);
    if (raw) {
      const parts = raw.split(/[\s/|｜]+/).filter(Boolean);
      for (const part of parts) {
        if (!locationText && /^(北京|上海|广州|深圳|杭州|南京|成都|武汉|西安|苏州|重庆|天津|长沙|郑州|青岛|合肥|济南|宁波|福州|厦门|无锡|大连|沈阳|哈尔滨|长春|昆明|贵阳|南宁|太原|石家庄|兰州|南昌|常州|温州|佛山|东莞|珠海|中山|惠州|嘉兴|绍兴|金华|台州|扬州|南通|徐州|泉州|洛阳|烟台|潍坊|海外|远程|全国)/.test(part)) {
          locationText = part;
        }
        if (!experienceText && /(经验|应届|在校|\d+\s*年)/.test(part)) experienceText = part;
        if (!educationText && /(博士|硕士|研究生|本科|大专|专科|高中|中专|学历不限|不限学历)/.test(part)) educationText = part;
      }
    }
  }

  const bodyText = visibleText(document.body).slice(0, 20000);
  const jdText = picked.jd || "";

  return {
    status: isJobPage ? "OK" : "NOT_A_JOB_PAGE",
    page_url: location.href,
    page_title: document.title || "",
    site,
    used_selectors: usedSelectors,
    provided: {
      company: picked.company,
      role: picked.role,
      location: locationText,
      salary_text: picked.salary,
      education: educationText,
      experience: experienceText,
    },
    confidence,
    // 交给后端兜底解析的原文：优先 JD 区块，其次整页可见文本
    source_text: jdText || bodyText,
    has_jd_block: Boolean(jdText),
    note: isJobPage ? "" : "当前页面看起来不是职位详情页，读取结果可能不完整。",
  };
}

// executeScript 的返回值就是最后一个表达式的值
extractJob();
