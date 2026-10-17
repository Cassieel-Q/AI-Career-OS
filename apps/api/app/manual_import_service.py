"""手动导入岗位的解析服务（BOSS 直聘等中文招聘平台的复制文本 / 页面文本）。

设计原则（对应补充任务 M2）：
1. **只在原文里找证据**：所有字段都必须能在原文中定位；找不到就留空并给出 warnings，
   绝不用模型或常识「补一个像样的公司名 / 岗位名」。
2. **来源字段优先**：调用方（例如浏览器扩展从 DOM 里读到的字段）显式给了值的字段，
   不再用启发式结果覆盖 —— 避免此前「JD 首行被切成公司/岗位」的错误。
3. **可回溯**：保留清洗后的原文，结构化字段标记为 evidence，前端可高亮来源。
4. **安全**：输入先做 HTML 剥离；检测到提示词注入只**标记告警**，不改变解析逻辑，
   也不会把注入内容当作指令执行。
5. **合成数据不得冒充真实采集**：本模块只解析用户提供的文本，source_site 由调用方声明。
"""
from __future__ import annotations

import html
import re
from datetime import datetime, timezone

from .job_ingest_service import content_hash, dedupe_key, detect_employment_type

SOURCE_SITES = {"BOSS_ZHIPIN", "OTHER", "UNKNOWN"}
RECOGNITION = {"MANUAL_PASTE", "BROWSER_EXTENSION", "HEURISTIC"}

#: 文本长度上限：浏览器扩展 / 粘贴内容超过这个长度直接拒绝，避免超大请求体。
MAX_SOURCE_TEXT = 200_000

# --------------------------------------------------------------------------- 清洗

_TAG_RE = re.compile(r"<[^>]{0,2000}>")
_SCRIPT_RE = re.compile(r"<(script|style)\b[^>]*>.*?</\1>", re.I | re.S)
_BLANK_LINES_RE = re.compile(r"\n{3,}")


