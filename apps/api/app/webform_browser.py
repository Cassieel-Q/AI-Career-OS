"""受控浏览器桥客户端。

浏览器由用户在本地显式启动（Node + Playwright 桥，见 `apps/browser-bridge`），
本模块只做 HTTP 转发，不内置任何绕过登录 / 验证码 / 反爬的能力。

鉴权：浏览器桥要求 `Authorization: Bearer <token>`。令牌由桥启动时写入
``<数据目录>/browser-bridge.token``，也可通过环境变量 ``AI_CAREER_BRIDGE_TOKEN``
直接提供，避免本机其它进程随意调用浏览器会话。
"""

from __future__ import annotations

import os
from pathlib import Path

import httpx

from . import local_mode

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8770"
TOKEN_FILENAME = "browser-bridge.token"


class BrowserBridgeError(RuntimeError):
    pass


def bridge_url() -> str:
    """浏览器桥地址。

    优先用显式 ``BROWSER_BRIDGE_URL``（启动器会把实际端口注入后端进程）。
    未配置时按端口段探测真正在运行的桥：
    本机可能同时存在多个由不同入口启动的桥（例如手动 start-browser-bridge.cmd 与
    桌面启动器各起一个），令牌文件只反映最后一个，写死 8770 会导致 401 令牌不匹配。
    """
    explicit = os.getenv("BROWSER_BRIDGE_URL", "").strip()
    if explicit:
        return explicit.rstrip("/")
    for port in (8770, 8771, 8772, 8773):
        candidate = f"http://127.0.0.1:{port}"
        try:
            with httpx.Client(timeout=0.6) as probe:
                response = probe.get(f"{candidate}/health")
        except httpx.HTTPError:
            continue
        if response.status_code >= 500:
            continue
        try:
            if response.json().get("service") == "ai-career-os-browser-bridge":
                return candidate
        except ValueError:
            continue
    return DEFAULT_BRIDGE_URL


def _token_file() -> Path | None:
    override = os.getenv("AI_CAREER_BRIDGE_TOKEN_FILE", "").strip()
    if override:
        return Path(override)
    root = local_mode.data_root()
    if root is not None:
        return root / TOKEN_FILENAME
    return Path(os.path.join(os.environ.get("TEMP", "/tmp"), TOKEN_FILENAME))


def bridge_token() -> str:
    """按 环境变量 → 令牌文件 的顺序取令牌；都拿不到时返回空串。"""
    from_env = os.getenv("AI_CAREER_BRIDGE_TOKEN", "").strip()
    if from_env:
        return from_env
    path = _token_file()
    try:
        if path and path.exists():
            return path.read_text(encoding="utf-8").strip()
    except OSError:
        return ""
    return ""


def _headers() -> dict[str, str]:
    token = bridge_token()
    return {"Authorization": f"Bearer {token}"} if token else {}


def _call(method: str, path: str, payload: dict | None = None, *, timeout: float = 30.0) -> dict:
    url = f"{bridge_url()}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, json=payload, headers=_headers())
    except httpx.HTTPError as exc:
        raise BrowserBridgeError(
            f"受控浏览器未启动或不可达（{bridge_url()}）。请先运行 start-browser-bridge.cmd。"
        ) from exc
    if response.status_code == 401:
        raise BrowserBridgeError(
            "浏览器桥拒绝了本次调用（令牌不匹配）。请重启 start-browser-bridge.cmd 与后端，使两者使用同一份令牌。"
        )
    if response.status_code >= 400:
        detail = ""
        try:
            detail = response.json().get("error", "")
        except ValueError:
            detail = response.text[:200]
        raise BrowserBridgeError(detail or f"浏览器桥返回 HTTP {response.status_code}")
    try:
        return response.json()
    except ValueError as exc:
        raise BrowserBridgeError("浏览器桥返回内容不是 JSON") from exc


def health() -> dict:
    try:
        return {**_call("GET", "/health", timeout=5.0), "available": True, "bridge_url": bridge_url()}
    except BrowserBridgeError as exc:
        return {"available": False, "bridge_url": bridge_url(), "error": str(exc)}


def start_session(url: str | None = None) -> dict:
    return _call("POST", "/session/start", {"url": url or ""}, timeout=60.0)


def open_url(url: str) -> dict:
    return _call("POST", "/session/open", {"url": url}, timeout=60.0)


def read_page() -> dict:
    return _call("POST", "/read", {}, timeout=45.0)


def fill_page(assignments: list[dict]) -> dict:
    return _call("POST", "/fill", {"assignments": assignments}, timeout=60.0)


def extract_job() -> dict:
    """读取「当前招聘网页」并解析出岗位字段（只预览，不入库）。"""
    return _call("POST", "/extract-job", {}, timeout=60.0)


def close_session() -> dict:
    return _call("POST", "/session/close", {}, timeout=20.0)


__all__ = [
    "DEFAULT_BRIDGE_URL",
    "BrowserBridgeError",
    "bridge_token",
    "bridge_url",
    "close_session",
    "extract_job",
    "fill_page",
    "health",
    "open_url",
    "read_page",
    "start_session",
]
