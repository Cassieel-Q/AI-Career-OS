"""本地数据集 / 备份导出恢复测试。

真实验证「建立数据 → 导出 → 重启(新引擎) → 导入 → 核对记录」链路。
"""
from __future__ import annotations

import os
from pathlib import Path

import pytest

from app import backup_service, local_mode
from app.database import Base


def _seed_database(path: Path) -> None:
    from sqlalchemy import create_engine
    from sqlalchemy.orm import Session

    from app import models

    engine = create_engine(f"sqlite:///{path.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        profile = models.UserProfile(full_name="测试用户", phone="13800000000", email="t@example.com", city="上海")
        session.add(profile)
        session.commit()
        session.add(
            models.CandidateJob(
                profile_id=profile.id,
                source_text="公司：示例公司\n职位：AI 产品经理",
                source_hash="h",
                source_excerpt="示例公司 AI 产品经理",
                source_excerpt_hash="eh",
                company="示例公司",
                role="AI 产品经理",
                location="上海",
            )
        )
        session.commit()
    engine.dispose()


@pytest.fixture
def data_root(tmp_path, monkeypatch):
    root = tmp_path / "localdata"
    monkeypatch.setenv(local_mode.DATASET_ENV, str(root))
    root.mkdir(parents=True, exist_ok=True)
    (root / "datasets").mkdir(parents=True, exist_ok=True)
    return root


def test_export_contains_manifest_and_sha256(tmp_path, data_root):
    db_path = tmp_path / "main.db"
    _seed_database(db_path)

    filename, blob = backup_service.build_archive(f"sqlite:///{db_path.as_posix()}", dataset_label="测试集")
    assert filename.startswith("ai-career-backup-") and filename.endswith(".zip")
    assert len(blob) > 1000

    info = backup_service.inspect_archive(blob)
    assert info["integrity_ok"] is True
    assert info["database_present"] is True
    assert info["counts"]["user_profiles"] == 1
    assert info["counts"]["candidate_jobs"] == 1
    assert all(item["sha256_ok"] for item in info["files"])
    assert any("env" in item for item in info["excluded"]) or info["excluded"]


def test_export_excludes_secrets(monkeypatch, tmp_path, data_root):
    db_path = tmp_path / "main.db"
    _seed_database(db_path)
    monkeypatch.setenv("OPENAI_API_KEY", "sk-should-not-appear")
    _filename, blob = backup_service.build_archive(f"sqlite:///{db_path.as_posix()}")
    assert b"sk-should-not-appear" not in blob
    info = backup_service.inspect_archive(blob)
    assert "api key" in " ".join(info["excluded"]).lower() or info["excluded"]


def test_restore_creates_new_dataset_without_overwriting(tmp_path, data_root):
    db_path = tmp_path / "main.db"
    _seed_database(db_path)
    _filename, blob = backup_service.build_archive(f"sqlite:///{db_path.as_posix()}", dataset_label="源数据集")

    # 恢复前先有一个「当前」数据集，确认恢复不会覆盖它
    (data_root / "datasets" / "ds00000000aa.db").write_bytes(b"existing")
    local_mode.set_active_dataset("ds00000000aa", data_root)

    result = backup_service.restore_as_new_dataset(blob, label="恢复数据集")
    new_id = result["dataset_id"]
    new_path = Path(result["database_file"])
    assert new_path.exists()
    assert new_path.name == f"{new_id}.db"
    assert result["previous_dataset_id"] == "ds00000000aa"

    # 原来的数据集文件仍在
    assert (data_root / "datasets" / "ds00000000aa.db").read_bytes() == b"existing"
    # 指针已切到新数据集
    assert local_mode.active_dataset_id(data_root) == new_id

    # 新数据集里的记录与导出前一致
    import sqlite3

    conn = sqlite3.connect(str(new_path))
    try:
        assert conn.execute("select count(*) from user_profiles").fetchone()[0] == 1
        assert conn.execute("select count(*) from candidate_jobs").fetchone()[0] == 1
        assert conn.execute("select full_name from user_profiles").fetchone()[0] == "测试用户"
    finally:
        conn.close()


def test_restore_rejects_tampered_archive(tmp_path, data_root):
    db_path = tmp_path / "main.db"
    _seed_database(db_path)
    _filename, blob = backup_service.build_archive(f"sqlite:///{db_path.as_posix()}")

    import io
    import zipfile

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf, zipfile.ZipFile(io.BytesIO(blob)) as src:
        for name in src.namelist():
            data = src.read(name)
            if name == "data/career.db":
                data = data + b"tampered"
            zf.writestr(name, data)
    tampered = buffer.getvalue()

    info = backup_service.inspect_archive(tampered)
    assert info["integrity_ok"] is False
    with pytest.raises(local_mode.DatasetError):
        backup_service.restore_as_new_dataset(tampered)


def test_resolve_database_url_switches_with_pointer(tmp_path, data_root, monkeypatch):
    monkeypatch.setenv("DATABASE_URL", f"sqlite:///{(tmp_path / 'base.db').as_posix()}")
    assert local_mode.resolve_database_url().endswith("base.db")

    dataset = data_root / "datasets" / "ds11111111bb.db"
    dataset.write_bytes(b"x")
    local_mode.set_active_dataset("ds11111111bb", data_root)
    assert local_mode.resolve_database_url().endswith("ds11111111bb.db")


def test_local_mode_disabled_falls_back_to_env(tmp_path, monkeypatch):
    monkeypatch.delenv(local_mode.DATASET_ENV, raising=False)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///only-env.db")
    assert local_mode.resolve_database_url() == "sqlite:///only-env.db"
    assert local_mode.data_root() is None


def test_list_datasets_reports_active(data_root):
    (data_root / "datasets" / "ds22222222cc.db").write_bytes(b"x")
    local_mode.write_metadata("ds22222222cc", {"id": "ds22222222cc", "label": "我的数据集", "source": "LOCAL"}, data_root)
    local_mode.set_active_dataset("ds22222222cc", data_root)
    items = backup_service.list_datasets()
    assert any(item["id"] == "ds22222222cc" and item["active"] for item in items)
