"""本地数据集备份与恢复（对齐 ResumeForge 的本地数据集管理）。

格式（zip）::

    manifest.json          # 格式版本 / 时间 / 数据集信息 / 文件清单 + SHA-256 / 排除项
    data/career.db         # 一致性快照后的 SQLite 数据库
    attachments/           # 可选附件目录（当前简历为可重建文档，通常为空）

设计要点：
- 导出使用 SQLite 在线备份 API（``sqlite3.Connection.backup``），保证拿到事务一致的快照；
- 不含任何密钥 / Cookie / 密码：本仓库把密钥放在根目录 ``.env``（不入库），数据库内也不存认证凭据；
  manifest 会显式列出「已排除项」，避免用户误以为备份里含密钥；
- 恢复**不覆盖当前库**：解包为一个新的独立数据集文件，由 `local_mode` 的指针切换。
"""

from __future__ import annotations

import hashlib
import io
import json
import sqlite3
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

from . import local_mode

BACKUP_FORMAT = "ai-career-os-backup"
BACKUP_VERSION = 1
MANIFEST_NAME = "manifest.json"
DATABASE_NAME = "data/career.db"
ATTACHMENTS_DIR = "attachments"

#: 解压上限（防「解压炸弹」）：单文件 256 MiB，整包解压总计 1 GiB。
MAX_MEMBER_BYTES = 256 * 1024 * 1024
MAX_TOTAL_BYTES = 1024 * 1024 * 1024


def _safe_attachment_rel(name: str) -> str | None:
    """把压缩包内的附件名转成安全的相对路径；不安全则返回 None。

    防 Zip Slip：`attachments/../../evil.txt` 这类成员名会把文件写到数据集目录之外。
    这里同时拒绝绝对路径、盘符、反斜杠与任何 `..` 段。
    """
    if not name.startswith(f"{ATTACHMENTS_DIR}/"):
        return None
    rel = name[len(ATTACHMENTS_DIR) + 1 :]
    if not rel or rel.endswith("/"):
        return None
    if "\\" in rel or ":" in rel:
        return None
    parts = [part for part in rel.split("/") if part not in {"", "."}]
    if not parts or any(part == ".." for part in parts):
        return None
    return "/".join(parts)


#: 备份中显式排除的内容（写进清单，供用户核对）。
EXCLUDED_ITEMS = (
    "根目录 .env（模型 API Key 等本机密钥）",
    "浏览器 Cookie / 站点登录态",
    "任何网站密码或短信验证码",
    "Typst 等外部二进制",
)

#: 参与清单计数的关键业务表。
COUNTED_TABLES = (
    "user_profiles",
    "education",
    "experiences",
    "profile_skills",
    "certifications",
    "application_profiles",
    "job_missions",
    "target_resumes",
    "target_resume_bullets",
    "resume_studio_documents",
    "job_applications",
    "candidate_jobs",
    "interview_records",
    "resume_claims",
    "job_descriptions",
    "web_form_records",
)


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _sqlite_path_from_url(url: str) -> Path:
    raw = (url or "").strip()
    if not raw.startswith("sqlite"):
        raise local_mode.DatasetError(f"备份只支持本地 SQLite 数据集，当前为：{raw or '(空)'}")
    _, _, tail = raw.partition(":///")
    if not tail:
        raise local_mode.DatasetError(f"无法解析 SQLite 路径：{raw}")
    return Path(tail)


def snapshot_database(db_url: str) -> bytes:
    """用 SQLite 在线备份 API 生成一致性快照（即便有并发写入也不会撕裂）。"""
    source_path = _sqlite_path_from_url(db_url)
    if not source_path.exists():
        raise local_mode.DatasetError(f"数据库文件不存在：{source_path}")

    with tempfile.TemporaryDirectory() as tmp:
        dest_path = Path(tmp) / "snapshot.db"
        source = sqlite3.connect(str(source_path))
        dest = sqlite3.connect(str(dest_path))
        try:
            source.backup(dest)
            dest.commit()
        finally:
            dest.close()
            source.close()
        return dest_path.read_bytes()


