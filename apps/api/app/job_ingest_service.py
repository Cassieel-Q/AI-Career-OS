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
import os
import re
import threading
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode
from uuid import UUID

import fitz
import httpx
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

USER_AGENT = "AICareerOS/1.0 (+local-first job collection; contact: local user)"
REMOTEOK_API = "https://remoteok.com/api"
REMOTIVE_API = "https://remotive.com/api/remote-jobs"

#: 每个来源两次请求之间的最小间隔（秒）——对公开接口保持礼貌，避免触发限流。
SOURCE_MIN_INTERVAL = float(os.environ.get("AI_CAREER_COLLECT_MIN_INTERVAL", "0.5"))
#: 单个来源请求失败后的重试次数与退避基数（秒）。
SOURCE_MAX_RETRIES = int(os.environ.get("AI_CAREER_COLLECT_RETRIES", "2"))
SOURCE_BACKOFF = 0.8

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
    """抓取公开链接正文。返回结构含 status / text / title / note。

    SSRF 防护：只允许公网 http(s)；重定向逐跳手动跟随，每一跳都重新校验，
    防止「公网 URL 302 跳内网/云元数据」的绕过（见 url_guard）。
    """
    from .url_guard import MAX_REDIRECTS, UrlBlocked, assert_public_url, safe_redirect_target

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
        # 第一跳之前先校验；随后每一跳重新校验（重定向不允许交给 httpx 自动跟随）。
        assert_public_url(parsed)
        with httpx.Client(
            follow_redirects=False,
            timeout=timeout,
            headers={"User-Agent": USER_AGENT, "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8"},
        ) as client:
            response = None
            current = parsed
            for _ in range(MAX_REDIRECTS + 1):
                assert_public_url(current)
                response = client.get(current)
                if response.is_redirect:
                    next_url = safe_redirect_target(current, response.headers.get("location", ""))
                    if next_url:
                        current = next_url
                        continue
                break
            else:
                result["note"] = "重定向次数过多，已停止抓取。"
                return result
    except UrlBlocked as exc:
        raise HTTPException(exc.status_code, exc.detail) from exc
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
        # 正文指纹：优先级最高的去重依据。用「落库的那一段完整文本」来算，
        # 这样 save 之后拿 row.source_text 重算能得到同样的值（同岗位 JD 更新 → UPDATED）。
        "content_hash": content_hash(role, location, text),
        "needs_confirm": unresolved,
        "text": text,
        "raw": raw or {},
    }


def content_hash(*parts: str | None) -> str:
    """岗位正文指纹（公司除外，跨来源同一岗位的公司名写法可能不同）。

    为什么要先做稳定化：RemoteOK 之类的来源会在 JD 正文里插入每次请求都不同的随机串
    （例如 ``(#RMS4yMDMuMTEwLjIz)`` 这样的反垃圾标记），直接哈希会让同一岗位每次都被误判成
    ``UPDATED``。因此先去掉 URL 与疑似随机长 token，再哈希。
    """
    normalized = " ".join(stable_text(part) for part in parts)
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


_URL_RE = re.compile(r"https?://\S+")
#: 疑似随机 token：12 位以上、同时含字母与数字的字符串，允许 base64 的 ``=`` 补齐后缀。
#: 形如 ``RMS4yMDMuMTEwLjE1Ng==`` / ``(#RMS4yMDMuMTEwLjIz)`` ——来源用这类随机串做反垃圾，
#: 每次请求都不一样，必须剥掉才能稳定去重。
_VOLATILE_TOKEN_RE = re.compile(
    r"(?<![\w=])(?=[A-Za-z0-9_\-]*\d)(?=[A-Za-z0-9_\-]*[A-Za-z])[A-Za-z0-9_\-]{12,}={0,2}(?![\w=])"
)
_WS_RE2 = re.compile(r"\s+")


def stable_text(value: str | None) -> str:
    """去掉 URL 与每次请求都变的随机串，只保留稳定正文用于去重/比对。"""
    text = (value or "").lower()
    text = _URL_RE.sub(" ", text)
    text = _VOLATILE_TOKEN_RE.sub(" ", text)
    return _WS_RE2.sub(" ", text).strip()


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


_RATE_LOCK = threading.Lock()
_LAST_REQUEST_AT: dict[str, float] = {}


