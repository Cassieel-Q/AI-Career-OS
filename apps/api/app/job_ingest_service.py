"""岗位统一入口：粘贴 / 公开链接 / 文件导入 + 去重 + 来源元数据。

设计边界（严格遵守）：
- 只访问**公开可访问**的页面或**官方公开接口**；
- **不绕过**登录、验证码、付费墙或反爬限制：一旦识别到需要登录/验证，返回
  ``BLOCKED`` 并提示用户手动粘贴，绝不伪造"已真实采集"；
- 采集到的每一条都记录来源 URL、采集时间、原文与解析状态，便于回溯。

真实来源适配器：
- ``generic_url``：用户提供的公开招聘页链接（HTML 正文抽取 / PDF 直链解析）；
- ``remoteok``：RemoteOK 官方公开 JSON 接口（`https://remoteok.com/api`），
  无需登录、条款允许，可直接列出真实在招岗位。
"""

from __future__ import annotations

import hashlib
import html
import re
from datetime import datetime, timezone
from pathlib import Path
from uuid import UUID

import fitz
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

USER_AGENT = "AICareerOS/1.0 (+local-first job collection; contact: local user)"
REMOTEOK_API = "https://remoteok.com/api"

#: 识别到这些标记时判定为「需要登录 / 有访问限制」，不做任何绕过。
_BLOCK_MARKERS = (
    "请先登录",
    "请登录后",
    "登录后查看",
    "验证码",
    "captcha",
    "verify you are human",
    "sign in to continue",
    "login required",
    "access denied",
    "请完成安全验证",
)

_SCRIPT_RE = re.compile(r"<(script|style|noscript)[^>]*>.*?</\1>", re.IGNORECASE | re.DOTALL)
_BLOCK_TAG_RE = re.compile(
    r"</?(p|div|br|li|ul|ol|tr|td|th|h[1-6]|section|article|header|footer|table|blockquote)[^>]*>",
    re.IGNORECASE,
)
_TAG_RE = re.compile(r"<[^>]+>")
_WS_RE = re.compile(r"[ \t\u00a0]+")
_MULTI_NL_RE = re.compile(r"\n{3,}")
_TITLE_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.IGNORECASE | re.DOTALL)


def html_to_text(raw: str) -> str:
    """把 HTML 粗转为可读文本（去掉脚本/样式，块级标签转换行）。"""
    cleaned = _SCRIPT_RE.sub(" ", raw)
    cleaned = _BLOCK_TAG_RE.sub("\n", cleaned)
    cleaned = _TAG_RE.sub(" ", cleaned)
    cleaned = html.unescape(cleaned)
    cleaned = _WS_RE.sub(" ", cleaned)
    lines = [line.strip() for line in cleaned.splitlines()]
    return _MULTI_NL_RE.sub("\n\n", "\n".join(line for line in lines if line))


def extract_pdf_text(blob: bytes) -> str:
    with fitz.open(stream=blob, filetype="pdf") as doc:
        return "\n".join(page.get_text() for page in doc).strip()


def extract_file_text(filename: str, blob: bytes) -> tuple[str, str]:
    """返回 (文本, 解析状态)。图片类不在此做 OCR，明确标记为不支持自动解析。"""
    suffix = Path(filename or "").suffix.lower()
    if suffix == ".pdf":
        text = extract_pdf_text(blob)
        return text, "PARSED" if text.strip() else "PARSE_EMPTY"
    if suffix in {".txt", ".md", ".csv", ".json"}:
        return blob.decode("utf-8", errors="replace"), "PARSED"
    if suffix in {".docx", ".doc"}:
        return _extract_docx(blob)
    if suffix in {".png", ".jpg", ".jpeg", ".webp", ".bmp", ".gif"}:
        return "", "UNSUPPORTED_IMAGE"
    return "", "UNSUPPORTED_TYPE"


def _extract_docx(blob: bytes) -> tuple[str, str]:
    """极简 docx 文本抽取（zip + XML），不引入额外依赖。"""
    import io
    import zipfile

    try:
        with zipfile.ZipFile(io.BytesIO(blob)) as zf:
            xml = zf.read("word/document.xml").decode("utf-8", errors="replace")
    except (KeyError, zipfile.BadZipFile):
        return "", "UNSUPPORTED_TYPE"
    xml = xml.replace("</w:p>", "\n")
    text = _TAG_RE.sub("", xml)
    return html.unescape(text), "PARSED"