def _count_rows(db_bytes: bytes) -> dict[str, int]:
    counts: dict[str, int] = {}
    with tempfile.TemporaryDirectory() as tmp:
        path = Path(tmp) / "count.db"
        path.write_bytes(db_bytes)
        conn = sqlite3.connect(str(path))
        try:
            present = {row[0] for row in conn.execute("select name from sqlite_master where type='table'")}
            for table in COUNTED_TABLES:
                if table not in present:
                    continue
                try:
                    counts[table] = int(conn.execute(f"select count(*) from {table}").fetchone()[0])
                except sqlite3.Error:
                    continue
        finally:
            conn.close()
    return counts


def build_archive(
    db_url: str,
    *,
    dataset_label: str = "本地数据集",
    attachments: dict[str, bytes] | None = None,
) -> tuple[str, bytes]:
    """构造备份 zip，返回 (文件名, 内容)。"""
    db_bytes = snapshot_database(db_url)
    counts = _count_rows(db_bytes)

    files: list[dict] = [{"path": DATABASE_NAME, "size": len(db_bytes), "sha256": _sha256(db_bytes)}]
    attachment_payload = attachments or {}
    for name, blob in attachment_payload.items():
        files.append({"path": f"{ATTACHMENTS_DIR}/{name}", "size": len(blob), "sha256": _sha256(blob)})

    manifest = {
        "format": BACKUP_FORMAT,
        "version": BACKUP_VERSION,
        "created_at": datetime.now(timezone.utc).isoformat(),
        "dataset_label": dataset_label,
        "database_url_scheme": "sqlite",
        "counts": counts,
        "files": files,
        "excluded": list(EXCLUDED_ITEMS),
        "notes": [
            "简历为可重建文档（Resume Studio 以 JSON 存储，可重新渲染 PDF），数据库即完整业务数据。",
            "本备份不含模型密钥、Cookie、密码或验证码。",
        ],
    }

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False, indent=2))
        zf.writestr(DATABASE_NAME, db_bytes)
        for name, blob in attachment_payload.items():
            zf.writestr(f"{ATTACHMENTS_DIR}/{name}", blob)

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    return f"ai-career-backup-{stamp}.zip", buffer.getvalue()


def inspect_archive(blob: bytes) -> dict:
    """只读解析备份，校验清单与 SHA-256，返回预览信息（不落盘）。"""
    if not blob:
        raise local_mode.DatasetError("备份内容为空。")
    try:
        zf = zipfile.ZipFile(io.BytesIO(blob))
    except zipfile.BadZipFile as exc:
        raise local_mode.DatasetError("不是有效的备份压缩包。") from exc

    with zf:
        names = set(zf.namelist())
        if MANIFEST_NAME not in names:
            raise local_mode.DatasetError("备份缺少 manifest.json。")
        manifest = json.loads(zf.read(MANIFEST_NAME).decode("utf-8"))
        if manifest.get("format") != BACKUP_FORMAT:
            raise local_mode.DatasetError("备份格式不受支持。")

        verified: list[dict] = []
        for item in manifest.get("files", []):
            path = item.get("path", "")
            ok = False
            actual_size = 0
            if path in names:
                # 先用成员声明大小挡一道「解压炸弹」，避免无上限地把内容读进内存
                if zf.getinfo(path).file_size > MAX_MEMBER_BYTES:
                    verified.append(
                        {
                            "path": path,
                            "declared_size": item.get("size"),
                            "actual_size": zf.getinfo(path).file_size,
                            "sha256_ok": False,
                            "too_large": True,
                        }
                    )
                    continue
                data = zf.read(path)
                actual_size = len(data)
                ok = _sha256(data) == item.get("sha256")
            verified.append(
                {
                    "path": path,
                    "declared_size": item.get("size"),
                    "actual_size": actual_size,
                    "sha256_ok": ok,
                }
            )

        db_present = DATABASE_NAME in names
        counts = manifest.get("counts", {}) if db_present else {}

    return {
        "format": manifest.get("format"),
        "version": manifest.get("version"),
        "created_at": manifest.get("created_at"),
        "dataset_label": manifest.get("dataset_label"),
        "counts": counts,
        "files": verified,
        "database_present": db_present,
        "integrity_ok": bool(verified) and all(item["sha256_ok"] for item in verified) and db_present,
        "excluded": manifest.get("excluded", []),
        "notes": manifest.get("notes", []),
        "size_bytes": len(blob),
    }