def _throttle(key: str) -> None:
    """同一 host 的请求之间留出最小间隔，避免短时间打爆公开接口。"""
    interval = SOURCE_MIN_INTERVAL
    if interval <= 0:
        return
    while True:
        with _RATE_LOCK:
            now = time.monotonic()
            wait = interval - (now - _LAST_REQUEST_AT.get(key, 0.0))
            if wait <= 0:
                _LAST_REQUEST_AT[key] = now
                return
        time.sleep(min(wait, 2.0))


def _http_json(url: str, *, timeout: float = 20.0, retries: int | None = None) -> tuple[object | None, str | None]:
    """GET 一个公开 JSON 接口（带节流 / 重试 / 退避）；失败时返回 (None, 真实错误原因)，绝不返回演示数据。"""
    attempts = SOURCE_MAX_RETRIES if retries is None else max(0, int(retries))
    last_error = "请求失败"
    for attempt in range(attempts + 1):
        if attempt:
            time.sleep(SOURCE_BACKOFF * attempt)
        _throttle(url)
        try:
            with httpx.Client(timeout=timeout, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
                response = client.get(url)
        except httpx.HTTPError as exc:
            last_error = f"请求失败：{exc.__class__.__name__}"
            continue
        if response.status_code in {429, 500, 502, 503, 504} and attempt < attempts:
            last_error = f"{url} 返回 HTTP {response.status_code}"
            continue
        if response.status_code != 200:
            return None, f"{url} 返回 HTTP {response.status_code}"
        try:
            return response.json(), None
        except ValueError:
            return None, "返回内容不是合法 JSON"
    return None, f"{last_error}（已重试 {attempts} 次）"


def collect_remoteok(*, tag: str | None = None, limit: int = 20, keywords: list[str] | None = None) -> dict:
    """从 RemoteOK 官方公开 JSON 接口采集真实岗位（无需登录，条款允许）。

    RemoteOK 本身只有远程岗位，因此「城市」筛选在这里命中率很低，这一点会在
    ``note`` 里如实说明，不做任何伪造。
    """
    limit = max(1, min(int(limit or 20), 50))
    collected_at = datetime.now(timezone.utc).isoformat()
    payload, error = _http_json(REMOTEOK_API)
    if error:
        return {"source": "remoteok", "status": "ERROR", "note": error, "errors": [error], "jobs": [], "count": 0, "collected_at": collected_at}
    if not isinstance(payload, list):
        return {"source": "remoteok", "status": "ERROR", "note": "返回内容不是岗位数组", "errors": ["返回内容不是岗位数组"], "jobs": [], "count": 0, "collected_at": collected_at}

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


_REMOTIVE_JOB_TYPES = {"full_time": "FULLTIME", "part_time": "PARTTIME", "contract": "CONTRACT"}


def collect_remotive(*, keywords: list[str] | None = None, limit: int = 20, **_unused) -> dict:
    """Remotive 公开招聘接口：`remotive.com/api/remote-jobs?search=...`（无需登录，官方公开）。

    该来源支持**服务端关键词检索**，但同样只有远程岗位，地点/实习仍靠本地过滤。
    """
    collected_at = datetime.now(timezone.utc).isoformat()
    wanted = [item for item in (keywords or []) if item]
    query = " ".join(wanted[:2]).strip()
    limit = max(1, min(int(limit or 20), 50))
    jdbc = REMOTIVE_API + ("?" + urlencode({"search": query, "limit": max(limit * 3, 30)}) if query else "?limit=30")
    payload, error = _http_json(jdbc, timeout=25.0)
    if error:
        return {"source": "remotive", "status": "ERROR", "note": error, "jobs": [], "count": 0, "collected_at": collected_at, "errors": [error]}
    rows = (payload or {}).get("jobs") if isinstance(payload, dict) else None
    if not isinstance(rows, list):
        note = "返回结构里没有 jobs 数组"
        return {"source": "remotive", "status": "ERROR", "note": note, "jobs": [], "count": 0, "collected_at": collected_at, "errors": [note]}

    jobs: list[dict] = []
    for item in rows:
        if not isinstance(item, dict) or not item.get("id"):
            continue
        tags = item.get("tags") or []
        tags = tags if isinstance(tags, list) else []
        description = html_to_text(item.get("description") or "")
        job_type = str(item.get("job_type") or "").lower()
        employment = _REMOTIVE_JOB_TYPES.get(job_type) or detect_employment_type(item.get("title"), " ".join(tags), description)
        job = normalize_job(
            source="remotive",
            source_url=item.get("url") or "",
            apply_url=item.get("url") or "",
            company=(item.get("company_name") or "").strip(),
            role=(item.get("title") or "").strip(),
            location=(item.get("candidate_required_location") or "Remote").strip() or "Remote",
            jd=description,
            posted_at=item.get("publication_date"),
            employment_type=employment,
            tags=tags,
            raw={"remotive_id": item.get("id"), "job_type": item.get("job_type"), "salary": item.get("salary")},
        )
        if job_matches(job, wanted):
            jobs.append(job)
        if len(jobs) >= limit:
            break

    note = "" if jobs else f"Remotive 公开接口没有匹配到关键词的岗位（查询词：{query or '空'}）。"
    return {
        "source": "remotive",
        "status": "OK" if jobs else "EMPTY",
        "collected_at": collected_at,
        "count": len(jobs),
        "note": note,
        "errors": [],
        "jobs": jobs,
    }


#: 统一适配器契约。每个来源必须声明自己支持什么，前端才不会假装它有某个筛选能力。
#: - ``capabilities.keywords``：来源侧能否按关键词检索（否则就是拉全量后本地匹配）
#: - ``capabilities.location / employment_type / posted_within``：是否支持服务端过滤
#: - ``filter_mode``：``server`` = 服务端过滤；``local`` = 采集后再本地过滤（UI 需如实标注）
ADAPTER_SPECS: dict[str, dict] = {
    "remoteok": {
        "id": "remoteok",
        "label": "RemoteOK 公开接口",
        "mode": "adapter",
        "requires_config": False,
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "RemoteOK 官方公开 JSON 接口（无需登录）。该站只有远程岗位，因此城市筛选命中率很低。",
        "health_endpoint": REMOTEOK_API,
        "collect": collect_remoteok,
    },
    "remotive": {
        "id": "remotive",
        "label": "Remotive 公开接口",
        "mode": "adapter",
        "requires_config": False,
        "capabilities": {"keywords": True, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "Remotive 官方公开接口，支持服务端关键词检索；同样只收录远程岗位。",
        "health_endpoint": REMOTIVE_API + "?limit=1",
        "collect": collect_remotive,
    },
    "greenhouse": {
        "id": "greenhouse",
        "label": "Greenhouse 公开招聘板",
        "mode": "adapter",
        "requires_config": True,
        "config_key": "greenhouse_boards",
        "config_placeholder": "招聘板标识，逗号分隔，例如：airbnb,stripe",
        "presets": ["stripe", "airbnb", "anthropic", "figma", "databricks", "discord", "reddit", "roblox", "coinbase", "thoughtworks", "elastic", "scaleai", "figureai"],
        "preset_verified_at": datetime(2026, 10, 16, tzinfo=timezone.utc).isoformat(),
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "按企业招聘板标识逐个拉取（boards-api.greenhouse.io 公开接口），**不是全网检索**；需要先填写 board token。",
        "health_endpoint": "https://boards-api.greenhouse.io/v1/boards/{config}/jobs?content=false",
        "collect": collect_greenhouse,
    },
    "lever": {
        "id": "lever",
        "label": "Lever 公开招聘板",
        "mode": "adapter",
        "requires_config": True,
        "config_key": "lever_companies",
        "config_placeholder": "企业标识，逗号分隔，例如：palantir,spotify",
        "presets": ["leverdemo", "palantir", "spotify"],
        "preset_verified_at": datetime(2026, 10, 16, tzinfo=timezone.utc).isoformat(),
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "按企业在 Lever 的标识逐个拉取（api.lever.co 公开接口），**不是全网检索**。",
        "health_endpoint": "https://api.lever.co/v0/postings/{config}?mode=json",
        "collect": collect_lever,
    },
    "browser": {
        "id": "browser",
        "label": "采集当前招聘网页",
        "mode": "browser",
        "requires_config": False,
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "复用本地受控浏览器桥，读取你在浏览器里打开的招聘页面；只读取页面可见内容，不绕过登录与验证码。",
        "collect": None,
    },
    "paste": {
        "id": "paste",
        "label": "粘贴完整 JD",
        "mode": "manual",
        "requires_config": False,
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "任何平台都可用的兜底方式，正文由用户提供（也是 BOSS / 实习僧等需登录平台的唯一合规入口）。",
        "collect": None,
    },
    "file": {
        "id": "file",
        "label": "岗位截图 / PDF / 文档",
        "mode": "upload",
        "requires_config": False,
        "capabilities": {"keywords": False, "location": False, "employment_type": False, "posted_within": False},
        "filter_mode": "local",
        "note": "PDF / 文本 / Word 可直接解析；图片暂不支持自动 OCR，需手动粘贴。",
        "collect": None,
    },
}


def adapter_spec(source: str) -> dict | None:
    spec = ADAPTER_SPECS.get(source)
    if not spec:
        return None
    return {key: value for key, value in spec.items() if key != "collect"} | {"has_collect": spec.get("collect") is not None}


def validate_source_config(source: str, *, greenhouse_boards: list[str] | None = None, lever_companies: list[str] | None = None) -> list[str]:
    """采集前的配置校验：缺参数就明确报错，不让用户以为「采集过但没结果」。"""
    spec = ADAPTER_SPECS.get(source)
    if spec is None:
        return [f"未知来源：{source}"]
    if not spec.get("requires_config"):
        return []
    if source == "greenhouse" and not [item for item in (greenhouse_boards or []) if item and item.strip()]:
        return ["Greenhouse 需要至少一个招聘板标识（board token），可在来源卡片里点击预设填。"]
    if source == "lever" and not [item for item in (lever_companies or []) if item and item.strip()]:
        return ["Lever 需要至少一个企业标识，可在来源卡片里点击预设填。"]
    return []


def health_check(source: str, *, greenhouse_boards: list[str] | None = None, lever_companies: list[str] | None = None) -> dict:
    """来源可用性自检：真实发一次轻量请求，失败就如实返回 ERROR。"""
    spec = ADAPTER_SPECS.get(source)
    if spec is None:
        return {"source": source, "status": "ERROR", "note": f"未知来源：{source}"}
    endpoint = spec.get("health_endpoint")
    if not endpoint:
        return {"source": source, "status": "SKIPPED", "note": "该来源不支持自动健康检查（需用户手动触发或粘贴）。"}
    targets: list[str] = [""]
    if source == "greenhouse":
        targets = [item for item in (greenhouse_boards or []) if item and item.strip()] or (spec.get("presets") or [])[:1]
    if source == "lever":
        targets = [item for item in (lever_companies or []) if item and item.strip()] or (spec.get("presets") or [])[:1]

    notes: list[str] = []
    failures: list[str] = []
    started = time.monotonic()
    for target in targets[:3]:
        url = endpoint.format(config=target) if "{config}" in endpoint else endpoint
        payload, error = _http_json(url, timeout=15.0, retries=0)
        if error:
            failures.append(f"{target or '默认接口'}：{error}")
        else:
            notes.append(f"{target or '默认接口'}：HTTP 200")
    elapsed_ms = int((time.monotonic() - started) * 1000)
    status = "OK" if notes and not failures else ("PARTIAL" if notes and failures else "ERROR")
    return {
        "source": source,
        "status": status,
        "checked": notes + failures,
        "note": "；".join(failures) if failures else "；".join(notes),
        "latency_ms": elapsed_ms,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }


ADAPTERS = {
    "remoteok": lambda **kwargs: collect_remoteok(**kwargs),
    "remotive": lambda **kwargs: collect_remotive(**kwargs),
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
    timeout_seconds: float | None = None,
    cancel_check: Callable[[], bool] | None = None,
    progress: Callable[[dict], None] | None = None,
) -> dict:
    """按来源逐个采集 → 统一筛选 → 跨来源去重，返回分来源成败统计。

    任何来源失败都如实写入 ``reports``，不静默吞错、不返回演示数据。
    ``cancel_check`` 在每个来源之间被调用一次，用于支持用户取消。
    """
    started = datetime.now(timezone.utc)
    keywords = [item.strip() for item in (keywords or []) if item and item.strip()]
    reports: list[dict] = []
    per_source_jobs: list[list[dict]] = []

    def report(event: dict) -> None:
        if progress:
            try:
                progress(event)
            except Exception:  # pragma: no cover - 进度回调失败不能影响主流程
                pass

    for name in sources:
        deadline_hit = timeout_seconds is not None and (datetime.now(timezone.utc) - started).total_seconds() >= timeout_seconds
        cancelled = bool(cancel_check and cancel_check())
        if cancelled or deadline_hit:
            reports.append(
                {
                    "source": name,
                    "status": "CANCELLED" if cancelled else "TIMEOUT",
                    "fetched": 0,
                    "count": 0,
                    "filtered_out": 0,
                    "note": "用户取消了采集。" if cancelled else "已达到本次采集的时间上限，剩余来源未继续请求。",
                    "errors": [],
                }
            )
            continue

        config_errors = validate_source_config(name, greenhouse_boards=greenhouse_boards, lever_companies=lever_companies)
        if config_errors:
            reports.append({"source": name, "status": "ERROR", "fetched": 0, "count": 0, "filtered_out": 0, "note": "".join(config_errors), "errors": config_errors})
            continue

        adapter = ADAPTERS.get(name)
        if adapter is None:
            reports.append({"source": name, "status": "ERROR", "fetched": 0, "count": 0, "filtered_out": 0, "note": f"未知来源：{name}", "errors": [f"未知来源：{name}"]})
            continue

        kwargs: dict = {"limit": limit, "keywords": keywords}
        if name == "greenhouse":
            kwargs["boards"] = greenhouse_boards or []
        if name == "lever":
            kwargs["companies"] = lever_companies or []
        if name == "remoteok" and keywords:
            kwargs["tag"] = keywords[0]

        report({"type": "SOURCE_STARTED", "source": name, "index": len(reports)})
        source_started = time.monotonic()
        try:
            result = adapter(**kwargs)
        except Exception as exc:  # pragma: no cover - 防御性：适配器不应抛出
            reports.append({"source": name, "status": "ERROR", "fetched": 0, "count": 0, "filtered_out": 0, "note": f"采集异常：{exc.__class__.__name__}: {exc}", "errors": [str(exc)]})
            continue
        elapsed_ms = int((time.monotonic() - source_started) * 1000)
        source_jobs = filter_jobs(
            result.get("jobs", []),
            location=location,
            employment_type=employment_type,
            posted_within_days=posted_within_days,
        )
        spec = ADAPTER_SPECS.get(name, {})
        reports.append(
            {
                "source": name,
                "status": result.get("status", "ERROR"),
                "fetched": len(result.get("jobs", [])),
                "count": len(source_jobs),
                "filtered_out": len(result.get("jobs", [])) - len(source_jobs),
                "note": result.get("note", ""),
                "errors": result.get("errors", []),
                "filter_mode": spec.get("filter_mode", "local"),
                "capabilities": spec.get("capabilities", {}),
                "latency_ms": elapsed_ms,
            }
        )
        report({"type": "SOURCE_FINISHED", "source": name, "status": result.get("status", "ERROR"), "fetched": len(result.get("jobs", [])), "kept": len(source_jobs)})
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

    def overall_status() -> str:
        states = {item["status"] for item in reports}
        if "CANCELLED" in states:
            return "CANCELLED"
        if len(reports) == len([item for item in reports if item["status"] == "ERROR"]) and reports:
            return "FAILED"
        if "ERROR" in states or "TIMEOUT" in states:
            return "PARTIAL"
        if not jobs:
            return "COMPLETED"
        return "COMPLETED"

    status = overall_status()
    return {
        "status": status,
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
            "timeout_seconds": timeout_seconds,
        },
        "reports": reports,
        "jobs": jobs,
        "duplicates": duplicates,
        "totals": recompute_result_totals(
            {
                "returned": len(jobs),
                "fetched": sum(item.get("fetched", 0) for item in reports),
                "filtered_out": sum(item.get("filtered_out", 0) for item in reports),
                "cross_source_duplicates": len(duplicates),
                "sources_total": len(reports),
                "sources_ok": sum(1 for item in reports if item["status"] == "OK"),
                "sources_failed": sum(1 for item in reports if item["status"] == "ERROR"),
                "sources_empty": sum(1 for item in reports if item["status"] == "EMPTY"),
                "sources_cancelled": sum(1 for item in reports if item["status"] == "CANCELLED"),
                "sources_timeout": sum(1 for item in reports if item["status"] == "TIMEOUT"),
            },
            jobs,
        ),
    }


def recompute_result_totals(totals: dict, jobs: list[dict]) -> dict:
    """按每条结果的 ``result_status`` 重算「抓到 vs 可保存」的统计。

    注意顺序：``classify_collected`` 在采集之后才跑，所以只有调用这个函数
    得到的 new/duplicate/updated/needs_review/failed 才是准确的。
    """
    totals = dict(totals)
    counts = {state: 0 for state in ("NEW", "DUPLICATE", "UPDATED", "NEEDS_REVIEW", "FAILED")}
    for job in jobs:
        state = job.get("result_status") or ("NEW" if not job.get("needs_confirm") else "NEEDS_REVIEW")
        counts[state] = counts.get(state, 0) + 1
    totals.update(
        {
            "new": counts["NEW"],
            "duplicate": counts["DUPLICATE"],
            "updated": counts["UPDATED"],
            "needs_review": counts["NEEDS_REVIEW"],
            "failed": counts["FAILED"],
            # 「可保存」= 库里没有的新岗位 + 有变化可更新 + 待确认但用户补齐后仍可保存
            "saveable": counts["NEW"] + counts["UPDATED"] + counts["NEEDS_REVIEW"],
        }
    )
    return totals


def classify_collected(db: Session, profile_id: UUID, jobs: list[dict]) -> list[dict]:
    """给每条采集结果标注「相对于现有岗位库」的状态，UI 才能区分抓到 ≠ 新增。

    ``NEW`` 库里没有；``DUPLICATE`` 已有且正文一致；``UPDATED`` 已有但 JD 有变化；
    ``NEEDS_REVIEW`` 关键字段缺失/低置信需要用户确认；``FAILED`` 结构化失败（不可用）。
    """
    if not jobs:
        return jobs

    existing: dict[str, dict] = {}
    for row in db.scalars(select(models.CandidateJob).where(models.CandidateJob.profile_id == profile_id)).all():
        key = getattr(row, "dedupe_key", None) or dedupe_key(row.company, row.role, row.location)
        payload = row.raw_payload if isinstance(row.raw_payload, dict) else {}
        existing.setdefault(
            key,
            {
                "kind": "CANDIDATE",
                "id": str(row.id),
                "company": row.company,
                "role": row.role,
                "hash": payload.get("content_hash"),
            },
        )
    for row in db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all():
        key = dedupe_key(row.company, row.role, getattr(row, "location", None))
        existing.setdefault(
            key,
            {
                "kind": "MISSION",
                "id": str(row.id),
                "company": row.company,
                "role": row.role,
                "hash": ((row.resume_source or {}) or {}).get("content_hash") if isinstance(row.resume_source, dict) else None,
            },
        )

    for job in jobs:
        job.setdefault("needs_confirm", [])
        is_usable = bool((job.get("role") or "").strip() or (job.get("company") or "").strip()) and bool((job.get("jd") or "").strip() or (job.get("source_url") or "").strip())
        if not is_usable:
            job["result_status"] = "FAILED"
            job["result_reason"] = "结构化字段不足：既没有公司/岗位，也没有 JD 或来源链接。"
            continue
        key = job.get("dedupe_key") or dedupe_key(job.get("company"), job.get("role"), job.get("location"))
        hit = existing.get(key)
        if hit is None:
            job["result_status"] = "NEEDS_REVIEW" if job.get("needs_confirm") else "NEW"
            job["result_reason"] = "库里还没有这条岗位。" if not job.get("needs_confirm") else "关键字段缺失或置信度低，保存前请确认。"
            continue
        job["existing"] = hit
        if hit.get("hash") and hit["hash"] == job.get("content_hash"):
            job["result_status"] = "DUPLICATE"
            job["result_reason"] = f"岗位库里已存在同一条（{hit['kind']}），正文完全一致。"
        else:
            job["result_status"] = "UPDATED"
            job["result_reason"] = "岗位库里已存在同一条，但 JD 正文有变化，可选择更新。"
    return jobs


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
    "ADAPTER_SPECS",
    "ADAPTERS",
    "JOB_SCHEMA",
    "adapter_spec",
    "classify_collected",
    "collect_greenhouse",
    "collect_lever",
    "collect_remoteok",
    "collect_remotive",
    "content_hash",
    "dedupe_key",
    "detect_employment_type",
    "extract_file_text",
    "extract_pdf_text",
    "fetch_url_text",
    "filter_jobs",
    "find_duplicates",
    "health_check",
    "html_to_text",
    "job_match_score",
    "job_matches",
    "rank_jobs",
    "normalize_browser_capture",
    "normalize_job",
    "run_collection",
    "validate_source_config",
]