def _deem_blocked(text: str) -> bool:
    lowered = text.lower()
    return any(marker.lower() in lowered for marker in _BLOCK_MARKERS) and len(text) < 400


def fetch_url_text(url: str, *, timeout: float = 15.0) -> dict:
    """抓取公开链接正文。返回结构含 status / text / title / note。"""
    parsed = (url or "").strip()
    if not re.match(r"^https?://", parsed, re.IGNORECASE):
        raise HTTPException(422, "请输入以 http:// 或 https:// 开头的公开链接。")

    result = {
        "url": parsed,
        "status": "ERROR",
        "title": "",
        "text": "",
        "content_type": "",
        "note": "",
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }
    try:
        with httpx.Client(
            follow_redirects=True,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        ) as client:
            response = client.get(parsed)
    except httpx.HTTPError as exc:
        result["note"] = f"请求失败：{exc.__class__.__name__}"
        return result

    result["content_type"] = response.headers.get("content-type", "")
    ctype = result["content_type"].lower()

    if response.status_code >= 400:
        result["status"] = "BLOCKED" if response.status_code in {401, 403, 429} else "ERROR"
        result["note"] = f"服务器返回 HTTP {response.status_code}，未做任何绕过。请手动复制正文粘贴。"
        return result

    if "application/pdf" in ctype or parsed.lower().endswith(".pdf"):
        text = extract_pdf_text(response.content)
        result.update(status="PARSED" if text else "PARSE_EMPTY", text=text, note="来自 PDF 直链。")
        return result

    if "application/json" in ctype:
        result.update(status="UNSUPPORTED_PAGE", text="", note="该链接返回 JSON 数据，请改用对应的采集适配器。")
        return result

    raw = response.text
    title_match = _TITLE_RE.search(raw)
    result["title"] = html.unescape(title_match.group(1)).strip() if title_match else ""
    text = html_to_text(raw)
    if _deem_blocked(text):
        result.update(status="BLOCKED", text="", note="页面疑似需要登录或验证码，未做任何绕过。请手动复制正文粘贴。")
        return result
    if len(text) < 80:
        result.update(status="PARSE_EMPTY", text=text, note="正文过短，可能是动态渲染页面。请手动复制正文粘贴。")
        return result
    result.update(status="PARSED", text=text, note="已从公开页面抽取正文。")
    return result


# ==================================================================== 统一 Job Schema

JOB_SCHEMA = "ai-career-os/job@1"

#: 实习 / 全职判定。
#: 拉丁词必须用**词边界**，否则 "international" 里的 intern 会把一个资深岗位误判成实习。
_INTERN_RE = re.compile(
    r"(?<![a-z])(intern|internship|interns|trainee|apprentice|co-?op)(?![a-z])"
    r"|(?<![a-z])(campus|graduate)\s+(hire|hiring|program|programme|role|position)(?![a-z])"
    r"|实习|校招|应届生|见习",
    re.IGNORECASE,
)
_FULLTIME_RE = re.compile(
    r"(?<![a-z])(full[-\s]?time|permanent)(?![a-z])|全职|正式员工|正式编制",
    re.IGNORECASE,
)


def detect_employment_type(*parts: str | None) -> str:
    """从岗位名 / 标签 / 正文里识别实习或全职；识别不了就返回 UNKNOWN（不猜）。"""
    haystack = " ".join((part or "") for part in parts)
    if _INTERN_RE.search(haystack):
        return "INTERN"
    if _FULLTIME_RE.search(haystack):
        return "FULLTIME"
    return "UNKNOWN"


def _parse_iso(value) -> datetime | None:
    """尽量解析常见的发布时间格式（ISO 字符串 / 毫秒时间戳）。解析不了返回 None。"""
    if value is None or value == "":
        return None
    if isinstance(value, (int, float)):
        # Lever 用毫秒时间戳
        return datetime.fromtimestamp(value / 1000.0, tz=timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError:
        return None
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)


