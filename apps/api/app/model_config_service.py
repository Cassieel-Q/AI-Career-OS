"""统一模型配置中心（Model Config Service）。

职责：
1. 保存用户在「设置 → AI 模型」里配置的模型（提供商 / Base URL / 模型 ID / 密钥 / 超时）；
2. 为所有 AI 业务模块提供**唯一**的配置来源（:func:`llm_settings`）；
3. 配置优先级：**用户启用并验证过的本地配置** → 旧版环境变量（.env） → 未配置；
4. 连接测试（含 Tool Calling / JSON / 流式能力探测）与 SSRF 防护。

存储位置：``<数据目录>/model_config.json``。
该目录在 ``datasets/`` 之外，**不在数据库里**，因此数据集备份/恢复天然不包含密钥；
密钥本体由 :mod:`app.secret_store` 用 DPAPI 加密后存放。
"""
from __future__ import annotations

import ipaddress
import json
import os
import re
import socket
import threading
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlparse

from . import local_mode
from . import secret_store

CONFIG_FILENAME = "model_config.json"
_SCHEMA_VERSION = 1

#: 测试时的最大 token 用量（明确控制费用）
TEST_MAX_TOKENS = 16
TEST_REDIRECT_LIMIT = 3

# ---------------------------------------------------------------------------
# 提供商预设（只维护「默认地址 + 示例模型」，模型 ID 始终允许手改，避免型号过期）
# ---------------------------------------------------------------------------

PROVIDER_PRESETS: list[dict] = [
    {
        "id": "deepseek",
        "label": "DeepSeek",
        "base_url": "https://api.deepseek.com",
        "models": ["deepseek-chat", "deepseek-reasoner"],
        "requires_key": True,
        "local": False,
        "key_url": "https://platform.deepseek.com/api_keys",
        "hint": "基础地址填 https://api.deepseek.com（不要带 /v1，也不要带 /chat/completions）。",
    },
    {
        "id": "openai",
        "label": "OpenAI",
        "base_url": "https://api.openai.com/v1",
        "models": ["gpt-4o-mini", "gpt-4o"],
        "requires_key": True,
        "local": False,
        "key_url": "https://platform.openai.com/api-keys",
        "hint": "使用代理网关时把基础地址改成网关地址即可。",
    },
    {
        "id": "qwen",
        "label": "通义千问（阿里云百炼）",
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "models": ["qwen-plus", "qwen-max", "qwen-turbo"],
        "requires_key": True,
        "local": False,
        "key_url": "https://bailian.console.aliyun.com/?tab=model#/api-key",
        "hint": "走 OpenAI 兼容模式，基础地址以 /compatible-mode/v1 结尾。",
    },
    {
        "id": "moonshot",
        "label": "Kimi（Moonshot）",
        "base_url": "https://api.moonshot.cn/v1",
        "models": ["moonshot-v1-8k", "moonshot-v1-32k", "kimi-k2-0905"],
        "requires_key": True,
        "local": False,
        "key_url": "https://platform.moonshot.cn/console/api-keys",
        "hint": "",
    },
    {
        "id": "zhipu",
        "label": "智谱 GLM",
        "base_url": "https://open.bigmodel.cn/api/paas/v4",
        "models": ["glm-4.6", "glm-4.5-air", "glm-4-flash"],
        "requires_key": True,
        "local": False,
        "key_url": "https://open.bigmodel.cn/usercenter/apikeys",
        "hint": "",
    },
    {
        "id": "ollama",
        "label": "Ollama（本机本地模型）",
        "base_url": "http://127.0.0.1:11434/v1",
        "models": ["qwen2.5:7b", "llama3.1:8b"],
        "requires_key": False,
        "local": True,
        "key_url": "",
        "hint": "需先在本机安装并启动 Ollama（默认 11434 端口；改成其它端口也可以）。本机地址可用，内网与其它机器地址会被拒绝。",
    },
    {
        "id": "custom",
        "label": "自定义（OpenAI 兼容）",
        "base_url": "",
        "models": [],
        "requires_key": True,
        "local": False,
        "key_url": "",
        "hint": "任何 OpenAI 兼容网关。公网仅限 HTTPS；本机地址（127.0.0.1/localhost）任意端口可用，内网与其它机器地址会被拒绝。",
    },
]

_PRESET_BY_ID = {item["id"]: item for item in PROVIDER_PRESETS}

# ---------------------------------------------------------------------------
# 业务模块（AI 功能 → 模块键 → 旧环境变量回退链）
# ---------------------------------------------------------------------------

