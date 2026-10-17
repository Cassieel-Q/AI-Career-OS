/**
 * 页面内容抽取（在用户点击扩展图标后、由 activeTab 临时授权注入）。
 *
 * 硬边界：
 * 1. 只读取页面上**已经显示出来**的可见文本（innerText），不读 Cookie / localStorage /
 *    输入框（尤其不读 password）/ 聊天内容 / 任何隐藏接口返回；
 * 2. 只做 DOM 读取，不模拟点击、不绕过登录、不改页面；
 * 3. 选择器命中不了时降级为「整页可见文本」，并如实把置信度标成 LOW，
 *    由后端继续解析；绝不因为读不到就编造字段。
 *
 * v1.2.0：支持 BOSS「推荐流双栏布局」——左侧职位列表 + 右侧详情面板，
 * 点职位卡片时网址不变（仍是 /web/geek/jobs），详情直接在右侧展开。
 * 此时直接从右侧详情面板抽取，不再要求网址跳到 /job_detail/。
 */

/**
 * 整个文件包在 IIFE 里：顶层不允许出现 const/let，否则同一文档内第二次注入会
 * 触发 SyntaxError「Identifier has already been declared」——那时 executeScript
 * 依然报成功、result 依然是 null，但脚本一行都不会执行（v1.3.1 修的就是这个）。
 */