def normalize_job(
    *,
    source: str,
    source_url: str = "",
    apply_url: str = "",
    company: str = "",
    role: str = "",
    location: str = "",
    jd: str = "",
    posted_at: str | None = None,
    employment_type: str | None = None,
    tags: list[str] | None = None,
    needs_confirm: list[str] | None = None,
    raw: dict | None = None,
) -> dict:
    """统一岗位结构：所有来源适配器都必须产出这个结构，才能进入去重与岗位库。"""
    company = (company or "").strip()
    role = (role or "").strip()
    location = (location or "").strip()
    jd = (jd or "").strip()
    tags = [str(tag).strip() for tag in (tags or []) if str(tag).strip()]
    collected_at = datetime.now(timezone.utc).isoformat()
    employment = (employment_type or "").strip().upper() or detect_employment_type(role, " ".join(tags), jd)
    if employment not in {"INTERN", "FULLTIME", "UNKNOWN"}:
        employment = "UNKNOWN"

    # 落库用的整段文本：保留可回溯的原文，缺字段时不编造。
    text = "\n".join(
        part
        for part in [
            f"公司：{company}" if company else None,
            f"职位：{role}" if role else None,
            f"地点：{location}" if location else None,
            f"类型：{employment}" if employment != "UNKNOWN" else None,
            f"标签：{', '.join(tags)}" if tags else None,
            f"发布时间：{posted_at}" if posted_at else None,
            "",
            jd,
        ]
        if part is not None
    ).strip()

    unresolved = list(needs_confirm or [])
    for name, value in (("company", company), ("role", role), ("location", location), ("jd", jd)):
        if not value and name not in unresolved:
            unresolved.append(name)

    return {
        "schema": JOB_SCHEMA,
        "source": source,
        "source_url": source_url or "",
        "apply_url": apply_url or "",
        "company": company,
        "role": role,
        "location": location,
        "jd": jd,
        "jd_excerpt": jd[:400],
        "posted_at": posted_at,
        "collected_at": collected_at,
        "employment_type": employment,
        "tags": tags,
        "dedupe_key": dedupe_key(company, role, location),
        "needs_confirm": unresolved,
        "text": text,
        "raw": raw or {},
    }


def _tokens(value: str) -> list[str]:
    """中文按整串与 2-gram 切分，英文按词切分，便于多关键词模糊匹配。"""
    text = (value or "").lower()
    latin = re.findall(r"[a-z0-9+#.]+", text)
    cjk = re.findall(r"[\u4e00-\u9fff]+", text)
    grams: list[str] = []
    for chunk in cjk:
        grams.append(chunk)
        if len(chunk) >= 2:
            grams.extend(chunk[i : i + 2] for i in range(len(chunk) - 1))
    return latin + grams


def _compress(value: str) -> str:
    return re.sub(r"[\s\-_/·、,，]+", "", (value or "").lower())


def job_match_score(job: dict, keyword: str) -> int:
    """单个关键词与岗位的匹配分：0 = 未命中，3 = 命中岗位名，2 = 命中公司/标签，1 = 仅命中 JD 正文。

    拉丁多词关键词要求**所有词元都出现**，避免 "product manager" 只因为 JD 里
    出现了一个 product 就误命中；中文按整串子串匹配（归一化后忽略空格与分隔符）。
    """
    needle = (keyword or "").strip().lower()
    if not needle:
        return 0
    role = (job.get("role") or "").lower()
    company = (job.get("company") or "").lower()
    tags = " ".join(job.get("tags") or []).lower()
    jd = (job.get("jd") or "").lower()

    compressed_needle = _compress(needle)
    if compressed_needle and re.search(r"[\u4e00-\u9fff]", needle):
        if compressed_needle in _compress(role):
            return 3
        if compressed_needle in _compress(company) or compressed_needle in _compress(tags):
            return 2
        if compressed_needle in _compress(jd):
            return 1
        return 0

    tokens = [token for token in _tokens(needle) if token]
    if not tokens:
        return 0
    title_zone = f"{role} {company} {tags}"
    if all(token in title_zone for token in tokens):
        return 3
    if len(tokens) >= 2:
        # 复合关键词（如 "product manager"）只靠 JD 里两个词恰好都出现太容易误命中，
        # 因此要求至少有一个词元出现在岗位名 / 公司 / 标签里。
        if not any(token in title_zone for token in tokens):
            return 0
        return 2 if all(token in jd or token in title_zone for token in tokens) else 1
    # 单词关键词允许 JD 命中，但分数最低（排序时靠后）。
    return 1 if tokens[0] in jd else 0


