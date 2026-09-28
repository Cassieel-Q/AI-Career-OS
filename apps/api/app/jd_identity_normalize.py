from __future__ import annotations

"""Normalize JD identity enums for stable storage + consistent UI mapping.

LLM / paste paths may emit mixed shapes (校招 vs ENTRY_LEVEL, 北京市 vs 北京).
Store canonical enums / city names; FE maps enums to Chinese labels.
"""


_SENIORITY_CANONICAL = frozenset(
    {"ENTRY_LEVEL", "INTERN", "JUNIOR", "MID", "SENIOR", "LEAD", "UNKNOWN"}
)

# Chinese + English aliases → canonical enum stored in DB / API.
_SENIORITY_ALIASES: dict[str, str] = {
    # campus / new grad
    "校招": "ENTRY_LEVEL",
    "校园招聘": "ENTRY_LEVEL",
    "应届": "ENTRY_LEVEL",
    "应届生": "ENTRY_LEVEL",
    "校招生": "ENTRY_LEVEL",
    "fresh graduate": "ENTRY_LEVEL",
    "fresh grad": "ENTRY_LEVEL",
    "new grad": "ENTRY_LEVEL",
    "new graduate": "ENTRY_LEVEL",
    "campus": "ENTRY_LEVEL",
    "campus hire": "ENTRY_LEVEL",
    "entry": "ENTRY_LEVEL",
    "entry level": "ENTRY_LEVEL",
    "entry-level": "ENTRY_LEVEL",
    "entry_level": "ENTRY_LEVEL",
    # intern
    "实习": "INTERN",
    "实习生": "INTERN",
    "intern": "INTERN",
    "internship": "INTERN",
    # junior
    "初级": "JUNIOR",
    "junior": "JUNIOR",
    # mid
    "中级": "MID",
    "mid": "MID",
    "middle": "MID",
    "mid-level": "MID",
    "mid_level": "MID",
    "midlevel": "MID",
    "intermediate": "MID",
    # senior
    "高级": "SENIOR",
    "senior": "SENIOR",
    # lead / staff
    "资深": "LEAD",
    "专家": "LEAD",
    "lead": "LEAD",
    "staff": "LEAD",
    "principal": "LEAD",
}


def normalize_seniority(value: object) -> str:
    """Map loose LLM / form seniority to a stable enum (ENTRY_LEVEL, INTERN, …)."""
    if value is None:
        return "UNKNOWN"
    text = str(value).strip()
    if not text:
        return "UNKNOWN"
    upper = text.upper().replace("-", "_").replace(" ", "_")
    if upper in _SENIORITY_CANONICAL:
        return upper
    # Exact Chinese / mixed alias
    mapped = _SENIORITY_ALIASES.get(text) or _SENIORITY_ALIASES.get(text.casefold())
    if mapped:
        return mapped
    # Compact English: "EntryLevel" / "ENTRY LEVEL"
    compact = "".join(ch for ch in text.casefold() if ch.isalnum() or ch in {"_", "-"})
    compact = compact.replace("-", "_")
    for alias, enum in _SENIORITY_ALIASES.items():
        alias_c = "".join(ch for ch in alias.casefold() if ch.isalnum() or ch in {"_", "-"}).replace("-", "_")
        if alias_c and alias_c == compact:
            return enum
    if upper in {"N/A", "NONE", "NULL", "-"}:
        return "UNKNOWN"
    # Unknown free-text: keep trimmed (bounded) rather than forcing UNKNOWN so user edits survive.
    return text[:64]


def normalize_location(value: object) -> str | None:
    """Normalize location for storage: strip trailing 市 for plain cities; drop UNKNOWN placeholders."""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if text.upper() in {"UNKNOWN", "N/A", "NONE", "NULL", "-"} or text in {"未知", "待确认"}:
        return None
    # 北京市 → 北京; keep 浦东新区 / 朝阳区 as-is.
    if (
        text.endswith("市")
        and len(text) >= 3
        and "区" not in text
        and "县" not in text
        and "州" not in text
    ):
        text = text[:-1]
    return text[:255]


# Common mainland city stems (without trailing 市) for JD heuristic extraction.
_COMMON_CITIES = (
    "北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "西安", "苏州",
    "重庆", "天津", "长沙", "郑州", "青岛", "大连", "厦门", "合肥", "福州", "济南",
    "沈阳", "昆明", "南昌", "哈尔滨", "长春", "石家庄", "太原", "贵阳", "南宁", "海口",
    "珠海", "佛山", "东莞", "无锡", "宁波", "温州",
)


def infer_seniority_from_jd(raw_text: str) -> str:
    """Heuristic seniority from JD body when LLM left UNKNOWN.

    Prefers explicit campus/intern markers; returns canonical enum or UNKNOWN.
    """
    body = (raw_text or "").strip()
    if not body:
        return "UNKNOWN"
    # Explicit labeled fields first.
    import re as _re

    labeled = _re.search(
        r"(?:招聘类型|招聘形式|职级|级别|层级|Seniority|Level|Grade)\s*[：:\-]\s*([^\n\r，,；;]{1,40})",
        body,
        flags=_re.IGNORECASE,
    )
    if labeled:
        mapped = normalize_seniority(labeled.group(1))
        if mapped != "UNKNOWN":
            return mapped

    # Token scan — campus / intern before generic mid/senior words that appear in duties.
    campus_tokens = ("校招", "校园招聘", "校园招聘会", "应届生", "应届", "校招生", "fresh graduate", "new grad", "campus hire")
    intern_tokens = ("实习生", "实习岗", "实习招聘", "internship", "intern hiring")
    lower = body.casefold()
    for token in campus_tokens:
        if token.casefold() in lower or token in body:
            return "ENTRY_LEVEL"
    for token in intern_tokens:
        if token.casefold() in lower or token in body:
            return "INTERN"
    # Labeled 社招 / 社会招聘 alone is not a seniority enum — leave UNKNOWN.
    return "UNKNOWN"


def infer_location_from_jd(raw_text: str) -> str | None:
    """Heuristic work location from JD body when LLM left location empty."""
    body = (raw_text or "").strip()
    if not body:
        return None
    import re as _re

    labeled = _re.search(
        r"(?:工作地点|办公地点|工作城市|工作地址|地点|城市|Location|City|Base)\s*[：:\-]\s*([^\n\r]{1,80})",
        body,
        flags=_re.IGNORECASE,
    )
    if labeled:
        candidate = labeled.group(1).strip()
        # Take first segment before separators.
        candidate = _re.split(r"[|｜/、，,；;]", candidate)[0].strip(" 　-—·•【】[]()（）")
        normalized = normalize_location(candidate)
        if normalized:
            return normalized

    # Bare city mention near 地点 / 办公 / 坐班, else first common city in header lines.
    header = "\n".join(body.splitlines()[:12])
    for city in _COMMON_CITIES:
        if city in header or f"{city}市" in header:
            return city
    # Full-body fallback only when paired with location cue.
    if any(cue in body for cue in ("工作地点", "办公地点", "工作城市", "Location", "base in")):
        for city in _COMMON_CITIES:
            if city in body or f"{city}市" in body:
                return city
    return None