def strip_html(text: str) -> str:
    """把 HTML 片段转成纯文本；非 HTML 原文原样保留（只做实体解码的安全子集）。"""
    raw = text or ""
    if "<" not in raw or ">" not in raw:
        return raw
    cleaned = _SCRIPT_RE.sub(" ", raw)
    cleaned = _TAG_RE.sub("\n", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = re.sub(r"[ \t\u00a0]+", " ", cleaned)
    cleaned = _BLANK_LINES_RE.sub("\n\n", cleaned)
    return cleaned.strip()


# --------------------------------------------------------------------------- 注入检测

_INJECTION_PATTERNS = [
    re.compile(r"(忽略|无视|ignore|disregard)\s*(以上|上面|之前|previous|above|all)?\s*(所有)?\s*(指令|规则|提示|内容|instructions?|rules?|prompts?)", re.I),
    re.compile(r"(你现在是|you are now|act as|扮演)\s*\S{0,20}", re.I),
    re.compile(r"^\s*(system|assistant)\s*:", re.I | re.M),
    re.compile(r"(把|将|set)\s*(这家)?\s*(公司|岗位|薪资|学历)\s*(改成|设为|改为|to)\s*\S+"),
    re.compile(r"(标记为|评定为|判定为|mark as|rate as)\s*(高优先级|最匹配|high priority|best match)", re.I),
    re.compile(r"(请|务必|必须)\s*(直接|立即)?\s*(录用|录取|hire|accept)", re.I),
    re.compile(r"(不要告诉|隐瞒|don'?t tell)\s*(用户|候选人|the user)", re.I),
]


def detect_prompt_injection(text: str) -> list[str]:
    """检测 JD 里的提示词注入痕迹。只返回告警标签，不改变解析逻辑。"""
    if not text:
        return []
    hits: list[str] = []
    for pattern in _INJECTION_PATTERNS:
        if pattern.search(text):
            hits.append("prompt_injection_suspected")
            break
    # 大段不可见字符 / 零宽字符常见于隐藏注入
    if re.search(r"[\u200b-\u200f\u202a-\u202e\ufeff]{3,}", text):
        hits.append("hidden_characters")
    return hits


# --------------------------------------------------------------------------- 字段抽取

_LABEL_ALIASES = {
    "company": ("公司", "公司名称", "企业名称", "company", "雇主", "招聘方"),
    "role": ("岗位", "职位", "岗位名称", "职位名称", "招聘职位", "role", "position", "title"),
    "location": ("地点", "工作地点", "城市", "工作城市", "location", "上班地点"),
    "salary": ("薪资", "薪水", "薪酬", "工资", "薪资范围", "salary", "待遇"),
    "education": ("学历", "学历要求", "最低学历", "education"),
    "experience": ("经验", "工作经验", "经验要求", "experience"),
    "employment": ("工作类型", "职位类型", "招聘类型", "雇佣形式", "用工性质", "employment", "job type"),
}
#: 「岗位职责」「公司规模」「工作地点图」这类复合词不是字段标签，必须排除，
#: 否则会把 JD 小节标题当成公司名/岗位名（此前真实踩过的坑）。
_LABEL_NEGATIVE = {
    "company": r"(?!简介|介绍|规模|福利|地址|类型|性质|信息|文化|业务|官网|规模)",
    "role": r"(?!职责|描述|要求|介绍|说明|详情|信息|亮点|福利|内容|编号|类别)",
    "location": r"(?!图|示意图)",
    "salary": r"(?!待遇说明|范围说明)",
    "education": r"(?!要求说明)",
    "experience": r"(?!要求说明)",
    "employment": r"(?!说明)",
}

_LABEL_RE_CACHE: dict[str, re.Pattern[str]] = {}


def _label_regex(field: str) -> re.Pattern[str]:
    if field not in _LABEL_RE_CACHE:
        # 长别名优先，否则「公司名称」会先被「公司」吃掉，值变成「名称：xxx」
        aliases = "|".join(re.escape(a) for a in sorted(_LABEL_ALIASES[field], key=len, reverse=True))
        negative = _LABEL_NEGATIVE.get(field, "")
        # 支持 【岗位】xxx / 岗位：xxx / 岗位 xxx
        _LABEL_RE_CACHE[field] = re.compile(
            rf"(?:【|\[|<)?\s*(?:{aliases}){negative}\s*(?:】|\]|>|:|：)?\s*[:：]?\s*(?P<value>[^\n\r]{{1,120}})"
        )
    return _LABEL_RE_CACHE[field]


_CITY_LIST = [
    "北京", "上海", "广州", "深圳", "杭州", "南京", "成都", "武汉", "西安", "苏州",
    "重庆", "天津", "长沙", "郑州", "青岛", "合肥", "济南", "宁波", "福州", "厦门",
    "无锡", "大连", "沈阳", "哈尔滨", "长春", "昆明", "贵阳", "南宁", "太原", "石家庄",
    "兰州", "南昌", "常州", "温州", "佛山", "东莞", "珠海", "中山", "惠州", "嘉兴",
    "绍兴", "金华", "台州", "扬州", "南通", "徐州", "泉州", "洛阳", "烟台", "潍坊",
    "中国香港", "香港", "中国台湾", "台北", "中国澳门", "澳门", "海外", "远程", "全国",
]
_CITY_RE = re.compile(r"(" + "|".join(_CITY_LIST) + r")(?:[\s·•・\-,，、]+([\u4e00-\u9fff]{2,8}(?:区|县|市|镇|新区|园区|开发区)?))?")

_SALARY_RE = re.compile(
    r"(?<![\d.])"
    r"(?:\d{1,3}(?:\.\d+)?\s*[-~—－至到]\s*\d{1,3}(?:\.\d+)?|\d{1,4}(?:\.\d+)?)"
    r"\s*(?:[kK千]|[wW万]|元|块)"
    r"(?:\s*[·•xX*×]\s*(?:1[0-9]|[1-9])\s*薪)?"
    r"(?:\s*/\s*(?:月|年|天|周|小时|时))?"
)
_SALARY_NEGOTIABLE_RE = re.compile(r"(薪资?\s*面议|待遇?\s*面议|面议)")

_EDUCATION_RE = re.compile(r"(博士|硕士研究生|硕士|研究生|本科|大学本科|统招本科|大专|专科|高中|中专|中职|学历不限|不限学历)")
_EXPERIENCE_RE = re.compile(
    r"(在校/?应届|应届生|应届毕业生|在校生|实习生|经验不限|不限经验|经验?\s*不限|不限\s*经验|无经验要求|无经验|"
    r"\d+\s*年\s*(?:以上|以下)?|\d+\s*[-~至]\s*\d+\s*年)"
)
_EMPLOYMENT_MAP = [
    (re.compile(r"实习|见习|intern|trainee", re.I), "INTERN"),
    (re.compile(r"兼职|part-?time", re.I), "PARTTIME"),
    (re.compile(r"全职|正式|社招|校招|全职员工|full-?time", re.I), "FULLTIME"),
]

_TITLE_HINT_RE = re.compile(
    r"(产品经理|产品|项目经理|项目|运营|开发|工程师|算法|数据分析|数据|设计|测试|销售|市场|"
    r"人力|HR|财务|法务|行政|实习生|助理|专员|主管|经理|总监|架构师|研究员|分析师|顾问|"
    r"编辑|文案|客服|供应链|采购|实施|咨询|AI|AIGC|NLP|LLM|大模型|增长|商业分析|战略|投资|"
    r"研发|前端|后端|客户端|客户端开发|运维|安全|QA|UI|UX)"
)
_COMPANY_SUFFIX_RE = re.compile(
    r"([\u4e00-\u9fffA-Za-z0-9()（）·&\-]{2,40}?"
    r"(?:股份有限公司|有限责任公司|有限公司|集团公司|集团|科技公司|网络科技公司|信息技术有限公司|"
    r"Inc\.|Inc|Ltd\.?|LLC|GmbH|Corp\.?|Limited))"
)
_URL_RE = re.compile(r"https?://[^\s，,；;）)】\]]+")
#: BOSS 等站点首行常见「招聘产品经理/诚聘 XX」，岗位名里不应保留这些前缀
_ROLE_PREFIX_RE = re.compile(r"^\s*(?:诚聘|急招|急聘|热招|长期招聘|招聘|诚招|招)\s*")


def _first_match(pattern: re.Pattern[str], text: str) -> str:
    match = pattern.search(text or "")
    return match.group(0).strip() if match else ""


#: 薪资 / 学历 / 经验是短字段：整行里按已知取值集合规范化，避免把行尾杂项吃进来。
_SHORT_FIELD_NORMALIZER = {
    "salary": _SALARY_RE,
    "education": _EDUCATION_RE,
    "experience": _EXPERIENCE_RE,
}
#: 行首允许出现的列表符号 / 编号，去掉后再判断标签是否在行首。
_LINE_PREFIX_RE = re.compile(r"^[\s\-*·•>＞\d\.、）)\]】]+")


def _labeled_value(field: str, lines: list[str]) -> str:
    """在带标签的行里取值（「公司：xxx」/「【公司】xxx」）。"""
    regex = _label_regex(field)
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        probe = _LINE_PREFIX_RE.sub("", stripped)
        match = regex.search(probe)
        if not match:
            continue
        # 标签必须就在行首，避免把 JD 正文里出现的「公司：」当成字段
        if match.start() > 2:
            continue
        value = match.group("value").strip(" 　\t【】[]<>")
        normalizer = _SHORT_FIELD_NORMALIZER.get(field)
        if normalizer is not None:
            # 在这一行里按已知取值集合重新定位，取到的才是规范化后的短值
            narrowed = normalizer.search(probe)
            if not narrowed:
                continue
            value = narrowed.group(0).strip()
        return value
    return ""


def _guess_company(lines: list[str], text: str) -> str:
    match = _COMPANY_SUFFIX_RE.search(text)
    if match:
        return match.group(1).strip()
    # BOSS 详情页：公司名常单独成行，且不带 JD 常见的标点
    for line in lines[:6] + lines[-6:]:
        candidate = line.strip()
        if not candidate or len(candidate) > 40:
            continue
        if _SALARY_RE.search(candidate) or _CITY_RE.search(candidate):
            continue
        if _TITLE_HINT_RE.search(candidate) and not _COMPANY_SUFFIX_RE.search(candidate):
            continue
        if re.fullmatch(r"[\u4e00-\u9fffA-Za-z0-9()（）·&\-\s]{2,40}", candidate) and (
            _COMPANY_SUFFIX_RE.search(candidate) or candidate.endswith("公司")
        ):
            return candidate
    return ""


def _guess_role(lines: list[str]) -> str:
    """BOSS 详情页首行通常是岗位名；只有看起来像岗位名才采用。"""
    for line in lines[:3]:
        candidate = _ROLE_PREFIX_RE.sub("", line.strip()).strip().lstrip("【[").rstrip("】]")
        if not candidate or len(candidate) > 40:
            continue
        if _SALARY_RE.fullmatch(candidate) or _SALARY_RE.search(candidate):
            continue
        if re.fullmatch(r"[\d\s\-~Kk千万元/月年天]+", candidate):
            continue
        if _EDUCATION_RE.fullmatch(candidate) or _EXPERIENCE_RE.fullmatch(candidate):
            continue
        if _COMPANY_SUFFIX_RE.search(candidate):
            continue
        if _TITLE_HINT_RE.search(candidate):
            return candidate
        # 短且不像公司/薪资/地点，也当作岗位名（BOSS 首行）
        if 2 <= len(candidate) <= 20 and not _CITY_RE.search(candidate):
            return candidate
    return ""


def _guess_location(text: str) -> str:
    match = _CITY_RE.search(text)
    if not match:
        return ""
    parts = [p for p in match.groups() if p]
    return " ".join(dict.fromkeys(parts))


def _guess_employment_type(*parts: str | None) -> str:
    haystack = " ".join(p or "" for p in parts)
    for regex, value in _EMPLOYMENT_MAP:
        if regex.search(haystack):
            return value
    return detect_employment_type(*parts)


# --------------------------------------------------------------------------- 主入口


def parse_job_text(
    *,
    source_text: str,
    source_url: str = "",
    source_site: str = "UNKNOWN",
    recognition: str = "MANUAL_PASTE",
    provided: dict | None = None,
) -> dict:
    """把粘贴/页面文本解析成统一岗位草稿。

    ``provided`` 里的字段（来自浏览器扩展 DOM 读取）优先级最高，
    启发式结果只在缺失时补齐，绝不覆盖。
    """
    provided = {k: (v or "").strip() for k, v in (provided or {}).items() if isinstance(v, str) and v.strip()}
    raw = (source_text or "")[:MAX_SOURCE_TEXT]
    cleaned = strip_html(raw)
    lines = [line.strip() for line in cleaned.splitlines()]
    lines = [line for line in lines if line]

    injection = detect_prompt_injection(cleaned)

    company = provided.get("company") or _labeled_value("company", lines) or _guess_company(lines, cleaned)
    # provided / 标签 / 启发式三个来源都可能带「招聘」「诚聘」等前缀，统一在最后剥离
    role = _ROLE_PREFIX_RE.sub("", (provided.get("role") or _labeled_value("role", lines) or _guess_role(lines))).strip()
    location = provided.get("location") or _labeled_value("location", lines) or _guess_location(cleaned)
    salary = provided.get("salary_text") or _labeled_value("salary", lines) or _first_match(_SALARY_RE, cleaned)
    if not salary:
        salary = "面议" if _SALARY_NEGOTIABLE_RE.search(cleaned) else ""
    education = provided.get("education") or _labeled_value("education", lines) or _first_match(_EDUCATION_RE, cleaned)
    experience = provided.get("experience") or _labeled_value("experience", lines) or _first_match(_EXPERIENCE_RE, cleaned)
    employment = provided.get("employment_type") or _labeled_value("employment", lines) or ""
    employment = employment.upper() if employment in {"INTERN", "FULLTIME", "PARTTIME"} else _guess_employment_type(role, employment, cleaned[:400])
    if employment not in {"INTERN", "FULLTIME", "PARTTIME"}:
        employment = "UNKNOWN"

    url = provided.get("source_url") or source_url or _first_match(_URL_RE, cleaned)

    # JD：保留清洗后的全文，避免丢内容；结构化字段单独给出，不改写原文。
    jd = cleaned

    warnings: list[str] = []
    needs_confirm: list[str] = []
    for field, value in (("company", company), ("role", role), ("location", location), ("jd", jd)):
        if not value:
            warnings.append(f"{field}_missing")
            needs_confirm.append(field)
    if not salary:
        warnings.append("salary_missing")
    if not education:
        warnings.append("education_missing")
    if employment == "UNKNOWN":
        warnings.append("employment_type_unknown")
    warnings.extend(injection)

    confidence = {
        field: ("HIGH" if field in provided else ("MEDIUM" if value else "MISSING"))
        for field, value in (
            ("company", company), ("role", role), ("location", location),
            ("salary", salary), ("education", education), ("experience", experience),
        )
    }

    text = "\n".join(
        part
        for part in [
            f"公司：{company}" if company else None,
            f"职位：{role}" if role else None,
            f"地点：{location}" if location else None,
            f"薪资：{salary}" if salary else None,
            f"学历：{education}" if education else None,
            f"经验：{experience}" if experience else None,
            f"类型：{employment}" if employment != "UNKNOWN" else None,
            "",
            jd,
        ]
        if part is not None
    ).strip()

    site = source_site if source_site in SOURCE_SITES else "UNKNOWN"
    return {
        "schema": "ai-career-os/job@1",
        "source": "manual_import",
        "source_site": site,
        "recognition": recognition if recognition in RECOGNITION else "MANUAL_PASTE",
        "source_url": url[:1024],
        "company": company,
        "role": role,
        "location": location,
        "salary_text": salary,
        "education": education,
        "experience": experience,
        "employment_type": employment,
        "jd": jd,
        "jd_excerpt": jd[:400],
        "collected_at": datetime.now(timezone.utc).isoformat(),
        "dedupe_key": dedupe_key(company, role, location),
        "content_hash": content_hash(role, location, text),
        "needs_confirm": needs_confirm,
        "confidence": confidence,
        "warnings": list(dict.fromkeys(warnings)),
        "text": text,
    }


__all__ = [
    "MAX_SOURCE_TEXT",
    "SOURCE_SITES",
    "detect_prompt_injection",
    "parse_job_text",
    "strip_html",
]