def restore_as_new_dataset(blob: bytes, *, label: str | None = None) -> dict:
    """把备份恢复为一个**新的独立数据集**（不覆盖当前库），并切换指针到它。"""
    inspection = inspect_archive(blob)
    if not inspection["integrity_ok"]:
        raise local_mode.DatasetError("备份完整性校验未通过（文件缺失或 SHA-256 不匹配），已拒绝恢复。")

    root = local_mode.ensure_dirs()
    dataset_id = local_mode.new_dataset_id()
    target = local_mode.dataset_db_path(dataset_id, root)

    total_bytes = 0
    skipped_members: list[str] = []
    with zipfile.ZipFile(io.BytesIO(blob)) as zf:
        db_bytes = zf.read(DATABASE_NAME)
        if len(db_bytes) > MAX_MEMBER_BYTES:
            raise local_mode.DatasetError(f"备份中的数据库过大（>{MAX_MEMBER_BYTES} 字节），已拒绝恢复。")
        total_bytes += len(db_bytes)
        target.write_bytes(db_bytes)

        attachments_root = (root / "attachments" / dataset_id).resolve()
        for name in zf.namelist():
            rel = _safe_attachment_rel(name)
            if rel is None:
                # 路径穿越 / 非法成员名：跳过而不是写出数据集目录之外
                if name.startswith(f"{ATTACHMENTS_DIR}/") and not name.endswith("/"):
                    skipped_members.append(name)
                continue
            member_size = zf.getinfo(name).file_size
            if member_size > MAX_MEMBER_BYTES:
                raise local_mode.DatasetError(f"备份中 {name} 过大（>{MAX_MEMBER_BYTES} 字节），已拒绝恢复。")
            total_bytes += member_size
            if total_bytes > MAX_TOTAL_BYTES:
                raise local_mode.DatasetError("备份解压后体积超限（疑似解压炸弹），已拒绝恢复。")
            out = (attachments_root / rel).resolve()
            # 二次兜底：解析后的真实路径必须仍在附件目录内
            if not out.is_relative_to(attachments_root):
                skipped_members.append(name)
                continue
            out.parent.mkdir(parents=True, exist_ok=True)
            out.write_bytes(zf.read(name))

    previous = local_mode.active_dataset_id(root)
    local_mode.write_metadata(
        dataset_id,
        {
            "id": dataset_id,
            "label": label or inspection.get("dataset_label") or "恢复的数据集",
            "source": "RESTORE",
            "source_created_at": inspection.get("created_at"),
            "created_at": datetime.now(timezone.utc).isoformat(),
            "counts": inspection.get("counts", {}),
            "database_file": target.name,
        },
        root,
    )
    local_mode.set_active_dataset(dataset_id, root)

    return {
        "dataset_id": dataset_id,
        "label": label or inspection.get("dataset_label") or "恢复的数据集",
        "database_file": str(target),
        "previous_dataset_id": previous,
        "counts": inspection.get("counts", {}),
        "restored_files": len(inspection["files"]),
        "skipped_unsafe_members": skipped_members,
        "note": "已切换为恢复后的数据集；原数据集文件仍保留在本地，可随时切回。",
    }


def list_datasets() -> list[dict]:
    root = local_mode.data_root()
    if root is None:
        return []
    directory = root / local_mode.DATASETS_DIRNAME
    if not directory.exists():
        return []
    current = local_mode.active_dataset_id(root)
    items: list[dict] = []
    for path in sorted(directory.glob("*.db")):
        dataset_id = path.stem
        meta = local_mode.read_metadata(dataset_id, root)
        items.append(
            {
                "id": dataset_id,
                "label": meta.get("label") or dataset_id,
                "source": meta.get("source", "LOCAL"),
                "created_at": meta.get("created_at"),
                "counts": meta.get("counts", {}),
                "size_bytes": path.stat().st_size,
                "active": dataset_id == current,
            }
        )
    return items


__all__ = [
    "BACKUP_FORMAT",
    "BACKUP_VERSION",
    "EXCLUDED_ITEMS",
    "build_archive",
    "inspect_archive",
    "restore_as_new_dataset",
    "list_datasets",
    "snapshot_database",
]