def job_matches(job: dict, keywords: list[str]) -> bool:
    """多关键词取「或」：任一关键词有匹配分即算命中。"""
    if not keywords:
        return True
    return any(job_match_score(job, keyword) > 0 for keyword in keywords)


def rank_jobs(jobs: list[dict], keywords: list[str]) -> list[dict]:
    """按关键词匹配分从高到低排序（岗位名命中优先于 JD 里偶然出现）。"""
    if not keywords:
        return list(jobs)

    def score(job: dict) -> int:
        return max((job_match_score(job, keyword) for keyword in keywords), default=0)

    return sorted(jobs, key=lambda item: (-score(item), item.get("role") or ""))


def _within_days(posted_at: str | None, days: int | None) -> bool:
    if not days or days <= 0:
        return True
    parsed = _parse_iso(posted_at)
    if parsed is None:
        # 来源没给发布时间：不猜，直接放行（UI 会标注"发布时间未知"）。
        return True
    return (datetime.now(timezone.utc) - parsed).days <= days


def filter_jobs(
    jobs: list[dict],
    *,
    location: str | None = None,
    employment_type: str | None = None,
    posted_within_days: int | None = None,
) -> list[dict]:
    """统一筛选：城市（子串）/ 实习全职 / 发布时间窗口。"""
    result = []
    for job in jobs:
        if location:
            needle = location.strip().lower()
            if needle and needle not in (job.get("location") or "").lower():
                continue
        if employment_type and employment_type.upper() != "ANY":
            if (job.get("employment_type") or "UNKNOWN").upper() != employment_type.upper():
                continue
        if not _within_days(job.get("posted_at"), posted_within_days):
            continue
        result.append(job)
    return result


# ==================================================================== 来源适配器


def _http_json(url: str, *, timeout: float = 20.0) -> tuple[object | None, str | None]:
    """GET 一个公开 JSON 接口；失败时返回 (None, 真实错误原因)，绝不返回演示数据。"""
    try:
        with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(url)
    except httpx.HTTPError as exc:
        return None, f"请求失败：{exc.__class__.__name__}"
    if response.status_code != 200:
        return None, f"{url} 返回 HTTP {response.status_code}"
    try:
        return response.json(), None
    except ValueError:
        return None, "返回内容不是合法 JSON"


def collect_remoteok(*, tag: str | None = None, limit: int = 20, keywords: list[str] | None = None) -> dict:
    """从 RemoteOK 官方公开 JSON 接口采集真实岗位（无需登录，条款允许）。

    RemoteOK 本身只有远程岗位，因此「城市」筛选在这里命中率很低，这一点会在
    ``note`` 里如实说明，不做任何伪造。
    """
    limit = max(1, min(int(limit or 20), 50))
    collected_at = datetime.now(timezone.utc).isoformat()
    payload, error = _http_json(REMOTEOK_API)
    if error:
        return {"source": "remoteok", "status": "ERROR", "note": error, "jobs": [], "count": 0, "collected_at": collected_at}
    if not isinstance(payload, list):
        return {"source": "remoteok", "status": "ERROR", "note": "返回内容不是岗位数组", "jobs": [], "count": 0, "collected_at": collected_at}

    wanted = [item for item in keywords if item] or ([tag] if tag else [])
    jobs: list[dict] = []
    for item in payload:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        tags = item.get("tags") or []
        tags = tags if isinstance(tags, list) else []
        description = html_to_text(item.get("description") or "")
        job = normalize_job(
            source="remoteok",
            source_url=item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}",
            apply_url=item.get("apply_url") or "",
            company=(item.get("company") or "").strip(),
            role=(item.get("position") or "").strip(),
            location=(item.get("location") or "Remote").strip() or "Remote",
            jd=description,
            posted_at=item.get("date"),
            employment_type=detect_employment_type(item.get("position"), " ".join(tags), description),
            tags=tags,
            raw={"remoteok_id": item.get("id"), "salary": item.get("salary_min") or item.get("salary_max") or None},
        )
        if job_matches(job, wanted):
            jobs.append(job)
        if len(jobs) >= limit:
            break

    note = ""
    if not jobs:
        note = "RemoteOK 公开接口没有匹配到关键词的岗位（该站只有远程岗位）。"
    return {
        "source": "remoteok",
        "status": "OK" if jobs else "EMPTY",
        "collected_at": collected_at,
        "count": len(jobs),
        "note": note,
        "jobs": jobs,
    }