(function () {
  /** 与 background.js 约定：抽取结果写在这个 DOM 属性上，供回读。 */
  const CAPTURE_ATTR = "data-ai-career-capture";

  /** 只取可见文本：跳过 script/style/隐藏节点与表单控件。 */
  function visibleText(el) {
    if (!el) return "";
    const node = el.body || el; // Document 节点的 textContent 是 null，落到 body
    const clone = node.cloneNode(true);
    clone.querySelectorAll("script,style,noscript,input,textarea,select,button").forEach((node) => node.remove());
    return (clone.textContent || "").replace(/\u00a0/g, " ").replace(/[ \t]+/g, " ").trim();
  }

  function firstText(selectors, root) {
    const host = root || document;
    for (const selector of selectors) {
      try {
        const el = host.querySelector(selector);
        const text = visibleText(el);
        if (text) return { text, selector };
      } catch (_) {
        /* 选择器不合法就跳过 */
      }
    }
    return null;
  }

  /** BOSS 职位页：岗位名 / 薪资 / 城市 / 经验 / 学历 的常见类名。 */
  const FIELD_SELECTORS = {
    role: [
      ".job-banner .name h1",
      ".job-banner .name",
      ".job-primary .name h1",
      ".info-primary .name h1",
      ".job-detail .name h1",
      ".job-detail .name",
      ".job-name",
      ".job-title",
      ".position-name",
      "h1.job-title",
      "[class*='job-title']",
      "h1",
    ],
    salary: [
      ".job-banner .salary",
      ".job-primary .salary",
      ".info-primary .salary",
      ".name .salary",
      ".job-detail .salary",
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

  /** 职位描述区块的标志词。 */
  const JD_KEYWORDS = ["职位描述", "岗位职责", "工作职责", "任职要求", "岗位要求"];

  const CITY_RE =
    /^(北京|上海|广州|深圳|杭州|南京|成都|武汉|西安|苏州|重庆|天津|长沙|郑州|青岛|合肥|济南|宁波|福州|厦门|无锡|大连|沈阳|哈尔滨|长春|昆明|贵阳|南宁|太原|石家庄|兰州|南昌|常州|温州|佛山|东莞|珠海|中山|惠州|嘉兴|绍兴|金华|台州|扬州|南通|徐州|泉州|洛阳|烟台|潍坊|海外|远程|全国)/;

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

  /** BOSS 的推荐流 / 搜索结果等「列表型」网址（可能同时带右侧详情面板）。 */
  function isBossStreamPath() {
    const host = (location.hostname || "").toLowerCase();
    if (!host.includes("zhipin.com")) return false;
    const path = location.pathname || "";
    return /^\/web\/(geek|student)\/(jobs|recommend|position)/.test(path);
  }

  /**
   * 找「右侧详情面板」：一个包含真实 JD 内容（够长 + 有描述标志词）的容器，
   * 且不能把左侧职位列表整块包进来（用职位卡片数量做判据）。
   */
  function findDetailScope() {
    const candidates = [];
    const seen = new Set();
    const scopeSelectors = [
      ".job-detail",
      ".job-detail-main",
      "[class*='job-detail-sections']",
      "[class*='job-detail']",
      ".detail-content",
      "[class*='detail-content']",
    ];
    for (const selector of scopeSelectors) {
      let nodes;
      try {
        nodes = document.querySelectorAll(selector);
      } catch (_) {
        continue;
      }
      for (const node of nodes) {
        if (!seen.has(node)) {
          seen.add(node);
          candidates.push(node);
        }
      }
    }
    // 兜底：从「职位描述」标题往上找一个足够大的容器
    if (!candidates.length) {
      for (const heading of document.querySelectorAll("h2, h3, [class*='sec-title'], [class*='detail-title']")) {
        const text = (heading.textContent || "").trim();
        if (!JD_KEYWORDS.includes(text)) continue;
        let el = heading;
        for (let i = 0; i < 5 && el.parentElement; i++) {
          el = el.parentElement;
          if (visibleText(el).length >= 200) {
            candidates.push(el);
            break;
          }
        }
      }
    }

    let best = null;
    let bestLen = 0;
    for (const node of candidates) {
      const text = visibleText(node);
      if (text.length < 120) continue; // 太小，不像 JD 正文
      const hasJdMark = JD_KEYWORDS.some((keyword) => text.includes(keyword));
      if (!hasJdMark && text.length < 400) continue;
      // 左侧列表的包裹容器会带上很多职位卡片，必须排除
      let cardCount = 0;
      try {
        cardCount = node.querySelectorAll("[class*='job-card'], [class*='job-primary'], [class*='job-list'] li").length;
      } catch (_) {
        /* ignore */
      }
      if (cardCount > 3) continue;
      if (text.length > bestLen && text.length < 30000) {
        best = node;
        bestLen = text.length;
      }
    }
    return best;
  }

  /** 从标题「岗位-公司-城市-招聘-BOSS直聘」里取岗位与公司（仅作兜底，置信度 LOW）。 */
  function roleCompanyFromTitle() {
    const raw = (document.title || "").trim();
    const parts = raw.split(/[-–—|]/).map((part) => part.trim()).filter(Boolean);
    if (parts.length < 2) return null;
    const role = parts[0] && parts[0].length >= 2 ? parts[0] : "";
    const company = parts[1] && parts[1].length >= 2 ? parts[1] : "";
    if (!role && !company) return null;
    return { role, company };
  }

  /**
   * BOSS 页面噪声清理（v1.3.3，真实页面实测发现的两类污染）：
   * 1. 反爬零宽字符（肉眼不可见，会污染后续 AI 解析与去重哈希）；
   * 2. 正文里被随机插入的站点水印「BOSS直聘」——真实页面出现
   *    「紧BOSS直聘追全球AI模型」这类句子，删掉水印后才是「紧跟全球AI模型」；
   * 3. 详情面板动作条带出来的噪声词（收藏 / 立即沟通 / 举报 / 微信扫码分享 /
   *    不适合职位描述）——「立即沟通」等词在任何位置都移除（正常 JD 几乎不会
   *   出现），「收藏 / 举报 / 分享」只作为独立顿号/逗号分隔的词移除，避免误伤
   *    正文（例如「收藏品」「举报机制」）。
   * 只删已知噪声，不做任何“聪明”改写；站点名可能被 JD 正常提及，
   * 因此仅当 site === BOSS_ZHIPIN 时调用。
   */
  const INVISIBLE_RE = /[\u200b-\u200f\u202a-\u202e\u2060\ufeff]/g;
  const WATERMARK_RE = /BOSS\s*直聘/g;
  const ANYWHERE_NOISE_RE = /立即沟通|继续沟通|微信扫码分享|扫码分享|不适合职位描述/g;
  const TOKEN_NOISE_RE = /(^|[,，、;；])\s*(?:收藏|举报|分享)\s*(?=[,，、;；]|$)/g;

  function cleanBossNoise(text) {
    let value = String(text || "")
      .replace(INVISIBLE_RE, "")
      .replace(WATERMARK_RE, "")
      .replace(ANYWHERE_NOISE_RE, "");
    // 独立噪声词可能连续出现（如「…,收藏,举报,分享,」），循环剥到不再变化
    for (let i = 0; i < 5; i++) {
      const next = value.replace(TOKEN_NOISE_RE, "$1");
      if (next === value) break;
      value = next;
    }
    // 删词后残留的连续逗号折叠成一个
    return value.replace(/([,，、;；])[\s,，、;；]+/g, "$1").trim();
  }

  /** 从一段可见文本里切出 城市 / 经验 / 学历。 */
  function parseInfoLine(raw) {
    let locationText = "";
    let experienceText = "";
    let educationText = "";
    if (!raw) return { locationText, experienceText, educationText };
    const parts = raw.split(/[\s/|｜·]+/).filter(Boolean);
    for (const part of parts) {
      if (!locationText && CITY_RE.test(part)) locationText = part;
      if (!experienceText && /(经验|应届|在校|\d+\s*年)/.test(part)) experienceText = part;
      if (!educationText && /(博士|硕士|研究生|本科|大专|专科|高中|中专|学历不限|不限学历)/.test(part)) educationText = part;
    }
    return { locationText, experienceText, educationText };
  }

  /** 真实职位链接：详情面板内 → 被选中的职位卡片 → 岗位名匹配的卡片 → 页面第一条。 */
  function findJobUrl(scope, roleText) {
    const roots = [];
    if (scope !== document) roots.push(scope);
    const activeCard = document.querySelector(
      "[class*='job-card'][class*='active'], [class*='job-card'][class*='current'], [class*='job-card'][class*='selected']",
    );
    if (activeCard) roots.push(activeCard);
    if (roleText) {
      const needle = roleText.slice(0, 12);
      for (const card of document.querySelectorAll("[class*='job-card']")) {
        if (visibleText(card).includes(needle)) {
          roots.push(card);
          break;
        }
      }
    }
    roots.push(document);
    for (const root of roots) {
      let links = [];
      try {
        links = root.querySelectorAll("a[href*='/job_detail/']");
      } catch (_) {
        /* ignore */
      }
      for (const link of links) {
        const href = link.getAttribute("href") || "";
        if (!href) continue;
        try {
          return new URL(href, location.href).toString();
        } catch (_) {
          /* ignore */
        }
      }
    }
    return "";
  }

  /** 读取失败时的页面自诊信息：帮助远程定位真实站点的 DOM 结构差异。 */
  function pageProbe() {
    const count = (selector) => {
      try {
        return document.querySelectorAll(selector).length;
      } catch (_) {
        return -1;
      }
    };
    const bodyText = visibleText(document);
    return {
      detail_node: count("[class*='job-detail']"),
      sec_text: count(".job-sec-text, [class*='sec-text']"),
      job_card: count("[class*='job-card']"),
      job_banner: count("[class*='job-banner']"),
      jd_word: JD_KEYWORDS.some((keyword) => bodyText.includes(keyword)),
      body_len: bodyText.length,
    };
  }

  function extractJobCore() {
    const site = detectSite();
    const isJobPage = looksLikeJobPage();
    // 双栏推荐流：右侧详情面板（存在时优先作为抽取根节点，避免命中左侧卡片）
    const detailScope = findDetailScope();
    const streamWithDetail = !isJobPage && isBossStreamPath() ? detailScope : null;

    // 列表型网址且右侧**没有**展开详情：如实告知怎么走，不去猜用户要点哪个职位
    if (!isJobPage && !detailScope && (isBossStreamPath() || looksLikeBossListPage())) {
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
        job_url: "",
        probe: pageProbe(),
        note: "还没有打开具体职位：请在左侧职位列表里点一个职位卡片，右侧会展开职位详情，然后再点「读取当前岗位」。",
      };
    }

    // 抽取根节点：有详情面板就用它；经典详情页用整页
    const scope = detailScope || document;
    const picked = {};
    const confidence = {};
    const usedSelectors = {};
    for (const [field, selectors] of Object.entries(FIELD_SELECTORS)) {
      const hit = firstText(selectors, scope) || (scope !== document ? firstText(selectors) : null);
      if (hit && hit.text) {
        picked[field] = hit.text;
        usedSelectors[field] = hit.selector;
        confidence[field] = field === "jd" ? "MEDIUM" : "HIGH";
      } else {
        picked[field] = "";
        confidence[field] = "MISSING";
      }
    }

    // 信息栏（城市/经验/学历）在 BOSS 上常被合并成一行（可能在详情面板外，需回退整页）
    const bannerSelectors = [
      ".job-banner .info-primary p",
      ".job-primary .info-primary p",
      ".job-detail .info-primary p",
      ".job-banner .job-tags",
      ".job-detail .job-tags",
      "[class*='job-tags']",
      ".job-banner .info-primary",
      "[class*='job-banner'] [class*='info']",
      ".job-primary .info-primary",
      ".job-tags",
    ];
    const banner = firstText(bannerSelectors, scope) || (scope !== document ? firstText(bannerSelectors) : null);
    const infoRaw = banner ? banner.text : "";

    let locationText = picked.location;
    let experienceText = "";
    let educationText = "";
    let parsed = parseInfoLine(infoRaw);
    locationText = locationText || parsed.locationText;
    experienceText = parsed.experienceText;
    educationText = parsed.educationText;

    // 兜底：在详情面板正文开头找城市
    if (!locationText && scope !== document) {
      const head = visibleText(scope).slice(0, 300);
      const match = head.match(/(北京|上海|广州|深圳|杭州|南京|成都|武汉|西安)[\s·]*((?:[\u4e00-\u9fa5]{2,6}区?[\s·]*){0,2})?/);
      if (match) locationText = (match[1] + (match[2] || "")).trim();
    }

    // 岗位名 / 公司兜底：页面标题（BOSS 双栏流选中职位后标题通常是「岗位-公司-城市-招聘」）
    if (!picked.role || !picked.company) {
      const fromTitle = roleCompanyFromTitle();
      if (fromTitle) {
        if (!picked.role && fromTitle.role) {
          picked.role = fromTitle.role;
          confidence.role = "LOW";
          usedSelectors.role = "document.title";
        }
        if (!picked.company && fromTitle.company) {
          picked.company = fromTitle.company;
          confidence.company = "LOW";
          usedSelectors.company = "document.title";
        }
      }
    }

  // BOSS 真实页面带反爬水印与动作条噪声，交给后端/AI 前先清掉。
  // 触发条件：站点识别为 BOSS，**或**正文里出现了水印本身（测试页 / 任何携带
  // BOSS 水印的页面都能被清理；其他站点原文不动）。
  const rawScopeText = visibleText(scope).slice(0, 20000);
  const cleanText =
    site === "BOSS_ZHIPIN" || rawScopeText.includes("BOSS直聘")
      ? cleanBossNoise
      : (text) => String(text || "");
  const bodyText = cleanText(rawScopeText);
  const jdText = cleanText(picked.jd);

    // 真实职位链接
    const jobUrl = findJobUrl(scope, picked.role);

    const statusOk = isJobPage || Boolean(detailScope);
    let note = "";
    if (detailScope && !isJobPage) note = "已从右侧职位详情面板读取。";
    else if (!statusOk) note = "当前页面看起来不是职位详情页，读取结果可能不完整。";

    return {
      status: statusOk ? "OK" : "NOT_A_JOB_PAGE",
      page_url: location.href,
      page_title: document.title || "",
      job_url: jobUrl,
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
      // 交给后端兜底解析的原文：优先 JD 区块，其次详情面板可见文本
      source_text: jdText || bodyText,
      has_jd_block: Boolean(jdText),
      probe: statusOk ? null : pageProbe(),
      note,
    };
  }

  function looksLikeBossListPage() {
    const host = (location.hostname || "").toLowerCase();
    if (!host.includes("zhipin.com")) return false;
    const path = location.pathname || "";
    if (/job_detail|wejob|position\//.test(path)) return false;
    return Boolean(document.querySelector("[class*='job-card'], [class*='job-list-box'], .job-list, [class*='search-job-result']"));
  }

  function extractJob() {
    try {
      return extractJobCore();
    } catch (error) {
      // 绝不让异常静默：页面内脚本报错时也返回可序列化的诊断结果
      return {
        status: "ERROR",
        page_url: location.href,
        page_title: document.title || "",
        site: "UNKNOWN",
        used_selectors: {},
        provided: { company: "", role: "", location: "", salary_text: "", education: "", experience: "" },
        confidence: {},
        source_text: "",
        has_jd_block: false,
        job_url: "",
        probe: pageProbe(),
        note: "页面读取异常：" + (error && error.message ? error.message : String(error)),
      };
    }
  }

  /** 三条回读通道：DOM 属性（最可靠）/ 隔离世界全局变量 / chrome.storage。 */
  function writeCapture(payload) {
    let raw = "";
    try {
      raw = JSON.stringify(payload);
    } catch (_) {
      raw = JSON.stringify({ status: "ERROR", note: "抽取结果无法序列化。" });
    }
    try {
      document.documentElement.setAttribute(CAPTURE_ATTR, raw);
    } catch (_) {
      /* ignore */
    }
    try {
      window.__AI_CAREER_CAPTURE__ = raw;
    } catch (_) {
      /* ignore */
    }
    try {
      if (typeof chrome !== "undefined" && chrome.storage && chrome.storage.local) {
        chrome.storage.local.set({ aiCareerCapture: raw, aiCareerCaptureAt: Date.now() });
      }
    } catch (_) {
      /* ignore */
    }
    return raw;
  }

  // 关键 1：整个文件包在 IIFE 里 —— 顶层没有任何 const/let 声明，
  //        因此同一文档内重复注入不会触发「Identifier has already been declared」的
  //        SyntaxError（该错误会让 executeScript 报成功但脚本一行都不执行）。
  // 关键 2：把抽取函数挂到 window 上，让 background.js 能用 func 注入调用它。
  //        MV3 只有 func 注入才有返回值，files 注入的 result 恒为 null。
  window.__aiCareerExtract = extractJob;
  try {
    writeCapture(extractJob());
  } catch (_) {
    /* ignore */
  }
})();
