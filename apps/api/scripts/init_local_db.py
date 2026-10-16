"""初始化本地优先模式的数据库（稳定本地目录 + 当前模型全部表）。

用法（在 apps/api 目录下）：

    set AI_CAREER_DATA_DIR=%LOCALAPPDATA%\\AICareerOS
    set PYTHONPATH=.
    python scripts/init_local_db.py

行为：
1. 解析本地数据目录（默认 %LOCALAPPDATA%\\AICareerOS，可用 AI_CAREER_DATA_DIR 覆盖）；
2. 建好 datasets/ 子目录；
3. 若主库不存在则创建，并按当前 ORM 建全部表；已存在则只补齐缺失的表与列（不删除、不改数据）；
4. 把 alembic 版本戳到 head，便于后续 `alembic upgrade head`。
"""
from __future__ import annotations

import os
import sqlite3
import sys
from pathlib import Path

API_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(API_DIR))

from app import local_mode  # noqa: E402


def _sqlite_url(path: Path) -> str:
    return "sqlite:///" + path.as_posix()


def main() -> int:
    root = Path(os.getenv(local_mode.DATASET_ENV, "") or local_mode.default_data_root()).expanduser()
    (root / local_mode.DATASETS_DIRNAME).mkdir(parents=True, exist_ok=True)
    db_path = root / "career.db"
    os.environ.setdefault(local_mode.DATASET_ENV, str(root))
    os.environ["DATABASE_URL"] = _sqlite_url(db_path)

    from sqlalchemy import create_engine

    from app import models  # noqa: F401  注册所有模型
    from app.database import Base

    engine = create_engine(_sqlite_url(db_path), pool_pre_ping=True)

    existed = db_path.exists()
    before = _table_names(db_path) if existed else set()
    Base.metadata.create_all(engine)
    after = _table_names(db_path)

    created = sorted(after - before)
    missing = sorted(set(Base.metadata.tables) - after)

    added_columns = _sync_columns(db_path)

    _stamp_head(engine)

    print(f"[local] 数据目录: {root}")
    print(f"[local] 数据库:   {db_path} ({'已存在' if existed else '新建'})")
    print(f"[local] 新建表:   {created or '无'}")
    print(f"[local] 补列:     {added_columns or '无'}")
    print(f"[local] 缺失表:   {missing or '无'}")
    return 0 if not missing else 1


def _table_names(db_path: Path) -> set[str]:
    conn = sqlite3.connect(str(db_path))
    try:
        rows = conn.execute("select name from sqlite_master where type='table'").fetchall()
        return {row[0] for row in rows}
    finally:
        conn.close()


def _sync_columns(db_path: Path) -> list[str]:
    """给已存在的表补上缺失的列（SQLite ALTER TABLE ADD COLUMN）。"""
    from app.database import Base

    added: list[str] = []
    conn = sqlite3.connect(str(db_path))
    try:
        for table in Base.metadata.sorted_tables:
            existing = {row[1] for row in conn.execute(f"PRAGMA table_info({table.name})")}
            if not existing:
                continue
            for column in table.columns:
                if column.name in existing:
                    continue
                conn.execute(f"ALTER TABLE {table.name} ADD COLUMN {column.name} {_column_sql(column)}")
                added.append(f"{table.name}.{column.name}")
        conn.commit()
    finally:
        conn.close()
    return added


def _column_sql(column) -> str:
    type_name = column.type.__class__.__name__.upper()
    mapping = {
        "STRING": "VARCHAR",
        "TEXT": "TEXT",
        "INTEGER": "INTEGER",
        "FLOAT": "FLOAT",
        "JSON": "JSON",
        "DATETIME": "DATETIME",
        "DATE": "DATE",
        "UUID": "CHAR(36)",
        "BOOLEAN": "BOOLEAN",
    }
    sql = mapping.get(type_name, "TEXT")
    length = getattr(column.type, "length", None)
    if sql == "VARCHAR" and length:
        sql = f"VARCHAR({length})"
    return sql


def _stamp_head(engine) -> None:
    """把 alembic 版本戳到 head（表已由 create_all 建好，避免重复升级）。"""
    try:
        from alembic.config import Config
        from alembic.script import ScriptDirectory

        config = Config(str(API_DIR / "alembic.ini"))
        config.set_main_option("script_location", str(API_DIR / "alembic"))
        script = ScriptDirectory.from_config(config)
        head = script.get_current_head()
        if not head:
            return
        with engine.begin() as connection:
            connection.exec_driver_sql("CREATE TABLE IF NOT EXISTS alembic_version (version_num VARCHAR(32) NOT NULL)")
            connection.exec_driver_sql("DELETE FROM alembic_version")
            connection.exec_driver_sql("INSERT INTO alembic_version (version_num) VALUES (?)", (head,))
        print(f"[local] alembic 版本戳: {head}")
    except Exception as exc:  # noqa: BLE001 - 戳失败不影响本地使用
        print(f"[local] 跳过 alembic 版本戳: {exc}")


if __name__ == "__main__":
    raise SystemExit(main())
