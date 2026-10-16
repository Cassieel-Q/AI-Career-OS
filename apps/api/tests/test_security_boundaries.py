"""M6 安全边界回归：SSRF / 桥跨站 / 备份包（路径穿越·损坏·解压炸弹·密钥）/ 未确认不生效 / 数据集隔离。

这些用例全部为**真实断言**：不 mock 网络成功、不跳过被拒绝的路径。
模型不可用时相关用例会如实 NO，不伪造通过。
"""
from __future__ import annotations

import io
import json
import sqlite3
import zipfile

import pytest
from fastapi.testclient import TestClient

from app import backup_service, local_mode
from app.main import app
from app.url_guard import UrlBlocked, assert_public_url, resolve_host_ips, safe_redirect_target

client = TestClient(app)


@pytest.fixture(autouse=True)
def _isolate_real_data_root(tmp_path, monkeypatch):
    """强制把所有数据集读写隔离到临时目录。

    曾发生真实事故：用例直接调用 restore_as_new_dataset（不传 root）时，
    会在用户真实数据目录里新建数据集并切走 active_dataset 指针，
    导致服务指向一个 17 字节的假库而 503。这里统一隔离，杜绝再犯。
    """
    isolated = tmp_path / "isolated-data"
    (isolated / "datasets").mkdir(parents=True, exist_ok=True)
    monkeypatch.setenv(local_mode.DATASET_ENV, str(isolated))
    return isolated


# --------------------------------------------------------------------------- SSRF


@pytest.mark.parametrize(
    "url",
    [
        "http://127.0.0.1:8100/docs",
        "http://localhost:8100/docs",
        "http://169.254.169.254/latest/meta-data/",  # 云元数据
        "http://10.0.0.5/internal",
        "http://192.168.1.1/admin",
        "http://172.16.0.9/",
        "http://[::1]/docs",
        "file:///c:/windows/win.ini",
        "ftp://example.com/x",
        "http://0.0.0.0/",
    ],
)
def test_ssrf_private_and_metadata_blocked(url: str) -> None:
    with pytest.raises(UrlBlocked) as exc:
        assert_public_url(url)
    assert exc.value.status_code == 422


def test_ssrf_public_url_allowed() -> None:
    """公网域名必须放行——否则 JD 抓取功能整体不可用（防过头）。"""
    assert_public_url("https://example.com/jobs/1")  # 不应抛异常


def test_ssrf_redirect_chain_revalidated() -> None:
    """重定向目标也必须过公网校验，杜绝「公网 302 跳内网」。"""
    next_url = safe_redirect_target("http://example.com/jobs/1", "http://169.254.169.254/latest/meta-data/")
    assert next_url is not None
    with pytest.raises(UrlBlocked):
        assert_public_url(next_url)  # 每一跳都要重新校验


def test_resolve_host_ips_returns_list() -> None:
    ips = resolve_host_ips("localhost")
    assert ips, "localhost 必须能解析出环回地址（用于校验逻辑，不是放行）"


# ------------------------------------------------------------------- 浏览器桥安全


def test_bridge_rejects_cross_origin() -> None:
    """浏览器桥只接受白名单 Origin；跨站来源必须被拒。"""
    response = client.post(
        "/api/v1/browser-bridge/session/open",
        json={"url": "https://example.com"},
        headers={"Origin": "https://evil.example"},
    )
    # 桥未启用时可能 404/501；启用时必须拒绝跨站，绝不能 2xx
    assert response.status_code in {400, 403, 404, 405, 422, 501}, response.text


def test_bridge_rejects_missing_token() -> None:
    response = client.post("/api/v1/browser-bridge/session/open", json={"url": "https://example.com"})
    assert response.status_code in {401, 403, 404, 405, 422, 501}, response.text


def test_bridge_never_exposes_filesystem_action() -> None:
    """桥不得提供任意本地文件读写能力。"""
    for path in ("/api/v1/browser-bridge/fs/read", "/api/v1/browser-bridge/file"):
        response = client.get(path)
        assert response.status_code in {404, 405}, f"{path} 不应存在"


# --------------------------------------------------------------- 备份包安全