def collect_greenhouse(*, boards: list[str], limit: int = 20, keywords: list[str] | None = None) -> dict:
    """Greenhouse 公开招聘板接口：`boards-api.greenhouse.io/v1/boards/{token}/jobs?content=true`。

    这不是全网检索接口——必须按企业招聘板标识（board token）逐个拉取，
    拉取失败时返回真实错误，不会回退到任何模拟数据。
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    boards = [item.strip() for item in boards if item and item.strip()]
    if not boards:
        return {"source": "greenhouse", "status": "EMPTY", "note": "未填写任何 Greenhouse 招聘板标识。", "jobs": [], "count": 0, "collected_at": collected_at}

    jobs: list[dict] = []
    errors: list[str] = []
    for board in boards:
        payload, error = _http_json(f"https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true", timeout=25.0)
        if error:
            errors.append(f"{board}：{error}")
            continue
        rows = (payload or {}).get("jobs") if isinstance(payload, dict) else None
        if not isinstance(rows, list):
            errors.append(f"{board}：返回结构里没有 jobs 数组")
            continue
        for item in rows:
            if not isinstance(item, dict):
                continue
            content = html_to_text(item.get("content") or "")
            location_value = item.get("location")
            location = (location_value or {}).get("name") if isinstance(location_value, dict) else (location_value or "")
            title = (item.get("title") or "").strip()
            job = normalize_job(
                source="greenhouse",
                source_url=item.get("absolute_url") or "",
                apply_url=item.get("absolute_url") or "",
                # Greenhouse 公开接口不直接返回公司名，用招聘板标识占位并在 UI 标注待确认。
                company="",
                role=title,
                location=(location or "").strip(),
                jd=content,
                posted_at=item.get("updated_at") or item.get("first_published") or None,
                employment_type=detect_employment_type(title, "", content),
                tags=[board],
                needs_confirm=["company"],
                raw={"board": board, "greenhouse_id": item.get("id")},
            )
            job["company"] = board
            job["company_is_board_token"] = True
            if job_matches(job, keywords or []):
                jobs.append(job)
            if len(jobs) >= limit:
                break
        if len(jobs) >= limit:
            break

    note = ""
    if errors and not jobs:
        note = "；".join(errors)
    elif errors:
        note = f"部分招聘板失败：{'；'.join(errors)}"
    elif not jobs:
        note = "这些招聘板里没有匹配到关键词的岗位。"
    return {
        "source": "greenhouse",
        "status": "OK" if jobs else ("ERROR" if errors else "EMPTY"),
        "collected_at": collected_at,
        "count": len(jobs),
        "note": note,
        "errors": errors,
        "jobs": jobs,
    }


def collect_lever(*, companies: list[str], limit: int = 20, keywords: list[str] | None = None) -> dict:
    """Lever 公开招聘接口：`api.lever.co/v0/postings/{company}?mode=json`。

    同样按企业招聘板配置，不是全网检索。
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    companies = [item.strip() for item in companies if item and item.strip()]
    if not companies:
        return {"source": "lever", "status": "EMPTY", "note": "未填写任何 Lever 企业标识。", "jobs": [], "count": 0, "collected_at": collected_at}

    jobs: list[dict] = []
    errors: list[str] = []
    for company in companies:
        payload, error = _http_json(f"https://api.lever.co/v0/postings/{company}?mode=json", timeout=25.0)
        if error:
            errors.append(f"{company}：{error}")
            continue
        if not isinstance(payload, list):
            errors.append(f"{company}：返回内容不是岗位数组")
            continue
        for item in payload:
            if not isinstance(item, dict):
                continue
            categories = item.get("categories") or {}
            title = (item.get("text") or "").strip()
            description = "\n".join(
                part
                for part in [
                    item.get("descriptionPlain") or item.get("description") or "",
                    item.get("additionalPlain") or item.get("additional") or "",
                ]
                if part
            ).strip()
            commitment = (categories or {}).get("commitment") or ""
            employment = "INTERN" if "intern" in str(commitment).lower() else (
                "FULLTIME" if "full" in str(commitment).lower() else detect_employment_type(title, "", description)
            )
            job = normalize_job(
                source="lever",
                source_url=item.get("hostedUrl") or "",
                apply_url=item.get("applyUrl") or item.get("hostedUrl") or "",
                company=company,
                role=title,
                location=str((categories or {}).get("location") or "").strip(),
                jd=description,
                posted_at=item.get("createdAt"),
                employment_type=employment,
                tags=[str((categories or {}).get("team") or ""), str((categories or {}).get("department") or "")],
                raw={"lever_id": item.get("id"), "commitment": commitment},
            )
            if job_matches(job, keywords or []):
                jobs.append(job)
            if len(jobs) >= limit:
                break
        if len(jobs) >= limit:
            break

    note = ""
    if errors and not jobs:
        note = "；".join(errors)
    elif errors:
        note = f"部分企业失败：{'；'.join(errors)}"
    elif not jobs:
        note = "这些企业招聘板里没有匹配到关键词的岗位。"
    return {
        "source": "lever",
        "status": "OK" if jobs else ("ERROR" if errors else "EMPTY"),
        "collected_at": collected_at,
        "count": len(jobs),
        "note": note,
        "errors": errors,
        "jobs": jobs,
    }


