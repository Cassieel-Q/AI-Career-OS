"""本地敏感接口的访问控制（Origin + 自定义头，防 CSRF / 恶意网页）。

监听 127.0.0.1 **不等于**安全：任何网页都能向本机端口发请求（表单 POST、fetch、
DNS rebinding）。因此模型密钥这类敏感接口额外要求：

1. ``Origin`` 必须在白名单内（本地前端 / 已配置的 FRONTEND_ORIGINS）；
2. 必须带自定义头 ``X-AI-Career-Client`` —— 跨域简单请求（表单）无法携带自定义头，
   带自定义头的跨域请求会触发预检，而预检被上面的 Origin 白名单拦住；
3. 若浏览器给出 ``Sec-Fetch-Site: cross-site``，直接拒绝。
"""
from __future__ import annotations

import os
from urllib.parse import urlsplit

from fastapi import HTTPException, Request

CLIENT_HEADER = "X-AI-Career-Client"
CLIENT_HEADER_VALUE = "ai-career-web"

#: 本地前端固定来源（端口漂移时前端可能落到任意可用端口，故另见 LOOPBACK_ORIGIN_REGEX）
_LOCAL_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
)

#: 回环地址的任意端口都视为本机来源。
# 本地应用的前端端口会被其它项目挤占而漂移（3000 → 3001 → 3002…），
# 逐端口加白名单迟早会漏；但这里只允许 IP 字面量/localhost，非本机来源仍需显式配置。
LOOPBACK_HOSTS = frozenset({"127.0.0.1", "localhost", "::1", "[::1]", "0:0:0:0:0:0:0:1"})
LOOPBACK_ORIGIN_REGEX = r"^https?://(127\.0\.0\.1|localhost|\[::1\])(:\d+)?$"


def is_loopback_origin(origin: str) -> bool:
    """判断来源是否是本机回环地址（任意端口）。非法/非回环一律 False。"""
    candidate = (origin or "").strip().rstrip("/")
    if not candidate:
        return False
    try:
        parts = urlsplit(candidate)
    except ValueError:
        return False
    if parts.scheme not in ("http", "https"):
        return False
    host = (parts.hostname or "").casefold()
    return host in LOOPBACK_HOSTS


def allowed_origins() -> set[str]:
    configured = [origin.strip().rstrip("/") for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
    return {value.casefold() for value in (*_LOCAL_ORIGINS, *configured)}


def is_trusted_origin(origin: str) -> bool:
    """本机前端或显式配置的来源才放行；回环地址不限端口。"""
    candidate = (origin or "").strip().rstrip("/")
    if not candidate:
        return False
    if is_loopback_origin(candidate):
        return True
    return candidate.casefold() in allowed_origins()


def assert_trusted_request(request: Request) -> None:
    """校验来源；不通过直接 403。"""
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        if not is_trusted_origin(origin):
            raise HTTPException(403, "来源不被允许（Origin 不在本机白名单内）。")
    elif request.method != "GET":
        # 非浏览器客户端（curl / 本机脚本）允许；浏览器写请求一定带 Origin 或 Sec-Fetch-Site
        pass

    fetch_site = (request.headers.get("sec-fetch-site") or "").strip().casefold()
    if fetch_site == "cross-site":
        raise HTTPException(403, "跨站请求已被拒绝。")

    if request.method != "GET":
        if (request.headers.get(CLIENT_HEADER) or "").strip() != CLIENT_HEADER_VALUE:
            raise HTTPException(403, "缺少本机客户端标识头，已拒绝该写请求。")


__all__ = [
    "CLIENT_HEADER",
    "CLIENT_HEADER_VALUE",
    "LOOPBACK_HOSTS",
    "LOOPBACK_ORIGIN_REGEX",
    "allowed_origins",
    "is_loopback_origin",
    "is_trusted_origin",
    "assert_trusted_request",
]
