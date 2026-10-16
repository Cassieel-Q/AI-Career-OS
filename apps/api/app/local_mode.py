"""本地优先模式：稳定的本地数据目录 + 可切换的数据集（SQLite 文件）。

设计目标（对齐「本地优先使用模式」）：
- 用户不需要注册账号即可在本机使用核心功能；
- 数据落在**稳定的本地目录**（默认 `%LOCALAPPDATA%\\AICareerOS`，可用
  `AI_CAREER_DATA_DIR` 覆盖），而不是随时可能被清掉的临时演示库；
- 关闭 / 重启应用后数据完整；
- 支持多份数据集（dataset），备份导入时**恢复为新的独立数据集**，绝不覆盖当前库。

向后兼容：
- 未设置 `AI_CAREER_DATA_DIR` 时，行为与改造前完全一致 —— 只用 `DATABASE_URL`；
- 设置后进入「数据集模式」：数据库由 `<data_dir>/datasets/<active>.db` 决定，
  仅当指针文件存在且对应库存在时才接管，否则回退到 `DATABASE_URL`。
"""

from __future__ import annotations

import os
import re
import secrets
from datetime import datetime
from pathlib import Path

DATASET_ENV = "AI_CAREER_DATA_DIR"
DATASETS_DIRNAME = "datasets"
ACTIVE_POINTER = "active_dataset"
_META_SUFFIX = ".meta.json"
_ID_RE = re.compile(r"^[a-z0-9]{6,32}$")


class DatasetError(RuntimeError):
    """数据集路径 / 指针非法。"""


def data_root() -> Path | None:
    """返回本地数据目录；未启用本地模式时返回 None。"""
    raw = os.getenv(DATASET_ENV, "").strip()
    if not raw:
        return None
    return Path(raw).expanduser().resolve()


def default_data_root() -> Path:
    """默认的稳定本地数据目录（Windows 用 %LOCALAPPDATA%，其它平台用 ~/.ai-career-os）。"""
    local = os.getenv("LOCALAPPDATA", "").strip()
    if local:
        return Path(local) / "AICareerOS"
    return Path.home() / ".ai-career-os"


def ensure_dirs() -> Path:
    """确保数据目录与 datasets 子目录存在，返回数据根目录。"""
    root = data_root() or default_data_root()
    (root / DATASETS_DIRNAME).mkdir(parents=True, exist_ok=True)
    return root


def datasets_dir(root: Path | None = None) -> Path:
    base = root or data_root()
    if base is None:
        raise DatasetError("本地数据集模式未启用（缺少 AI_CAREER_DATA_DIR）。")
    return base / DATASETS_DIRNAME


def dataset_db_path(dataset_id: str, root: Path | None = None) -> Path:
    if not is_valid_dataset_id(dataset_id):
        raise DatasetError(f"非法的数据集 ID：{dataset_id!r}")
    return datasets_dir(root) / f"{dataset_id}.db"


def is_valid_dataset_id(dataset_id: str) -> bool:
    return bool(dataset_id) and bool(_ID_RE.match(dataset_id))


def new_dataset_id() -> str:
    return f"ds{datetime.now().strftime('%y%m%d%H%M%S')}{secrets.token_hex(2)}"


def _pointer_path(root: Path | None = None) -> Path:
    base = root or data_root()
    if base is None:
        raise DatasetError("本地数据集模式未启用（缺少 AI_CAREER_DATA_DIR）。")
    return base / ACTIVE_POINTER


def active_dataset_id(root: Path | None = None) -> str | None:
    path = _pointer_path(root)
    if not path.exists():
        return None
    value = path.read_text(encoding="utf-8").strip()
    return value or None


def set_active_dataset(dataset_id: str, root: Path | None = None) -> None:
    if not is_valid_dataset_id(dataset_id):
        raise DatasetError(f"非法的数据集 ID：{dataset_id!r}")
    path = _pointer_path(root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(dataset_id, encoding="utf-8")


def metadata_path(dataset_id: str, root: Path | None = None) -> Path:
    return datasets_dir(root) / f"{dataset_id}{_META_SUFFIX}"


def read_metadata(dataset_id: str, root: Path | None = None) -> dict:
    import json

    path = metadata_path(dataset_id, root)
    if not path.exists():
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def write_metadata(dataset_id: str, payload: dict, root: Path | None = None) -> None:
    import json

    path = metadata_path(dataset_id, root)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def resolve_database_url() -> str:
    """决定当前请求应使用哪个数据库 URL。

    - 未启用本地模式：直接返回 `DATABASE_URL`（与改造前一致）。
    - 启用本地模式：若 active 指针指向一个存在的数据集库，则用它；
      否则回退 `DATABASE_URL`（通常是新建的 local 主库）。
    """
    explicit = os.getenv("DATABASE_URL", "").strip()
    root = data_root()
    if root is None:
        return explicit

    (root / DATASETS_DIRNAME).mkdir(parents=True, exist_ok=True)
    current = active_dataset_id(root)
    if current:
        candidate = dataset_db_path(current, root)
        if candidate.exists():
            return f"sqlite:///{candidate.as_posix()}"
    return explicit
