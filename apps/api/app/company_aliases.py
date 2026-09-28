"""Normalize company names for Interview Intelligence retrieval."""
from __future__ import annotations

_ALIASES: dict[str, str] = {
    "百度": "baidu",
    "baidu": "baidu",
    "字节": "bytedance",
    "字节跳动": "bytedance",
    "bytedance": "bytedance",
    "byte dance": "bytedance",
    "小红书": "xiaohongshu",
    "xiaohongshu": "xiaohongshu",
    "red": "xiaohongshu",
    "rednote": "xiaohongshu",
}


def canonical_company(value: str | None) -> str:
    raw = " ".join((value or "").casefold().replace("-", " ").split())
    if not raw:
        return ""
    if raw in _ALIASES:
        return _ALIASES[raw]
    # substring hits
    for key, canon in _ALIASES.items():
        if key in raw or raw in key:
            return canon
    return raw
