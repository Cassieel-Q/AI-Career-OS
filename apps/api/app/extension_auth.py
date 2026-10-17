"""浏览器扩展与本地 API 的配对鉴权（M2.5）。

威胁模型：
- 任何网页都可能向 ``http://127.0.0.1:<port>`` 发请求（DNS rebinding / CSRF / 表单 POST）；
- 因此**不能**只靠「来源是 localhost」或 Origin 头来做写权限判定。

做法：
1. 本地生成一个高熵令牌，落在数据目录 ``extension.token``（**不放在网页 DOM / URL / 静态资源里**）；
2. 用户在本地网页点「生成配对码」，后端返回一个 5 分钟有效的 6 位数字码；
3. 扩展用配对码换取令牌，之后每个写请求都带 ``X-AI-Career-Token``；
4. 令牌比对用恒定时间比较；配对码有尝试次数与有效期限制。
"""
from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import time
from pathlib import Path

from .local_mode import default_data_root, ensure_dirs

TOKEN_FILENAME = "extension.token"
PAIR_CODE_TTL_SECONDS = 300
PAIR_CODE_MAX_ATTEMPTS = 8
_CODE_RE = re.compile(r"^\d{6}$")

#: 允许的扩展来源前缀（Edge / Chrome 的 MV3 扩展页面）
_EXTENSION_ORIGIN_PREFIXES = ("chrome-extension://", "moz-extension://", "edge://")
#: 本地前端
_LOCAL_ORIGINS = {
    "http://127.0.0.1:3000",
    "http://localhost:3000",
    "http://127.0.0.1:3001",
    "http://localhost:3001",
}

# 进程内短时状态（不落盘，重启即失效）
_codes: dict[str, dict] = {}
_failures: dict[str, int] = {}
_last_failure_at: float = 0.0
_FAILURE_WINDOW = 600.0
_FAILURE_LIMIT = 20


def _data_dir() -> Path:
    import os

    raw = os.getenv("AI_CAREER_DATA_DIR", "").strip()
    if raw:
        return Path(raw).expanduser()
    return default_data_root()


def token_path() -> Path:
    return _data_dir() / TOKEN_FILENAME


def current_token() -> str | None:
    path = token_path()
    if not path.exists():
        return None
    try:
        value = path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    return value or None


def ensure_token() -> str:
    """读取或生成本地扩展令牌（首次调用时创建）。"""
    existing = current_token()
    if existing:
        return existing
    path = token_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    token = secrets.token_urlsafe(32)
    path.write_text(token, encoding="utf-8")
    return token


def is_paired() -> bool:
    return current_token() is not None


def verify(token: str | None) -> bool:
    expected = current_token()
    if not expected or not token:
        return False
    return hmac.compare_digest(str(token), expected)


def issue_pair_code() -> dict:
    """生成一个 5 分钟内有效的 6 位配对码（同时作废上一个）。"""
    ensure_token()
    now = time.time()
    for key, item in list(_codes.items()):
        if item["expires_at"] <= now:
            _codes.pop(key, None)
    code = "".join(secrets.choice("0123456789") for _ in range(6))
    _codes[code] = {"expires_at": now + PAIR_CODE_TTL_SECONDS, "attempts": 0}
    return {"code": code, "expires_in": PAIR_CODE_TTL_SECONDS, "expires_at": now + PAIR_CODE_TTL_SECONDS}


def exchange_code(code: str) -> str | None:
    """用配对码换令牌；失败返回 None（带尝试次数限制）。"""
    global _last_failure_at
    if not code or not _CODE_RE.match(code.strip()):
        return None
    now = time.time()
    if now - _last_failure_at > _FAILURE_WINDOW:
        _failures.clear()
    if sum(_failures.values()) >= _FAILURE_LIMIT:
        return None

    item = _codes.get(code.strip())
    if item is None or item["expires_at"] <= now:
        _failures[code.strip()] = _failures.get(code.strip(), 0) + 1
        _last_failure_at = now
        return None
    item["attempts"] += 1
    if item["attempts"] > PAIR_CODE_MAX_ATTEMPTS:
        _codes.pop(code.strip(), None)
        return None
    _codes.pop(code.strip(), None)
    _failures.pop(code.strip(), None)
    return ensure_token()


def pending_codes() -> int:
    now = time.time()
    return sum(1 for item in _codes.values() if item["expires_at"] > now)


def origin_allowed(origin: str | None) -> bool:
    """扩展请求允许；未知网页来源一律拒绝。"""
    if not origin:
        # 扩展后台 fetch 有时不带 Origin，此时只依赖令牌
        return True
    value = origin.strip().lower()
    if value in _LOCAL_ORIGINS:
        return True
    return value.startswith(_EXTENSION_ORIGIN_PREFIXES)


def fingerprint(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()[:12]


__all__ = [
    "ensure_token",
    "exchange_code",
    "fingerprint",
    "is_paired",
    "issue_pair_code",
    "origin_allowed",
    "pending_codes",
    "token_path",
    "verify",
]
