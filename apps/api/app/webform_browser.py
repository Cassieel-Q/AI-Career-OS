"""受控浏览器桥客户端。

浏览器由用户在本地显式启动（Node + Playwright 桥，见 `apps/browser-bridge`），
本模块只做 HTTP 转发，不内置任何绕过登录 / 验证码 / 反爬的能力。
"""

from __future__ import annotations

import os

import httpx

DEFAULT_BRIDGE_URL = "http://127.0.0.1:8770"


class BrowserBridgeError(RuntimeError):
    pass


def bridge_url() -> str:
    return os.getenv("BROWSER_BRIDGE_URL", DEFAULT_BRIDGE_URL).rstrip("/")


def _call(method: str, path: str, payload: dict | None = None, *, timeout: float = 30.0) -> dict:
    url = f"{bridge_url()}{path}"
    try:
        with httpx.Client(timeout=timeout) as client:
            response = client.request(method, url, json=payload)
    except httpx.HTTPError as exc:
        raise BrowserBridgeError(
            f"受控浏览器未启动或不可达（{bridge_url()}）。请先运行 start-browser-bridge.cmd。"
        ) from exc
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


def close_session() -> dict:
    return _call("POST", "/session/close", {}, timeout=20.0)


__all__ = [
    "DEFAULT_BRIDGE_URL",
    "BrowserBridgeError",
    "bridge_url",
    "close_session",
    "fill_page",
    "health",
    "open_url",
    "read_page",
    "start_session",
]