ADAPTERS = {
    "remoteok": lambda **kwargs: collect_remoteok(**kwargs),
    "greenhouse": lambda **kwargs: collect_greenhouse(**kwargs),
    "lever": lambda **kwargs: collect_lever(**kwargs),
}


def run_collection(
    *,
    sources: list[str],
    keywords: list[str] | None = None,
    location: str | None = None,
    employment_type: str | None = None,
    posted_within_days: int | None = None,
    limit: int = 20,
    greenhouse_boards: list[str] | None = None,
    lever_companies: list[str] | None = None,
) -> dict:
    """按来源逐个采集 → 统一筛选 → 跨来源去重，返回分来源成败统计。

    任何来源失败都如实写入 ``reports``，不静默吞错、不返回演示数据。
    """
    started = datetime.now(timezone.utc)
    keywords = [item.strip() for item in (keywords or []) if item and item.strip()]
    reports: list[dict] = []
    per_source_jobs: list[list[dict]] = []

    for name in sources:
        adapter = ADAPTERS.get(name)
        if adapter is None:
            reports.append({"source": name, "status": "ERROR", "count": 0, "note": f"未知来源：{name}"})
            continue
        kwargs: dict = {"limit": limit, "keywords": keywords}
        if name == "greenhouse":
            kwargs["boards"] = greenhouse_boards or []
        if name == "lever":
            kwargs["companies"] = lever_companies or []
        if name == "remoteok" and keywords:
            kwargs["tag"] = keywords[0]
        try:
            result = adapter(**kwargs)
        except Exception as exc:  # pragma: no cover - 防御性：适配器不应抛出
            reports.append({"source": name, "status": "ERROR", "count": 0, "note": f"采集异常：{exc.__class__.__name__}: {exc}"})
            continue
        source_jobs = filter_jobs(
            result.get("jobs", []),
            location=location,
            employment_type=employment_type,
            posted_within_days=posted_within_days,
        )
        reports.append(
            {
                "source": name,
                "status": result.get("status", "ERROR"),
                "fetched": len(result.get("jobs", [])),
                "count": len(source_jobs),
                "filtered_out": len(result.get("jobs", [])) - len(source_jobs),
                "note": result.get("note", ""),
                "errors": result.get("errors", []),
            }
        )
        per_source_jobs.append(source_jobs)

    # 跨来源交替取样，避免第一个来源就把名额占满，导致后续来源一条都看不到。
    all_jobs: list[dict] = []
    for index in range(max((len(items) for items in per_source_jobs), default=0)):
        for items in per_source_jobs:
            if index < len(items):
                all_jobs.append(items[index])

    # 跨来源去重（同一岗位可能同时出现在多个来源）
    seen: dict[str, dict] = {}
    duplicates: list[dict] = []
    for job in all_jobs:
        key = job.get("dedupe_key") or dedupe_key(job.get("company"), job.get("role"), job.get("location"))
        if key in seen:
            duplicates.append(
                {
                    "company": job.get("company"),
                    "role": job.get("role"),
                    "location": job.get("location"),
                    "reason": "CROSS_SOURCE_DUPLICATE",
                    "kept_source": seen[key].get("source"),
                    "dropped_source": job.get("source"),
                }
            )
            continue
        seen[key] = job

    # 关键词匹配度高的排前面（岗位名命中 > 公司/标签命中 > 仅在 JD 里出现）
    jobs = rank_jobs(list(seen.values()), keywords)[:limit]
    for job in jobs:
        job["match_score"] = max((job_match_score(job, keyword) for keyword in keywords), default=0)
    return {
        "run_id": f"run-{started.strftime('%Y%m%d%H%M%S')}",
        "started_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "request": {
            "sources": sources,
            "keywords": keywords,
            "location": location,
            "employment_type": employment_type,
            "posted_within_days": posted_within_days,
            "limit": limit,
            "greenhouse_boards": greenhouse_boards or [],
            "lever_companies": lever_companies or [],
        },
        "reports": reports,
        "jobs": jobs,
        "duplicates": duplicates,
        "totals": {
            "returned": len(jobs),
            "cross_source_duplicates": len(duplicates),
            "sources_ok": sum(1 for item in reports if item["status"] == "OK"),
            "sources_failed": sum(1 for item in reports if item["status"] == "ERROR"),
            "sources_empty": sum(1 for item in reports if item["status"] == "EMPTY"),
        },
    }