MODEL_MODULES: list[dict] = [
    {
        "key": "assistant",
        "label": "顺顺 Agent",
        "env_chain": ["OPENAI_ASSISTANT_MODEL", "OPENAI_MISSION_MODEL", "OPENAI_MODEL"],
        "default_timeout": 180.0,
        "max_timeout": 600.0,
        "needs_tools": True,
        "needs_streaming": True,
    },
    {
        "key": "resume",
        "label": "简历解析与定向改写",
        "env_chain": ["OPENAI_MODEL", "OPENAI_RESUME_MODEL"],
        "default_timeout": 120.0,
        "max_timeout": 600.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "mission",
        "label": "岗位分析与 JD 解析",
        "env_chain": ["OPENAI_MISSION_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "insight",
        "label": "岗位匹配分析",
        "env_chain": ["OPENAI_INSIGHT_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "interview",
        "label": "模拟面试",
        "env_chain": ["OPENAI_INTERVIEW_MODEL", "OPENAI_MODEL"],
        "default_timeout": 120.0,
        "max_timeout": 600.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "claim",
        "label": "事实台账抽取",
        "env_chain": ["OPENAI_CLAIM_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "question",
        "label": "题库生成",
        "env_chain": ["OPENAI_QUESTION_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "role_exploration",
        "label": "角色探索",
        "env_chain": ["OPENAI_ROLE_EXPLORATION_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "proof_action",
        "label": "证据行动建议",
        "env_chain": ["OPENAI_PROOF_ACTION_MODEL", "OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
    {
        "key": "other",
        "label": "其它 AI 能力（差距分析 / 路线图）",
        "env_chain": ["OPENAI_MODEL"],
        "default_timeout": 60.0,
        "max_timeout": 300.0,
        "needs_tools": False,
        "needs_streaming": False,
    },
]

_MODULE_BY_KEY = {item["key"]: item for item in MODEL_MODULES}

#: 本机回环地址里也禁止访问的敏感端口（防把本机服务当成模型网关误连/被诱导访问）
_BLOCKED_LOCAL_PORTS = {22, 23, 25, 110, 143, 445, 1433, 3306, 3389, 5432, 6379, 9200, 11211, 27017}
#: AI Career OS 自身占用的端口：不允许把本机应用自己当成模型服务（自指调用会打乱会话与日志）
_SELF_LOCAL_PORTS = {8100, 8770}
_LOOPBACK_NAMES = {"localhost", "127.0.0.1", "::1"}


class ModelConfigError(RuntimeError):
    """配置本身有问题（字段非法 / 地址不合法）。"""


class ModelNotConfiguredError(RuntimeError):
    """没有任何可用模型配置（用户未配置，环境变量也没有）。"""


class ModelUnusableError(RuntimeError):
    """有配置但当前不可用（例如密钥与地址不匹配）。"""


@dataclass
class LLMSettings:
    """一个业务模块最终生效的模型设置。"""

    module: str
    source: str  # user | env
    api_key: str
    base_url: str | None
    model: str
    timeout: float
    is_deepseek: bool
    config_id: str | None = None
    config_name: str | None = None
    provider_id: str | None = None
    capabilities: dict = field(default_factory=dict)
    #: 用户配置存在但不可用、实际回退到环境变量时的原因（页面要提示，避免用户误判）
    fallback_reason: str | None = None

    def as_dict(self) -> dict:
        return {
            "module": self.module,
            "source": self.source,
            "model": self.model,
            "base_url": self.base_url,
            "timeout": self.timeout,
            "config_id": self.config_id,
            "config_name": self.config_name,
            "provider_id": self.provider_id,
            "capabilities": self.capabilities,
        }


# ---------------------------------------------------------------------------
# 存储
# ---------------------------------------------------------------------------


def config_path() -> Path:
    root = local_mode.data_root() or local_mode.default_data_root()
    return root / CONFIG_FILENAME


def _empty_store() -> dict:
    return {"version": _SCHEMA_VERSION, "default_config_id": None, "assignments": {}, "configs": []}


_LOCK = threading.RLock()


def _read_store() -> dict:
    path = config_path()
    if not path.exists():
        return _empty_store()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return _empty_store()
    if not isinstance(data, dict) or not isinstance(data.get("configs"), list):
        return _empty_store()
    data.setdefault("version", _SCHEMA_VERSION)
    data.setdefault("default_config_id", None)
    data.setdefault("assignments", {})
    return data


def _write_store(store: dict) -> None:
    path = config_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(store, ensure_ascii=False, indent=2), encoding="utf-8")
    tmp.replace(path)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_id() -> str:
    return uuid.uuid4().hex[:12]


# ---------------------------------------------------------------------------
# 配置 CRUD
# ---------------------------------------------------------------------------


def _normalize_base_url(value: str) -> str:
    return (value or "").strip().rstrip("/")


def _validate_fields(*, name: str, provider_id: str, base_url: str, model_id: str, timeout_seconds: float) -> None:
    if not (name or "").strip():
        raise ModelConfigError("请填写配置名称。")
    if not provider_id:
        raise ModelConfigError("请选择提供商。")
    if not base_url:
        raise ModelConfigError("请填写 Base URL（选择提供商后会自动填入，可修改）。")
    if not (model_id or "").strip():
        raise ModelConfigError("请填写模型 ID（例如 deepseek-chat）。")
    if timeout_seconds < 5 or timeout_seconds > 600:
        raise ModelConfigError("超时时间需在 5–600 秒之间。")
    ok, reason = validate_endpoint(base_url)
    if not ok:
        raise ModelConfigError(f"Base URL 不可用：{reason}")


def list_configs() -> list[dict]:
    """返回脱敏后的配置列表（**不含密钥明文**）。"""
    store = _read_store()
    return [_public_view(item, store) for item in store["configs"]]


def _public_view(item: dict, store: dict | None = None) -> dict:
    store = store or _read_store()
    secret = item.get("secret") or {}
    bound = bool(secret) and secret_store.binding_matches(
        secret, provider_id=item.get("provider_id", ""), base_url=item.get("base_url", "")
    )
    return {
        "id": item["id"],
        "name": item.get("name", ""),
        "provider_id": item.get("provider_id", ""),
        "provider_label": _PRESET_BY_ID.get(item.get("provider_id", ""), {}).get("label", item.get("provider_id", "")),
        "base_url": item.get("base_url", ""),
        "model_id": item.get("model_id", ""),
        "timeout_seconds": item.get("timeout_seconds", 60),
        "requires_key": config_requires_key(item),
        "enabled": item.get("enabled", True),
        "is_default": store.get("default_config_id") == item["id"],
        "created_at": item.get("created_at"),
        "updated_at": item.get("updated_at"),
        "key_present": bool(secret),
        "key_masked": secret.get("masked", "") if secret else "",
        "key_fingerprint": secret.get("fingerprint", "") if secret else "",
        "key_cipher": secret.get("cipher") if secret else None,
        "key_bound": bound,
        "key_bound_base_url": secret.get("bound_base_url", "") if secret else "",
        "capabilities": item.get("capabilities") or {},
        "last_test": item.get("last_test"),
    }


def get_config(config_id: str) -> dict | None:
    store = _read_store()
    return next((item for item in store["configs"] if item["id"] == config_id), None)


def _preset_requires_key(provider_id: str) -> bool:
    return bool(_PRESET_BY_ID.get(provider_id, {}).get("requires_key", True))


def config_requires_key(item: dict) -> bool:
    """该配置是否需要 API Key。

    Ollama 这类本机服务不需要密钥；用户也可以对自定义网关显式声明不需要。
    创建/更新时会把结果固化到配置里，之后读取、测试连接、网关调用都遵守同一个判断，
    避免「保存时允许无密钥、使用时却要求密钥」的规则漂移。
    """
    value = item.get("requires_key")
    if isinstance(value, bool):
        return value
    return _preset_requires_key(item.get("provider_id", ""))


def _require_key_for(provider_id: str, api_key: str | None, *, has_existing: bool) -> str | None:
    requires = _preset_requires_key(provider_id)
    if api_key:
        return api_key
    if requires and not has_existing:
        raise ModelConfigError("请填写 API Key（该提供商需要密钥）。")
    return None


def create_config(payload: dict) -> dict:
    store = _read_store()
    provider_id = (payload.get("provider_id") or "").strip()
    base_url = _normalize_base_url(payload.get("base_url") or _PRESET_BY_ID.get(provider_id, {}).get("base_url", ""))
    model_id = (payload.get("model_id") or "").strip()
    name = (payload.get("name") or "").strip() or _PRESET_BY_ID.get(provider_id, {}).get("label", "自定义模型")
    timeout_seconds = float(payload.get("timeout_seconds") or 60)
    _validate_fields(name=name, provider_id=provider_id, base_url=base_url, model_id=model_id, timeout_seconds=timeout_seconds)

    api_key = (payload.get("api_key") or "").strip()
    _require_key_for(provider_id, api_key, has_existing=False)

    item = {
        "id": _new_id(),
        "name": name,
        "provider_id": provider_id,
        "base_url": base_url,
        "model_id": model_id,
        "timeout_seconds": timeout_seconds,
        "enabled": True,
        "created_at": _now(),
        "updated_at": _now(),
        "capabilities": {},
        "secret": None,
        # 固化「是否必须带密钥」，后续读取/测试/调用都以它为准（Ollama 等本机服务为 False）
        "requires_key": (
            payload["requires_key"] if isinstance(payload.get("requires_key"), bool) else _preset_requires_key(provider_id)
        ),
    }
    if api_key:
        item["secret"] = secret_store.seal(api_key, provider_id=provider_id, base_url=base_url)

    store["configs"].append(item)
    if not store.get("default_config_id"):
        store["default_config_id"] = item["id"]
    _write_store(store)
    return _public_view(item, store)


def update_config(config_id: str, payload: dict) -> dict:
    """更新配置。

    ``api_key`` 语义：
    - 不传 / ``None`` → **保持原密钥不变**；
    - 传非空字符串 → 替换密钥；
    - ``clear_key=True`` → 删除密钥（删除后该配置不可再使用）。
    """
    store = _read_store()
    item = next((row for row in store["configs"] if row["id"] == config_id), None)
    if item is None:
        raise ModelConfigError("配置不存在。")

    provider_id = (payload.get("provider_id") or item.get("provider_id") or "").strip()
    base_url = _normalize_base_url(payload.get("base_url") or item.get("base_url", ""))
    if payload.get("base_url") is not None:
        base_url = _normalize_base_url(payload["base_url"])
    model_id = (payload.get("model_id") or item.get("model_id") or "").strip()
    name = (payload.get("name") or item.get("name") or "").strip()
    timeout_seconds = float(payload.get("timeout_seconds") or item.get("timeout_seconds") or 60)
    _validate_fields(name=name, provider_id=provider_id, base_url=base_url, model_id=model_id, timeout_seconds=timeout_seconds)

    raw_key = payload.get("api_key")
    clear_key = bool(payload.get("clear_key"))
    secret = item.get("secret")
    endpoint_changed = (base_url != item.get("base_url", "")) or (provider_id != item.get("provider_id", ""))

    if clear_key:
        secret = None  # 删除后不可继续使用
    elif isinstance(raw_key, str) and raw_key.strip():
        secret = secret_store.seal(raw_key.strip(), provider_id=provider_id, base_url=base_url)
    elif endpoint_changed and secret:
        # 换了地址/提供商却没给新密钥：保留但标记为「未绑定」，不允许再拿去请求
        secret = dict(secret)
        secret["bound_base_url"] = secret.get("bound_base_url", "")
        secret["unverified_after_change"] = True

    if isinstance(payload.get("requires_key"), bool):
        new_requires_key = payload["requires_key"]
    elif provider_id != item.get("provider_id", ""):
        new_requires_key = _preset_requires_key(provider_id)  # 换提供商后按新预设重算
    else:
        new_requires_key = config_requires_key(item)

    item.update(
        {
            "name": name,
            "provider_id": provider_id,
            "base_url": base_url,
            "model_id": model_id,
            "timeout_seconds": timeout_seconds,
            "requires_key": new_requires_key,
            "enabled": bool(payload.get("enabled", item.get("enabled", True))),
            "updated_at": _now(),
            "secret": secret,
        }
    )
    _write_store(store)
    return _public_view(item, store)


def delete_config(config_id: str) -> dict:
    """删除配置；密钥随配置一起删除（删除后原密钥不再可用）。"""
    store = _read_store()
    remaining = [row for row in store["configs"] if row["id"] != config_id]
    if len(remaining) == len(store["configs"]):
        raise ModelConfigError("配置不存在。")
    store["configs"] = remaining
    if store.get("default_config_id") == config_id:
        store["default_config_id"] = remaining[0]["id"] if remaining else None
    store["assignments"] = {k: v for k, v in store.get("assignments", {}).items() if v != config_id}
    _write_store(store)
    return {"deleted": config_id, "default_config_id": store.get("default_config_id")}


def activate_config(config_id: str) -> dict:
    store = _read_store()
    if not any(row["id"] == config_id for row in store["configs"]):
        raise ModelConfigError("配置不存在。")
    store["default_config_id"] = config_id
    _write_store(store)
    return {"default_config_id": config_id}


def set_assignments(assignments: dict) -> dict:
    store = _read_store()
    valid = {row["id"] for row in store["configs"]}
    cleaned = {key: value for key, value in (assignments or {}).items() if key in _MODULE_BY_KEY and value in valid}
    store["assignments"] = cleaned
    _write_store(store)
    return {"assignments": cleaned}


def clear_all() -> None:
    """仅供测试：清空全部配置。"""
    _write_store(_empty_store())


# ---------------------------------------------------------------------------
# SSRF 防护
# ---------------------------------------------------------------------------


def _is_loopback_host(host: str) -> bool:
    value = (host or "").strip().strip("[]").lower()
    if value in _LOOPBACK_NAMES:
        return True
    try:
        return ipaddress.ip_address(value).is_loopback
    except ValueError:
        return False


def _resolve_all(host: str) -> list[str]:
    try:
        return sorted({info[4][0] for info in socket.getaddrinfo(host, None)})
    except socket.gaierror:
        return []


def _ip_is_blocked(raw: str) -> bool:
    try:
        address = ipaddress.ip_address(raw)
    except ValueError:
        return True
    return (
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )


def validate_endpoint(base_url: str, *, allow_local: bool = True) -> tuple[bool, str]:
    """校验模型服务地址，防 SSRF。

    规则：
    - 仅允许 http/https，URL 中不得含用户名密码；
    - **公网地址必须是 HTTPS**，且解析出的 IP 不能落在内网/回环/保留网段（含 DNS rebinding 复测）；
    - **本机回环**是受控例外：允许 http（Ollama 默认就是 http://127.0.0.1:11434），
      但端口不得是本机常见敏感服务端口，且不会扩展到其它内网地址。
    """
    raw = (base_url or "").strip()
    if not raw:
        return False, "地址为空"
    parsed = urlparse(raw)
    if parsed.scheme not in {"http", "https"}:
        return False, "只支持 http/https 地址"
    if parsed.username or parsed.password:
        return False, "地址中不允许携带用户名或密码"
    host = parsed.hostname
    if not host:
        return False, "无法解析主机名"
    try:
        port = parsed.port
    except ValueError:
        return False, "端口号非法"

    if _is_loopback_host(host):
        # 本机模型服务端口没有统一标准：Ollama 默认 11434，LM Studio 常用 1234，
        # vLLM / 自建网关端口各异。因此产品边界是「本机回环任意端口」，
        # 只挡敏感服务端口与 AI Career OS 自身端口，而不是只认 11434。
        if not allow_local:
            return False, "不允许访问本机地址"
        if port is None:
            return True, ""
        if port in _SELF_LOCAL_PORTS:
            return False, f"本机 {port} 端口是 AI Career OS 自身服务，不允许作为模型地址"
        if port in _BLOCKED_LOCAL_PORTS:
            return False, f"本机 {port} 端口属于受保护服务，不允许作为模型地址"
        if port < 1024 and port != 11434:
            return False, f"本机 {port} 端口属于受保护服务，不允许作为模型地址"
        return True, ""

    if parsed.scheme != "https":
        return False, "公网地址必须使用 HTTPS"

    addresses = _resolve_all(host)
    if not addresses:
        return False, f"域名解析失败：{host}"
    for address in addresses:
        if _ip_is_blocked(address):
            return False, f"该地址解析到内网/保留地址（{address}），已拒绝"
    return True, ""


def _endpoint_root(base_url: str) -> str:
    return _normalize_base_url(base_url)


# ---------------------------------------------------------------------------
# 解析：业务模块 → 生效配置
# ---------------------------------------------------------------------------


def _env_model(module_key: str) -> str | None:
    for name in _MODULE_BY_KEY[module_key]["env_chain"]:
        value = (os.getenv(name) or "").strip()
        if value:
            return value
    return None


def _is_deepseek(base_url: str | None) -> bool:
    if not base_url:
        return False
    hostname = urlparse(base_url).hostname or ""
    host = hostname.casefold()
    return host == "deepseek.com" or host.endswith(".deepseek.com")


def _pick_config(store: dict, module_key: str) -> dict | None:
    assignments = store.get("assignments") or {}
    config_id = assignments.get(module_key) or store.get("default_config_id")
    if not config_id:
        return None
    return next((row for row in store["configs"] if row["id"] == config_id and row.get("enabled", True)), None)


def _settings_from_config(item: dict, module_key: str) -> LLMSettings:
    label = item.get("name") or "未命名配置"
    secret = item.get("secret")
    api_key = ""

    if config_requires_key(item):
        if not secret:
            raise ModelUnusableError(f"「{label}」还没有保存密钥，请编辑并填写 API Key。")
        if secret.get("unverified_after_change") or not secret_store.binding_matches(
            secret, provider_id=item.get("provider_id", ""), base_url=item.get("base_url", "")
        ):
            raise ModelUnusableError(
                f"「{label}」的密钥与当前服务地址不匹配，"
                "为避免把密钥发给错误的服务，请重新填写 API Key 并测试连接。"
            )
        try:
            api_key = secret_store.open_sealed(secret) or ""
        except secret_store.SecretStoreError as exc:
            raise ModelUnusableError(f"读取「{label}」的密钥失败：{exc}") from exc
        if not api_key:
            raise ModelUnusableError(f"「{label}」的密钥为空。")
    elif secret:
        # 不需要密钥的服务（Ollama 等）也可以自带一个可选密钥：能用就用，读不出来就如实报错
        try:
            api_key = secret_store.open_sealed(secret) or ""
        except secret_store.SecretStoreError as exc:
            raise ModelUnusableError(f"读取「{label}」的密钥失败：{exc}") from exc

    module = _MODULE_BY_KEY[module_key]
    timeout = float(item.get("timeout_seconds") or module["default_timeout"])
    timeout = max(5.0, min(timeout, float(module["max_timeout"])))
    return LLMSettings(
        module=module_key,
        source="user",
        api_key=api_key,
        base_url=item.get("base_url") or None,
        model=item.get("model_id", ""),
        timeout=timeout,
        is_deepseek=_is_deepseek(item.get("base_url")),
        config_id=item["id"],
        config_name=item.get("name"),
        provider_id=item.get("provider_id"),
        capabilities=dict(item.get("capabilities") or {}),
    )


def _settings_from_env(module_key: str) -> LLMSettings | None:
    api_key = (os.getenv("OPENAI_API_KEY") or "").strip()
    if not api_key:
        return None
    module = _MODULE_BY_KEY[module_key]
    base_url = (os.getenv("OPENAI_BASE_URL") or "").strip() or None
    model = _env_model(module_key) or "gpt-4o-mini"
    raw_timeout = (os.getenv("OPENAI_TIMEOUT_SECONDS") or "").strip()
    try:
        timeout = float(raw_timeout) if raw_timeout else module["default_timeout"]
    except ValueError:
        timeout = module["default_timeout"]
    timeout = max(5.0, min(timeout, float(module["max_timeout"])))
    return LLMSettings(
        module=module_key,
        source="env",
        api_key=api_key,
        base_url=base_url,
        model=model,
        timeout=timeout,
        is_deepseek=_is_deepseek(base_url),
        capabilities={},
    )


def llm_settings(module_key: str) -> LLMSettings:
    """业务模块取生效配置：用户配置 → 环境变量 → 抛错。"""
    if module_key not in _MODULE_BY_KEY:
        module_key = "other"
    with _LOCK:
        store = _read_store()
        item = _pick_config(store, module_key)
        user_error: BaseException | None = None
        if item is not None:
            try:
                return _settings_from_config(item, module_key)
            except (ModelUnusableError, secret_store.SecretStoreError) as exc:
                # 用户配置坏了不要「拖垮」整个 AI：有旧环境变量就回退，并把原因带到页面提示。
                user_error = exc
        env_settings = _settings_from_env(module_key)
    if env_settings is not None:
        if user_error is not None:
            env_settings.fallback_reason = str(user_error)
        return env_settings
    if user_error is not None:
        raise user_error
    raise ModelNotConfiguredError(
        "未配置 AI 模型。请在「设置 → AI 模型」里添加并启用一个模型；"
        "未配置时本地功能（岗位管理、简历编辑、PDF 导出）仍可正常使用。"
    )


def try_llm_settings(module_key: str) -> LLMSettings | None:
    try:
        return llm_settings(module_key)
    except (ModelNotConfiguredError, ModelUnusableError, ModelConfigError, secret_store.SecretStoreError):
        return None


def status() -> dict:
    """设置页状态：每个模块当前生效来源 + 是否有用户配置 + 环境回退提示。"""
    with _LOCK:
        store = _read_store()
        configs = [_public_view(row, store) for row in store["configs"]]
        modules = []
        for module in MODEL_MODULES:
            key = module["key"]
            item = _pick_config(store, key)
            entry = {
                "key": key,
                "label": module["label"],
                "source": "none",
                "config_id": None,
                "config_name": None,
                "model": None,
                "base_url": None,
                "note": "未配置 AI 模型（本地功能仍可用）",
                "usable": False,
            }
            if item is not None:
                try:
                    settings = _settings_from_config(item, key)
                    entry.update(
                        source="user",
                        config_id=item["id"],
                        config_name=item.get("name"),
                        model=settings.model,
                        base_url=settings.base_url,
                        usable=True,
                        note=f"使用你配置的「{item.get('name')}」",
                    )
                except (ModelUnusableError, secret_store.SecretStoreError) as exc:
                    env_settings = _settings_from_env(key)
                    entry.update(
                        source="user-broken",
                        config_id=item["id"],
                        config_name=item.get("name"),
                        model=env_settings.model if env_settings else item.get("model_id"),
                        base_url=env_settings.base_url if env_settings else item.get("base_url"),
                        usable=env_settings is not None,
                        note=str(exc) + ("（当前已回退到 .env 里的模型）" if env_settings else ""),
                    )
            else:
                env_settings = _settings_from_env(key)
                if env_settings is not None:
                    entry.update(
                        source="env",
                        model=env_settings.model,
                        base_url=env_settings.base_url,
                        usable=True,
                        note="当前使用 .env 环境变量里的模型（不是你在页面保存的配置）",
                    )
            modules.append(entry)

    env_present = bool((os.getenv("OPENAI_API_KEY") or "").strip())
    return {
        "configured": any(entry["usable"] for entry in modules),
        "has_user_config": bool(configs),
        "default_config_id": store.get("default_config_id"),
        "assignments": store.get("assignments", {}),
        "configs": configs,
        "modules": modules,
        "providers": PROVIDER_PRESETS,
        "env_fallback_active": env_present and not any(entry["source"] == "user" for entry in modules),
        "env_warning": (
            "当前没有任何页面配置生效，AI 功能正在使用 .env 里的旧环境变量。"
            "如果你想用刚保存的模型，请在「AI 模型」里启用它。"
            if env_present and not any(entry["source"] == "user" for entry in modules)
            else None
        ),
        "storage": {
            "path": str(config_path()),
            "in_backup": False,
            "note": "配置与加密后的密钥保存在数据目录（不在数据库里），因此数据集备份不包含密钥。",
        },
        "secret_cipher": "dpapi" if secret_store.is_windows() else ("plain" if secret_store.plaintext_allowed() else "unavailable"),
    }


# ---------------------------------------------------------------------------
# 连接测试
# ---------------------------------------------------------------------------


def _classify_error(exc: BaseException) -> tuple[str, str]:
    import httpx

    if isinstance(exc, httpx.TimeoutException):
        return "timeout", "请求超时（可能是网络不通、代理拦截或超时时间太短）。"
    if isinstance(exc, httpx.ConnectError):
        return "unreachable", "无法连接该地址（地址写错、服务未启动或被防火墙拦截）。"
    if isinstance(exc, httpx.HTTPStatusError):
        code = exc.response.status_code
        if code == 401:
            return "auth", "API Key 不正确或已失效（401）。"
        if code == 403:
            return "auth", "没有权限访问该模型（403），请检查密钥权限或账户余额。"
        if code == 429:
            return "rate_limit", "触发限流（429），请稍后再试或降低调用频率。"
        if code == 404:
            return "not_found", "地址或模型不存在（404），请检查 Base URL 与模型 ID。"
        if 500 <= code < 600:
            return "server_error", f"模型服务返回 {code}，服务商侧暂时不可用。"
        return "http_error", f"请求失败（HTTP {code}）。"
    return "unknown", f"{type(exc).__name__}: {exc}"


def _chat_url(base_url: str) -> str:
    root = _endpoint_root(base_url)
    if root.endswith("/v1"):
        return f"{root}/chat/completions"
    return f"{root}/v1/chat/completions"


def _models_url(base_url: str) -> str:
    root = _endpoint_root(base_url)
    if root.endswith("/v1"):
        return f"{root}/models"
    return f"{root}/v1/models"


_TOOL_PROBE = [
    {
        "type": "function",
        "function": {
            "name": "ping_tool",
            "description": "Connectivity probe.",
            "parameters": {"type": "object", "properties": {"value": {"type": "string"}}, "required": []},
        },
    }
]


def test_connection(payload: dict) -> dict:
    """测试连接（会产生少量费用，必须用户显式触发）。

    payload:
      - ``config_id``：测试已保存配置（用它自己的密钥）；
      - 或 ``provider_id/base_url/model_id/api_key``：测试草稿（密钥来自本次输入）；
      - ``confirm``：必须为 True，防止误触；
      - ``probe_tools`` / ``probe_stream``：是否探测工具调用/流式。
    """
    import httpx

    if not payload.get("confirm"):
        return {"ok": False, "error": {"category": "confirm_required", "message": "请先确认「测试会产生少量费用」再执行。"}, "steps": []}

    started = time.perf_counter()
    steps: list[dict] = []

    def add(step: str, ok: bool | None, detail: str) -> None:
        steps.append({"step": step, "ok": ok, "detail": detail})

    config_id = payload.get("config_id")
    raw_key = (payload.get("api_key") or "").strip()
    item = get_config(config_id) if config_id else None
    if config_id and item is None:
        return {"ok": False, "error": {"category": "not_found", "message": "配置不存在。"}, "steps": steps}

    if item is not None:
        provider_id = payload.get("provider_id") or item.get("provider_id", "")
        base_url = _normalize_base_url(payload.get("base_url") or item.get("base_url", ""))
        model_id = (payload.get("model_id") or item.get("model_id") or "").strip()
        timeout = float(payload.get("timeout_seconds") or item.get("timeout_seconds") or 30)
        endpoint_overridden = bool(payload.get("base_url")) and _normalize_base_url(payload["base_url"]) != item.get("base_url", "")
        # 地址被改过却没给新密钥 → 不能拿旧配置已验证过的密钥去打新地址
        # 但不需要密钥的本机服务（Ollama）不受此限，否则永远测不通
        if not raw_key:
            if not config_requires_key(item):
                api_key = ""
            elif endpoint_overridden:
                return {
                    "ok": False,
                    "error": {
                        "category": "key_required",
                        "message": "修改了服务地址后需要重新填写 API Key（不会把原密钥发给未验证的新地址）。",
                    },
                    "steps": steps,
                }
            else:
                secret = item.get("secret")
                if not secret:
                    return {"ok": False, "error": {"category": "key_required", "message": "该配置还没有密钥，请先填写 API Key。"}, "steps": steps}
                if secret.get("unverified_after_change"):
                    return {
                        "ok": False,
                        "error": {
                            "category": "key_required",
                            "message": "该配置的密钥是在旧的服务地址下保存的，请重新填写 API Key 后再测试。",
                        },
                        "steps": steps,
                    }
                try:
                    api_key = secret_store.open_sealed(secret) or ""
                except secret_store.SecretStoreError as exc:
                    return {"ok": False, "error": {"category": "key_unreadable", "message": str(exc)}, "steps": steps}
        else:
            api_key = raw_key
    else:
        provider_id = (payload.get("provider_id") or "").strip()
        base_url = _normalize_base_url(payload.get("base_url") or _PRESET_BY_ID.get(provider_id, {}).get("base_url", ""))
        model_id = (payload.get("model_id") or "").strip()
        timeout = float(payload.get("timeout_seconds") or 30)
        api_key = raw_key
        preset = _PRESET_BY_ID.get(provider_id, {})
        requires_key = (
            payload["requires_key"] if isinstance(payload.get("requires_key"), bool) else preset.get("requires_key", True)
        )
        if requires_key and not api_key:
            return {"ok": False, "error": {"category": "key_required", "message": "请先填写 API Key。"}, "steps": steps}

    # 1. 字段校验
    if not base_url:
        add("字段校验", False, "缺少 Base URL")
        return {"ok": False, "error": {"category": "invalid", "message": "缺少 Base URL。"}, "steps": steps}
    if not model_id:
        add("字段校验", False, "缺少模型 ID")
        return {"ok": False, "error": {"category": "invalid", "message": "缺少模型 ID。"}, "steps": steps}
    add("字段校验", True, f"{provider_id or 'custom'} · {model_id}")

    # 2. 地址合法性（SSRF）
    ok, reason = validate_endpoint(base_url)
    if not ok:
        add("地址校验", False, reason)
        return {"ok": False, "error": {"category": "ssrf_blocked", "message": reason}, "steps": steps}
    add("地址校验", True, base_url)

    headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
    timeout = max(5.0, min(timeout, 60.0))
    capabilities: dict[str, bool | None] = {"chat": None, "tools": None, "json": None, "streaming": None}

    try:
        with httpx.Client(trust_env=False, timeout=timeout, follow_redirects=False) as client:
            # 3. 认证 + 模型可用性
            auth_ok = True
            try:
                response = client.get(_models_url(base_url), headers=headers)
                if response.status_code in (301, 302, 303, 307, 308):
                    location = response.headers.get("location", "")
                    add("认证检查", None, f"服务端返回重定向（{response.status_code}）→ {location or '(空)'}，已按重定向目标重新校验")
                    ok_redirect, reason_redirect = validate_endpoint(location)
                    if not ok_redirect:
                        add("重定向校验", False, f"重定向目标被拒绝：{reason_redirect}")
                        return {"ok": False, "error": {"category": "ssrf_blocked", "message": f"重定向目标不安全：{reason_redirect}"}, "steps": steps}
                    add("重定向校验", True, location)
                elif response.status_code == 401:
                    auth_ok = False
                    add("认证检查", False, "401：API Key 无效")
                    return {"ok": False, "error": {"category": "auth", "message": "API Key 无效或已失效（401）。"}, "steps": steps}
                elif response.status_code >= 400:
                    add("模型列表", None, f"模型列表接口返回 {response.status_code}（部分服务商不支持该接口，改由对话请求验证）")
                else:
                    names: list[str] = []
                    try:
                        names = [row.get("id", "") for row in (response.json().get("data") or [])]
                    except ValueError:
                        names = []
                    if names and model_id not in names:
                        add("模型可用性", False, f"该账号下没有模型「{model_id}」（可选：{', '.join(names[:6])}）")
                        return {
                            "ok": False,
                            "error": {"category": "model_not_found", "message": f"该账号下找不到模型 {model_id}。可选：{', '.join(names[:6])}"},
                            "steps": steps,
                        }
                    add("模型可用性", True, f"共 {len(names)} 个模型，包含 {model_id}" if names else "（服务商未返回列表，跳过比对）")
            except Exception as exc:  # noqa: BLE001
                category, message = _classify_error(exc)
                add("认证检查", False, message)
                return {"ok": False, "error": {"category": category, "message": message}, "steps": steps}

            if auth_ok:
                add("认证检查", True, "密钥有效")

            # 4. 普通对话
            try:
                chat = client.post(
                    _chat_url(base_url),
                    headers=headers,
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": "回复 OK"}],
                        "max_tokens": TEST_MAX_TOKENS,
                        "stream": False,
                    },
                )
                if chat.status_code == 401:
                    add("对话测试", False, "401：API Key 无效")
                    return {"ok": False, "error": {"category": "auth", "message": "API Key 无效或已失效（401）。"}, "steps": steps}
                if chat.status_code == 429:
                    add("对话测试", False, "429：限流")
                    return {"ok": False, "error": {"category": "rate_limit", "message": "触发限流（429），请稍后再试。"}, "steps": steps}
                if chat.status_code >= 400:
                    detail = chat.text[:200]
                    add("对话测试", False, f"HTTP {chat.status_code}：{detail}")
                    return {"ok": False, "error": {"category": "http_error", "message": f"对话请求失败（HTTP {chat.status_code}）：{detail}"}, "steps": steps}
                content = ""
                try:
                    content = ((chat.json().get("choices") or [{}])[0].get("message") or {}).get("content") or ""
                except ValueError:
                    content = ""
                capabilities["chat"] = True
                add("对话测试", True, f"返回正常（{content.strip()[:24] or '空回复'}）")
            except Exception as exc:  # noqa: BLE001
                category, message = _classify_error(exc)
                add("对话测试", False, message)
                return {"ok": False, "error": {"category": category, "message": message}, "steps": steps}

            # 5. JSON 结构化输出
            try:
                json_call = client.post(
                    _chat_url(base_url),
                    headers=headers,
                    json={
                        "model": model_id,
                        "messages": [{"role": "user", "content": 'Return JSON: {"ok": true}'}],
                        "max_tokens": TEST_MAX_TOKENS,
                        "response_format": {"type": "json_object"},
                    },
                )
                capabilities["json"] = json_call.status_code < 400
                add(
                    "结构化 JSON",
                    capabilities["json"],
                    "支持 response_format=json_object" if capabilities["json"] else f"不支持（HTTP {json_call.status_code}），将改用宽松解析",
                )
            except Exception as exc:  # noqa: BLE001
                capabilities["json"] = False
                add("结构化 JSON", False, f"探测失败：{_classify_error(exc)[1]}")

            # 6. Tool Calling（顺顺需要）
            if payload.get("probe_tools", True):
                try:
                    tool_call = client.post(
                        _chat_url(base_url),
                        headers=headers,
                        json={
                            "model": model_id,
                            "messages": [{"role": "user", "content": "请调用 ping_tool 工具确认连通性"}],
                            "tools": _TOOL_PROBE,
                            "tool_choice": "auto",
                            "max_tokens": TEST_MAX_TOKENS,
                        },
                    )
                    if tool_call.status_code >= 400:
                        capabilities["tools"] = False
                        add("工具调用", False, f"不支持工具调用（HTTP {tool_call.status_code}）：顺顺将退化为「不用工具的对话模式」")
                    else:
                        try:
                            message = (tool_call.json().get("choices") or [{}])[0].get("message") or {}
                        except ValueError:
                            message = {}
                        called = bool(message.get("tool_calls"))
                        capabilities["tools"] = called
                        add(
                            "工具调用",
                            called,
                            "模型能返回 tool_calls，顺顺可用完整工具能力"
                            if called
                            else "模型没有返回 tool_calls（可能不支持或本次未触发），顺顺将退化为普通对话",
                        )
                except Exception as exc:  # noqa: BLE001
                    capabilities["tools"] = False
                    add("工具调用", False, f"探测失败：{_classify_error(exc)[1]}")

            # 7. 流式输出
            if payload.get("probe_stream", True):
                try:
                    with client.stream(
                        "POST",
                        _chat_url(base_url),
                        headers=headers,
                        json={
                            "model": model_id,
                            "messages": [{"role": "user", "content": "回复 OK"}],
                            "max_tokens": TEST_MAX_TOKENS,
                            "stream": True,
                        },
                    ) as stream:
                        if stream.status_code >= 400:
                            capabilities["streaming"] = False
                            add("流式输出", False, f"不支持流式（HTTP {stream.status_code}）")
                        else:
                            received = 0
                            for line in stream.iter_lines():
                                if line.startswith("data:"):
                                    received += 1
                                if received >= 2:
                                    break
                            capabilities["streaming"] = received > 0
                            add("流式输出", capabilities["streaming"], f"收到 {received} 个流式分片" if received else "未收到流分片")
                except Exception as exc:  # noqa: BLE001
                    capabilities["streaming"] = False
                    add("流式输出", False, f"探测失败：{_classify_error(exc)[1]}")
    except Exception as exc:  # noqa: BLE001
        category, message = _classify_error(exc)
        add("连接", False, message)
        return {"ok": False, "error": {"category": category, "message": message}, "steps": steps}

    ok = bool(capabilities["chat"])
    result = {
        "ok": ok,
        "capabilities": capabilities,
        "steps": steps,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "cost_note": f"本次最多消耗 {TEST_MAX_TOKENS} 个输出 token（约 3 次极小请求）。",
        "error": None if ok else {"category": "chat_failed", "message": "对话测试未通过。"},
    }

    # 8. 保存能力到已保存的配置
    if item is not None and ok:
        store = _read_store()
        for row in store["configs"]:
            if row["id"] == item["id"]:
                row["capabilities"] = capabilities
                row["last_test"] = {"at": _now(), "ok": True, "model": model_id}
                # 地址一致且带新密钥测试通过 → 重新绑定，解除「地址变更后未验证」状态
                if raw_key and _normalize_base_url(base_url) == item.get("base_url", ""):
                    row["secret"] = secret_store.seal(raw_key, provider_id=item.get("provider_id", ""), base_url=item.get("base_url", ""))
                elif row.get("secret"):
                    row["secret"].pop("unverified_after_change", None)
        _write_store(store)
    return result


def build_client(module_key: str, *, async_client: bool = True, default_timeout: float | None = None):
    """构造 OpenAI 兼容客户端，返回 ``(client, model, settings)``。"""
    import httpx
    from openai import AsyncOpenAI, OpenAI

    settings = llm_settings(module_key)
    options: dict[str, object] = {
        "api_key": settings.api_key,
        "timeout": settings.timeout,
        "max_retries": 0,
    }
    if settings.base_url:
        options["base_url"] = settings.base_url
    if async_client:
        options["http_client"] = httpx.AsyncClient(trust_env=False, timeout=settings.timeout)
        return AsyncOpenAI(**options), settings.model, settings
    options["http_client"] = httpx.Client(trust_env=False, timeout=settings.timeout)
    return OpenAI(**options), settings.model, settings


__all__ = [
    "MODEL_MODULES",
    "PROVIDER_PRESETS",
    "LLMSettings",
    "ModelConfigError",
    "ModelNotConfiguredError",
    "ModelUnusableError",
    "activate_config",
    "build_client",
    "clear_all",
    "config_path",
    "config_requires_key",
    "create_config",
    "delete_config",
    "get_config",
    "list_configs",
    "llm_settings",
    "set_assignments",
    "status",
    "test_connection",
    "try_llm_settings",
    "update_config",
    "validate_endpoint",
]
