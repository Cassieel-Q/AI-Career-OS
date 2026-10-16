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


def collect_remoteok(*, tag: str | None = None, limit: int = 20) -> dict:
    """从 RemoteOK 官方公开 JSON 接口采集真实岗位。"""
    limit = max(1, min(int(limit or 20), 50))
    collected_at = datetime.now(timezone.utc).isoformat()
    try:
        with httpx.Client(timeout=20.0, headers={"User-Agent": USER_AGENT}) as client:
            response = client.get(REMOTEOK_API)
    except httpx.HTTPError as exc:
        return {"source": "remoteok", "status": "ERROR", "note": f"请求失败：{exc.__class__.__name__}", "jobs": []}

    if response.status_code != 200:
        return {
            "source": "remoteok",
            "status": "ERROR",
            "note": f"RemoteOK 返回 HTTP {response.status_code}",
            "jobs": [],
        }

    try:
        payload = response.json()
    except ValueError:
        return {"source": "remoteok", "status": "ERROR", "note": "返回内容不是合法 JSON", "jobs": []}

    rows = [item for item in payload if isinstance(item, dict) and item.get("id")]
    if tag:
        needle = tag.strip().lower()
        # 只在「标签 / 岗位名 / 公司」上匹配，避免正文里偶然出现该词就误命中。
        def haystack(item: dict) -> str:
            tags = item.get("tags") or []
            return " ".join(
                [
                    " ".join(tags) if isinstance(tags, list) else str(tags),
                    str(item.get("position") or ""),
                    str(item.get("company") or ""),
                ]
            ).lower()

        rows = [item for item in rows if needle in haystack(item)]
    rows = rows[:limit]

    jobs = []
    for item in rows:
        description = html_to_text(item.get("description") or "")
        tags = item.get("tags") or []
        jobs.append(
            {
                "source": "remoteok",
                "source_url": item.get("url") or f"https://remoteok.com/remote-jobs/{item.get('id')}",
                "apply_url": item.get("apply_url") or "",
                "company": (item.get("company") or "").strip(),
                "role": (item.get("position") or "").strip(),
                "location": (item.get("location") or "Remote").strip() or "Remote",
                "tags": tags if isinstance(tags, list) else [],
                "posted_at": item.get("date"),
                "collected_at": collected_at,
                "text": "\n".join(
                    part
                    for part in [
                        f"公司：{item.get('company', '')}",
                        f"职位：{item.get('position', '')}",
                        f"地点：{item.get('location', '')}",
                        f"标签：{', '.join(tags) if isinstance(tags, list) else tags}",
                        "",
                        description,
                    ]
                    if part is not None
                ).strip(),
            }
        )
    return {
        "source": "remoteok",
        "status": "OK" if jobs else "EMPTY",
        "collected_at": collected_at,
        "count": len(jobs),
        "jobs": jobs,
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


__all__ = [
    "collect_remoteok",
    "dedupe_key",
    "extract_file_text",
    "extract_pdf_text",
    "fetch_url_text",
    "find_duplicates",
    "html_to_text",
]
