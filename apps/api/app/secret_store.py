"""本机用户级密钥加密存储（Windows 优先 DPAPI）。

设计约束（对应需求「安全的 Key 存储」）：
- 密钥**明文不落盘**：落盘的只有 DPAPI 加密后的密文（用户级密钥，绑定到当前 Windows 账户/机器）；
- 加密失败**绝不静默降级为明文**：直接抛 :class:`SecretStoreError`，由调用方把错误显示给用户；
- 非 Windows 平台默认**拒绝保存**，除非显式设置 ``AI_CAREER_ALLOW_PLAINTEXT_SECRETS=1``
  （仅用于 CI / Linux 开发调试，保存时会带 ``plain`` 标记，状态页会提示）；
- 每份密文都绑定 provider_id 与 base_url：地址变了就不允许继续用旧密钥（防把 A 家的 Key 发给 B 家）。
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import os
import sys
from datetime import datetime, timezone

_CIPHER_DPAPI = "dpapi"
_CIPHER_PLAIN = "plain"
_ALLOW_PLAIN_ENV = "AI_CAREER_ALLOW_PLAINTEXT_SECRETS"


class SecretStoreError(RuntimeError):
    """密钥加密/解密失败（不允许静默降级为明文）。"""


def is_windows() -> bool:
    return os.name == "nt" or sys.platform.startswith("win")


def plaintext_allowed() -> bool:
    return os.getenv(_ALLOW_PLAIN_ENV, "").strip().lower() in {"1", "true", "yes"}


def _dpapi_available() -> bool:
    return is_windows() and hasattr(__import__("ctypes"), "windll")


def _protect(data: bytes) -> bytes:
    """DPAPI CryptProtectData（当前用户密钥）。失败抛 SecretStoreError。"""
    if not is_windows():
        raise SecretStoreError("当前平台不支持 DPAPI 加密。")
    import ctypes
    import ctypes.wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # LocalFree 在 kernel32

    def _to_blob(raw: bytes) -> "_DATA_BLOB":
        buffer = ctypes.create_string_buffer(raw, len(raw))
        blob = _DATA_BLOB()
        blob.cbData = len(raw)
        blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        blob._buffer = buffer  # type: ignore[attr-defined]  # 防止被 GC
        return blob

    source = _to_blob(data)
    target = _DATA_BLOB()
    ok = crypt32.CryptProtectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(target),
    )
    if not ok:
        raise SecretStoreError("Windows DPAPI 加密失败，密钥未保存。")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def _unprotect(blob: bytes) -> bytes:
    """DPAPI CryptUnprotectData。失败抛 SecretStoreError。"""
    if not is_windows():
        raise SecretStoreError("当前平台不支持 DPAPI 解密（该密钥在本机之外无法使用）。")
    import ctypes
    import ctypes.wintypes

    class _DATA_BLOB(ctypes.Structure):
        _fields_ = [("cbData", ctypes.wintypes.DWORD), ("pbData", ctypes.POINTER(ctypes.c_char))]

    crypt32 = ctypes.windll.crypt32  # type: ignore[attr-defined]
    kernel32 = ctypes.windll.kernel32  # type: ignore[attr-defined]  # LocalFree 在 kernel32

    def _to_blob(raw: bytes) -> "_DATA_BLOB":
        buffer = ctypes.create_string_buffer(raw, len(raw))
        data_blob = _DATA_BLOB()
        data_blob.cbData = len(raw)
        data_blob.pbData = ctypes.cast(buffer, ctypes.POINTER(ctypes.c_char))
        data_blob._buffer = buffer  # type: ignore[attr-defined]
        return data_blob

    source = _to_blob(blob)
    target = _DATA_BLOB()
    ok = crypt32.CryptUnprotectData(
        ctypes.byref(source),
        None,
        None,
        None,
        None,
        0,
        ctypes.byref(target),
    )
    if not ok:
        raise SecretStoreError("Windows DPAPI 解密失败（可能不是原机器/原账户，或密钥已损坏）。")
    try:
        return ctypes.string_at(target.pbData, target.cbData)
    finally:
        kernel32.LocalFree(target.pbData)


def fingerprint(secret: str) -> str:
    """密钥指纹（只用于展示/比对，无法反推明文）。"""
    return hashlib.sha256(secret.encode("utf-8")).hexdigest()[:10]


def mask(secret: str | None) -> str:
    """脱敏展示：只保留前 3 位与后 4 位。"""
    if not secret:
        return ""
    # 只保留末 4 位用于辨认，不暴露前缀（避免泄露服务商前缀格式）
    return f"***{secret[-4:]}"


def seal(secret: str, *, provider_id: str, base_url: str) -> dict:
    """加密一份密钥，并绑定提供商与地址。"""
    raw = (secret or "").strip()
    if not raw:
        raise SecretStoreError("密钥为空。")
    if _dpapi_available():
        cipher = _CIPHER_DPAPI
        payload = _protect(raw.encode("utf-8"))
    elif plaintext_allowed():
        # 仅在显式允许时使用（Linux/CI）。状态页会明确提示「本地未加密保存」。
        cipher = _CIPHER_PLAIN
        payload = raw.encode("utf-8")
    else:
        raise SecretStoreError(
            "本机无法加密保存密钥（需要 Windows DPAPI）。"
            "如需在非 Windows 环境调试，请显式设置 AI_CAREER_ALLOW_PLAINTEXT_SECRETS=1 —— 但这会以明文保存。"
        )
    return {
        "cipher": cipher,
        "data": base64.b64encode(payload).decode("ascii"),
        "fingerprint": fingerprint(raw),
        "masked": mask(raw),
        "bound_provider_id": provider_id,
        "bound_base_url": base_url,
        "sealed_at": datetime.now(timezone.utc).isoformat(),
    }


def open_sealed(record: dict | None) -> str | None:
    """解密封装记录；失败抛 SecretStoreError（不返回空串，避免被当成「没配置」而静默改用其它来源）。"""
    if not record:
        return None
    cipher = record.get("cipher")
    payload = base64.b64decode(record.get("data") or "")
    if cipher == _CIPHER_DPAPI:
        return _unprotect(payload).decode("utf-8")
    if cipher == _CIPHER_PLAIN:
        if not plaintext_allowed():
            raise SecretStoreError("该密钥以明文方式保存，当前环境已禁止读取明文密钥。")
        return payload.decode("utf-8")
    raise SecretStoreError(f"未知的密钥封装方式：{cipher}")


def binding_matches(record: dict | None, *, provider_id: str, base_url: str) -> bool:
    """密钥是否与当前提供商/地址绑定（防止把旧地址验证过的密钥拿去新地址用）。"""
    if not record:
        return False
    return bool(
        hmac.compare_digest(str(record.get("bound_base_url") or ""), base_url)
    )


def cipher_label(cipher: str | None) -> str:
    return {"dpapi": "Windows DPAPI（用户级加密）", "plain": "明文（仅限显式允许的调试环境）"}.get(cipher or "", "未知")


__all__ = [
    "SecretStoreError",
    "binding_matches",
    "cipher_label",
    "fingerprint",
    "is_windows",
    "mask",
    "open_sealed",
    "plaintext_allowed",
    "seal",
]
