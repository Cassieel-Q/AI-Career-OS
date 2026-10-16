"""URL 抓取安全防护（防 SSRF）。

M4 安全边界：**任何**由用户提供的 URL（粘贴 JD 链接、网申页面等）在被后端请求之前，
必须经过这里的校验：

- 只允许 http/https；
- 主机名解析出的**所有** IP 都必须是公网地址（拒绝环回 / 私网 / 链路本地 /
  保留地址 / 组播 / 未指定地址——包括云元数据服务 169.254.169.254）；
- 重定向不放给 httpx 自动跟随：逐跳手动跟随（最多 5 跳），**每一跳**都重新校验，
  防止「公网 URL 302 跳内网」的绕过。
"""
from __future__ import annotations

import ipaddress
import socket
from urllib.parse import urlsplit

from fastapi import HTTPException

MAX_REDIRECTS = 5


class UrlBlocked(HTTPException):
    """URL 被安全校验拒绝（统一 422，提示不泄露内网细节）。"""


def _blocked_reason(ip: ipaddress.IPv4Address | ipaddress.IPv6Address) -> str | None:
    if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_reserved or ip.is_multicast or ip.is_unspecified:
        return "目标地址不是公网地址"
    return None


def resolve_host_ips(host: str) -> list[str]:
    """解析主机名的全部 IP；解析失败按拒绝处理（不泄露 DNS 细节）。"""
    try:
        infos = socket.getaddrinfo(host, None)
    except OSError:
        raise UrlBlocked(422, "无法解析该链接的主机名，已拒绝抓取。") from None
    return sorted({info[4][0] for info in infos})


def assert_public_url(url: str) -> None:
    """校验 URL 指向公网 http(s) 资源；不通过直接抛 422。"""
    try:
        parts = urlsplit((url or "").strip())
    except ValueError:
        raise UrlBlocked(422, "链接格式无效，已拒绝抓取。") from None
    if parts.scheme not in {"http", "https"}:
        raise UrlBlocked(422, "只允许抓取 http/https 公开链接。")
    host = (parts.hostname or "").strip().rstrip(".")
    if not host:
        raise UrlBlocked(422, "链接缺少主机名，已拒绝抓取。")
    # 字面量 IP 直接判断；域名则解析全部 IP 判断（防止 DNS 指向内网）。
    try:
        literal = ipaddress.ip_address(host)
    except ValueError:
        literal = None
    if literal is not None:
        reason = _blocked_reason(literal)
        if reason:
            raise UrlBlocked(422, f"{reason}，已拒绝抓取。")
        return
    for ip_text in resolve_host_ips(host):
        try:
            ip = ipaddress.ip_address(ip_text)
        except ValueError:
            continue
        reason = _blocked_reason(ip)
        if reason:
            raise UrlBlocked(422, f"{reason}，已拒绝抓取。")


def safe_redirect_target(current_url: str, location: str) -> str | None:
    """计算下一跳 URL；无 location 返回 None。每跳由调用方重新 assert_public_url。"""
    if not location:
        return None
    from urllib.parse import urljoin

    return urljoin(current_url, location)