def dedupe_key(company: str | None, role: str | None, location: str | None) -> str:
    raw = "|".join(
        re.sub(r"\s+", "", (value or "").strip().lower()) for value in (company, role, location)
    )
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def find_duplicates(db: Session, profile_id: UUID, company: str | None, role: str | None, location: str | None) -> list[dict]:
    """在候选草稿与正式岗位里查同公司同岗位的重复项。"""
    key = dedupe_key(company, role, location)
    if not (company or role):
        return []

    matches: list[dict] = []
    candidates = db.scalars(
        select(models.CandidateJob).where(models.CandidateJob.profile_id == profile_id)
    ).all()
    for row in candidates:
        # 优先用落库时的 dedupe_key（采集来源更可信），缺失时按字段现算。
        stored = getattr(row, "dedupe_key", None) or dedupe_key(row.company, row.role, row.location)
        if stored == key:
            matches.append({"kind": "CANDIDATE", "id": str(row.id), "company": row.company, "role": row.role, "status": row.status})

    missions = db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all()
    for row in missions:
        if dedupe_key(row.company, row.role, getattr(row, "location", None)) == key:
            matches.append({"kind": "MISSION", "id": str(row.id), "company": row.company, "role": row.role})
    return matches


def normalize_browser_capture(payload: dict) -> dict:
    """把浏览器桥读到的「当前招聘网页」结果转成统一 Job Schema。

    浏览器只读取页面上**已经可见**的内容；字段拿不到就标 ``NEEDS_CONFIRM``，
    由用户在预览里补齐后再保存。
    """
    confidence = payload.get("confidence") or {}
    needs_confirm = [
        field
        for field in ("company", "role", "location", "jd")
        if confidence.get(field) in (None, "MISSING", "LOW")
    ]
    return normalize_job(
        source="browser",
        source_url=payload.get("page_url") or "",
        apply_url=payload.get("apply_url") or "",
        company=payload.get("company") or "",
        role=payload.get("role") or "",
        location=payload.get("location") or "",
        jd=payload.get("jd") or "",
        posted_at=payload.get("posted_at"),
        employment_type=payload.get("employment_type") or detect_employment_type(payload.get("role"), "", payload.get("jd")),
        tags=payload.get("tags") or [],
        needs_confirm=needs_confirm,
        raw={
            "page_title": payload.get("page_title"),
            "confidence": confidence,
            "extraction": payload.get("extraction") or "",
        },
    )


__all__ = [
    "ADAPTERS",
    "JOB_SCHEMA",
    "collect_greenhouse",
    "collect_lever",
    "collect_remoteok",
    "dedupe_key",
    "detect_employment_type",
    "extract_file_text",
    "extract_pdf_text",
    "fetch_url_text",
    "filter_jobs",
    "find_duplicates",
    "html_to_text",
    "job_match_score",
    "job_matches",
    "rank_jobs",
    "normalize_browser_capture",
    "normalize_job",
    "run_collection",
]