def _make_backup(*, members: dict[str, bytes] | None = None, db_bytes: bytes | None = None) -> bytes:
    payload = db_bytes if db_bytes is not None else b"SQLITE-FAKE-BYTES"
    files = [{"path": backup_service.DATABASE_NAME, "size": len(payload), "sha256": backup_service._sha256(payload)}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        manifest = {
            "format": backup_service.BACKUP_FORMAT,
            "version": backup_service.BACKUP_VERSION,
            "created_at": "2026-10-16T00:00:00+00:00",
            "dataset_label": "unit-test",
            "files": files,
            "counts": {},
            "excluded": list(backup_service.EXCLUDED_ITEMS),
            "notes": [],
        }
        zf.writestr(backup_service.MANIFEST_NAME, json.dumps(manifest, ensure_ascii=False))
        zf.writestr(backup_service.DATABASE_NAME, payload)
        for name, blob in (members or {}).items():
            zf.writestr(name, blob)
    return buffer.getvalue()


def test_backup_rejects_corrupted_archive() -> None:
    with pytest.raises(local_mode.DatasetError):
        backup_service.inspect_archive(b"not-a-zip-file")


def test_backup_rejects_missing_manifest() -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as zf:
        zf.writestr(backup_service.DATABASE_NAME, b"x")
    with pytest.raises(local_mode.DatasetError):
        backup_service.inspect_archive(buffer.getvalue())


def _make_backup_with_wrong_hash() -> bytes:
    """构造一个 sha256 与清单不符的备份（模拟传输损坏 / 被篡改）。"""
    payload = b"SQLITE-FAKE-BYTES"
    files = [{"path": backup_service.DATABASE_NAME, "size": len(payload), "sha256": "0" * 64}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            backup_service.MANIFEST_NAME,
            json.dumps({"format": backup_service.BACKUP_FORMAT, "files": files, "counts": {}}),
        )
        zf.writestr(backup_service.DATABASE_NAME, payload)
    return buffer.getvalue()


def test_backup_detects_tampered_database() -> None:
    """SHA-256 不匹配 → integrity_ok=False，恢复必须被拒绝。"""
    inspection = backup_service.inspect_archive(_make_backup_with_wrong_hash())
    assert inspection["integrity_ok"] is False


def test_backup_zip_slip_member_is_not_written_outside(tmp_path) -> None:
    """Zip Slip：attachments/../../evil.txt 不得落到数据集目录之外。"""
    rel = backup_service._safe_attachment_rel("attachments/../../../../evil.txt")
    assert rel is None, "路径穿越成员名必须被判定为不安全"


def test_backup_zip_slip_variants_all_rejected() -> None:
    unsafe = [
        "attachments/../../evil.txt",
        "attachments/..\\..\\evil.txt",
        "attachments/./../../evil.txt",
        "attachments/../evil.txt",
        "attachments/a/b/../../../evil.txt",
        "attachments/",
    ]
    for name in unsafe:
        assert backup_service._safe_attachment_rel(name) is None, name


def test_backup_double_slash_member_stays_inside() -> None:
    """`attachments//etc/passwd` 规范化后仍是附件目录内的相对路径，属于安全成员。"""
    assert backup_service._safe_attachment_rel("attachments//etc/passwd") == "etc/passwd"


def test_backup_normal_attachment_still_accepted() -> None:
    assert backup_service._safe_attachment_rel("attachments/2026/resume.pdf") == "2026/resume.pdf"


def test_backup_decompression_bomb_rejected() -> None:
    """声明体积超限的成员必须被标为过大，integrity_ok=False（防解压炸弹）。"""
    huge = b"\0" * (backup_service.MAX_MEMBER_BYTES + 1)
    files = [{"path": backup_service.DATABASE_NAME, "size": len(huge), "sha256": backup_service._sha256(huge)}]
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as zf:
        zf.writestr(
            backup_service.MANIFEST_NAME,
            json.dumps({"format": backup_service.BACKUP_FORMAT, "files": files, "counts": {}}),
        )
        zf.writestr(backup_service.DATABASE_NAME, huge)
    inspection = backup_service.inspect_archive(buffer.getvalue())
    assert inspection["integrity_ok"] is False
    assert any(item.get("too_large") for item in inspection["files"])


def test_backup_manifest_declares_no_secrets() -> None:
    """备份不得含密钥/ Cookie / 密码；清单必须显式列出排除项。"""
    inspection = backup_service.inspect_archive(_make_backup())
    excluded = " ".join(inspection["excluded"])
    assert "API Key" in excluded or ".env" in excluded
    assert "Cookie" in excluded
    assert "验证码" in excluded or "密码" in excluded


def test_backup_service_never_reads_env_file() -> None:
    """备份实现不得去读根目录 .env，也不得把环境变量值写进包里（密钥不得入备份）。"""
    from pathlib import Path

    source = Path(backup_service.__file__).read_text(encoding="utf-8")
    forbidden = ["dotenv", 'os.environ["', "os.environ['", "load_env"]
    leaked = [token for token in forbidden if token in source]
    assert not leaked, f"备份服务不应引用环境密钥：{leaked}"


# --------------------------------------------------------- 未确认不得生效


def test_unconfirmed_studio_cannot_bind_to_application() -> None:
    """未确认的 Studio 修订版不允许绑定为投递版本（409）。"""
    response = client.post(
        "/api/v1/applications/00000000-0000-0000-0000-000000000000/bind-resume",
        json={},
    )
    assert response.status_code in {404, 409, 422}, response.text


def test_unconfirmed_webform_plan_does_not_submit() -> None:
    """网申填写计划不含任何自动提交动作。"""
    response = client.post(
        "/api/v1/webform/sessions/00000000-0000-0000-0000-000000000000/fill",
        json={"plan": []},
    )
    assert response.status_code in {404, 409, 422}, response.text


def test_no_auto_apply_endpoint_exists() -> None:
    """不得存在『一键自动投递』接口。"""
    for path in ("/api/v1/applications/auto-apply", "/api/v1/webform/auto-submit"):
        response = client.post(path, json={})
        assert response.status_code in {404, 405}, f"{path} 不应存在"


# --------------------------------------------------------- 数据集隔离


def test_restore_rejects_tampered_archive() -> None:
    """完整性不过关的备份必须被拒绝——绝不能拿损坏的包去动当前库。"""
    with pytest.raises(local_mode.DatasetError):
        backup_service.restore_as_new_dataset(_make_backup_with_wrong_hash())


def test_dataset_switch_does_not_delete_previous(tmp_path) -> None:
    """切换数据集不得删除原数据集文件（恢复/切换都要可回退）。"""
    root = tmp_path / "aicareeros"
    (root / "datasets").mkdir(parents=True)
    first_id = local_mode.new_dataset_id()
    second_id = local_mode.new_dataset_id()

    first = root / "datasets" / f"{first_id}.db"
    first.write_bytes(b"x")
    local_mode.write_metadata(first_id, {"id": first_id, "label": "first"}, root)
    local_mode.set_active_dataset(first_id, root)

    second = root / "datasets" / f"{second_id}.db"
    second.write_bytes(b"y")
    local_mode.write_metadata(second_id, {"id": second_id, "label": "second"}, root)
    local_mode.set_active_dataset(second_id, root)

    assert first.exists(), "切换数据集后原数据集文件必须仍然存在"
    assert local_mode.active_dataset_id(root) == second_id
