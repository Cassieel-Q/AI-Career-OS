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

from fastapi import HTTPException, Request

CLIENT_HEADER = "X-AI-Career-Client"
CLIENT_HEADER_VALUE = "ai-career-web"

#: 本地前端固定来源（含端口漂移时的常见端口）
_LOCAL_ORIGINS = (
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
    "http://127.0.0.1:3002",
    "http://localhost:3002",
)


def allowed_origins() -> set[str]:
    configured = [origin.strip().rstrip("/") for origin in os.getenv("FRONTEND_ORIGINS", "").split(",") if origin.strip()]
    return {value.casefold() for value in (*_LOCAL_ORIGINS, *configured)}


def assert_trusted_request(request: Request) -> None:
    """校验来源；不通过直接 403。"""
    origin = (request.headers.get("origin") or "").strip()
    if origin:
        if origin.rstrip("/").casefold() not in allowed_origins():
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


__all__ = ["CLIENT_HEADER", "CLIENT_HEADER_VALUE", "allowed_origins", "assert_trusted_request"]
