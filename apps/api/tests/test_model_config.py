"""AI 模型中心：配置 CRUD、优先级、连接测试、安全与备份隔离。

全部使用 Mock Provider（不产生任何真实网络请求与费用）。
真实提供商测试默认 NOT_RUN（见 docs/model-center-test-report.md）。
"""
from __future__ import annotations

import base64
import io
import json
import zipfile

import httpx
import pytest

from app import model_config_service as service
from app import secret_store
from app import local_access
from app.local_access import CLIENT_HEADER, CLIENT_HEADER_VALUE
from app.model_config_service import ModelConfigError, ModelNotConfiguredError, ModelUnusableError

TEST_KEY = "sk-unit-test-key-0123456789"
OTHER_KEY = "sk-another-key-9876543210"
LOCAL_HEADERS = {"Origin": "http://127.0.0.1:3001", CLIENT_HEADER: CLIENT_HEADER_VALUE}
EVIL_HEADERS = {"Origin": "https://evil.example.com", CLIENT_HEADER: CLIENT_HEADER_VALUE}


@pytest.fixture(autouse=True)
def _isolated(tmp_path, monkeypatch):
    """每个用例用独立数据目录，并清掉环境变量，保证确定性。"""
    monkeypatch.setenv("AI_CAREER_DATA_DIR", str(tmp_path))
    for name in (
        "OPENAI_API_KEY",
        "OPENAI_BASE_URL",
        "OPENAI_MODEL",
        "OPENAI_RESUME_MODEL",
        "OPENAI_MISSION_MODEL",
        "OPENAI_ASSISTANT_MODEL",
        "OPENAI_TIMEOUT_SECONDS",
    ):
        monkeypatch.delenv(name, raising=False)
    monkeypatch.setenv("AI_CAREER_ALLOW_PLAINTEXT_SECRETS", "1")  # 非 Windows CI 允许明文
    service.clear_all()
    yield
    service.clear_all()


def _make_config(**overrides) -> dict:
    payload = {
        "name": "主力模型",
        "provider_id": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model_id": "deepseek-chat",
        "timeout_seconds": 60,
        "api_key": TEST_KEY,
    }
    payload.update(overrides)
    return service.create_config(payload)


# ---------------------------------------------------------------------------
# Mock Provider：可控的 OpenAI 兼容服务
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int = 200, payload: dict | None = None, text: str = "") -> None:
        self.status_code = status_code
        self._payload = payload if payload is not None else {}
        self.text = text or json.dumps(self._payload, ensure_ascii=False)

    def json(self) -> dict:
        if isinstance(self._payload, dict):
            return self._payload
        raise ValueError("not json")


class _FakeStream:
    def __init__(self, status_code: int, lines: list[str], raise_exc: BaseException | None = None) -> None:
        self.status_code = status_code
        self._lines = lines
        self._raise = raise_exc

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def iter_lines(self):
        if self._raise:
            raise self._raise
        for line in self._lines:
            yield line


class FakeClient:
    """按 scenario 返回不同行为的假客户端（记录在 cls.calls 里供断言）。"""

    scenario = "ok"
    calls: list[dict] = []

    def __init__(self, *args, **kwargs) -> None:
        pass

    def __enter__(self):
        return self

    def __exit__(self, *args) -> bool:
        return False

    def get(self, url: str, headers=None, **kwargs):
        FakeClient.calls.append({"method": "GET", "url": url, "headers": dict(headers or {})})
        if FakeClient.scenario == "auth":
            return _FakeResponse(401, {}, "unauthorized")
        if FakeClient.scenario == "unreachable":
            raise httpx.ConnectError("connect failed")
        if FakeClient.scenario == "timeout":
            raise httpx.ConnectTimeout("timeout")
        return _FakeResponse(200, {"data": [{"id": "deepseek-chat"}, {"id": "deepseek-reasoner"}]})

    def post(self, url: str, headers=None, json=None, **kwargs):
        payload = json or {}
        FakeClient.calls.append({"method": "POST", "url": url, "json": payload, "headers": dict(headers or {})})
        scenario = FakeClient.scenario
        if scenario == "auth":
            return _FakeResponse(401, {}, "unauthorized")
        if scenario == "unreachable":
            raise httpx.ConnectError("connect failed")
        if scenario == "timeout":
            raise httpx.ReadTimeout("timeout")
        if scenario == "rate_limit":
            return _FakeResponse(429, {}, "too many requests")
        if scenario == "server_error":
            return _FakeResponse(503, {}, "upstream down")
        if scenario == "stream_broken" and payload.get("stream"):
            raise httpx.RemoteProtocolError("connection closed")
        if payload.get("tools"):
            if scenario == "no_tools":
                # 有的模型直接报 400
                return _FakeResponse(400, {}, "tools not supported")
            if scenario == "no_tool_calls":
                return _FakeResponse(200, {"choices": [{"message": {"content": "我不调用工具"}}]})
            return _FakeResponse(200, {"choices": [{"message": {"tool_calls": [{"function": {"name": "ping_tool"}}]}}]})
        if payload.get("response_format"):
            if scenario == "no_json":
                return _FakeResponse(400, {}, "response_format unsupported")
            return _FakeResponse(200, {"choices": [{"message": {"content": '{"ok": true}'}}]})
        if scenario == "model_not_found":
            return _FakeResponse(404, {}, "model missing")
        return _FakeResponse(200, {"choices": [{"message": {"content": "OK"}}]})

    def stream(self, method: str, url: str, headers=None, json=None, **kwargs):
        FakeClient.calls.append({"method": "STREAM", "url": url, "json": json or {}})
        if FakeClient.scenario == "no_stream":
            return _FakeStream(400, [])
        if FakeClient.scenario == "stream_broken":
            return _FakeStream(200, [], raise_exc=httpx.RemoteProtocolError("closed"))
        if FakeClient.scenario == "timeout":
            raise httpx.ReadTimeout("timeout")
        return _FakeStream(200, ["data: {1}", "data: {2}", "data: [DONE]"])


@pytest.fixture
def fake_http(monkeypatch):
    FakeClient.calls = []
    FakeClient.scenario = "ok"
    monkeypatch.setattr(httpx, "Client", FakeClient)
    return FakeClient


def _test_payload(**overrides) -> dict:
    payload = {
        "provider_id": "deepseek",
        "base_url": "https://api.deepseek.com",
        "model_id": "deepseek-chat",
        "api_key": TEST_KEY,
        "confirm": True,
    }
    payload.update(overrides)
    return payload


# ---------------------------------------------------------------------------
# 1. 配置 CRUD 与持久化
# ---------------------------------------------------------------------------


def test_create_and_reload_after_refresh():
    created = _make_config()
    assert created["key_present"] is True
    assert created["key_masked"].endswith(TEST_KEY[-4:]) and "***" in created["key_masked"]
    assert TEST_KEY not in json.dumps(created, ensure_ascii=False)  # 响应不含明文

    reloaded = service.list_configs()
    assert len(reloaded) == 1
    assert reloaded[0]["id"] == created["id"]
    assert reloaded[0]["model_id"] == "deepseek-chat"


def test_switch_default_model():
    first = _make_config(name="A")
    second = _make_config(name="B", model_id="deepseek-reasoner")
    assert service.list_configs()[0]["is_default"] is True  # 第一个自动成为默认

    service.activate_config(second["id"])
    views = {row["id"]: row for row in service.list_configs()}
    assert views[second["id"]]["is_default"] is True
    assert views[first["id"]]["is_default"] is False

    settings = service.llm_settings("assistant")
    assert settings.config_id == second["id"]
    assert settings.model == "deepseek-reasoner"


def test_edit_without_changing_key_keeps_secret():
    created = _make_config()
    before = service.list_configs()[0]["key_fingerprint"]

    updated = service.update_config(created["id"], {"model_id": "deepseek-reasoner", "timeout_seconds": 90})
    assert updated["model_id"] == "deepseek-reasoner"
    assert updated["key_fingerprint"] == before  # 没改密钥 → 指纹不变
    assert service.llm_settings("mission").api_key == TEST_KEY


def test_replace_key_changes_fingerprint():
    created = _make_config()
    before = service.list_configs()[0]["key_fingerprint"]
    updated = service.update_config(created["id"], {"api_key": OTHER_KEY})
    assert updated["key_fingerprint"] != before
    assert service.llm_settings("mission").api_key == OTHER_KEY


def test_change_endpoint_without_new_key_blocks_usage(monkeypatch):
    """换地址却没给新密钥：不允许拿旧密钥去打新地址。"""
    monkeypatch.setattr(service.socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", ("93.184.216.34", 0))])
    created = _make_config()
    service.update_config(created["id"], {"base_url": "https://api.other.example/v1"})
    with pytest.raises(ModelUnusableError) as exc:
        service.llm_settings("mission")
    assert "重新填写" in str(exc.value)

    # 没有新密钥时，测试连接也必须拒绝（不能把旧密钥发给新地址）
    result = service.test_connection({"config_id": created["id"], "base_url": "https://api.other.example/v1", "confirm": True})
    assert result["ok"] is False
    assert result["error"]["category"] == "key_required"

    # 补上新密钥后可以恢复使用
    service.update_config(created["id"], {"api_key": OTHER_KEY})
    assert service.llm_settings("mission").api_key == OTHER_KEY


def test_delete_model_disables_key():
    created = _make_config()
    service.delete_config(created["id"])
    assert service.list_configs() == []
    with pytest.raises(ModelNotConfiguredError):
        service.llm_settings("assistant")


def test_clear_key_makes_config_unusable():
    created = _make_config()
    service.update_config(created["id"], {"clear_key": True})
    assert service.list_configs()[0]["key_present"] is False
    with pytest.raises(ModelUnusableError):
        service.llm_settings("assistant")


def test_validation_rejects_bad_fields():
    with pytest.raises(ModelConfigError):
        service.create_config({"provider_id": "deepseek", "base_url": "https://api.deepseek.com", "api_key": TEST_KEY})  # 缺模型 ID
    with pytest.raises(ModelConfigError):
        service.create_config({"provider_id": "deepseek", "base_url": "ftp://x.example", "model_id": "m", "api_key": TEST_KEY})
    with pytest.raises(ModelConfigError):
        service.create_config({"provider_id": "deepseek", "base_url": "https://api.deepseek.com", "model_id": "m"})  # 缺密钥


# ---------------------------------------------------------------------------
# 2. 连接测试（Mock Provider）
# ---------------------------------------------------------------------------


def test_connection_success_reports_capabilities(fake_http):
    result = service.test_connection(_test_payload())
    assert result["ok"] is True
    assert result["capabilities"]["chat"] is True
    assert result["capabilities"]["tools"] is True
    assert result["capabilities"]["json"] is True
    assert result["capabilities"]["streaming"] is True
    assert result["cost_note"]


def test_connection_requires_confirmation(fake_http):
    result = service.test_connection({"provider_id": "deepseek", "base_url": "https://api.deepseek.com", "model_id": "m", "api_key": TEST_KEY})
    assert result["ok"] is False
    assert result["error"]["category"] == "confirm_required"
    assert FakeClient.calls == []  # 未确认 → 不发任何请求（不产生费用）


def test_connection_bad_key(fake_http):
    FakeClient.scenario = "auth"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False
    assert result["error"]["category"] == "auth"


def test_connection_bad_url(fake_http):
    FakeClient.scenario = "unreachable"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False
    assert result["error"]["category"] == "unreachable"


def test_connection_timeout(fake_http):
    FakeClient.scenario = "timeout"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False
    assert result["error"]["category"] == "timeout"


def test_connection_rate_limit(fake_http):
    FakeClient.scenario = "rate_limit"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False
    assert result["error"]["category"] == "rate_limit"


def test_connection_service_unavailable(fake_http):
    FakeClient.scenario = "server_error"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False
    assert result["error"]["category"] == "http_error"


def test_connection_without_tool_calling(fake_http):
    FakeClient.scenario = "no_tools"
    result = service.test_connection(_test_payload())
    assert result["ok"] is True  # 对话可用，只是没有工具能力
    assert result["capabilities"]["tools"] is False


def test_connection_without_json_mode(fake_http):
    FakeClient.scenario = "no_json"
    result = service.test_connection(_test_payload())
    assert result["ok"] is True
    assert result["capabilities"]["json"] is False


def test_connection_stream_interrupted(fake_http):
    FakeClient.scenario = "stream_broken"
    result = service.test_connection(_test_payload())
    assert result["capabilities"]["streaming"] is False


def test_connection_model_not_found(fake_http):
    FakeClient.scenario = "model_not_found"
    result = service.test_connection(_test_payload())
    assert result["ok"] is False


def test_connection_does_not_leak_key_to_other_provider(fake_http):
    """改了地址没给新密钥时，绝不把原密钥发给新地址。"""
    created = _make_config()
    result = service.test_connection({"config_id": created["id"], "base_url": "https://api.deepseek.com", "confirm": True})
    sent = [(call.get("headers") or {}).get("Authorization", "") for call in FakeClient.calls]
    assert any(TEST_KEY in value for value in sent)  # 同地址 → 用原密钥

    FakeClient.calls = []
    result = service.test_connection({"config_id": created["id"], "base_url": "https://evil.example/v1", "confirm": True})
    assert result["ok"] is False
    assert FakeClient.calls == []  # 异地址且无新密钥 → 一个请求都不发


# ---------------------------------------------------------------------------
# 3. SSRF 防护
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,allowed",
    [
        ("https://api.deepseek.com", True),
        ("http://api.deepseek.com", False),  # 公网必须 HTTPS
        ("http://127.0.0.1:11434/v1", True),  # 本机 Ollama：受控例外
        ("http://localhost:11434/v1", True),
        ("http://127.0.0.1:3306", False),  # 本机敏感服务
        ("http://192.168.1.10:11434", False),  # 内网不允许
        ("http://10.0.0.5/v1", False),
        ("https://user:pw@api.deepseek.com", False),  # 带凭据
        ("file:///etc/passwd", False),
    ],
)
def test_endpoint_ssrf_rules(url, allowed):
    ok, _reason = service.validate_endpoint(url)
    assert ok is allowed


def test_private_dns_name_is_rejected(monkeypatch):
    monkeypatch.setattr(service.socket, "getaddrinfo", lambda *args, **kwargs: [(0, 0, 0, "", ("10.0.0.8", 0))])
    ok, reason = service.validate_endpoint("https://internal.example.com")
    assert ok is False
    assert "内网" in reason


# ---------------------------------------------------------------------------
# 4. 优先级：用户配置 > 环境变量 > 未配置
# ---------------------------------------------------------------------------


def test_user_config_wins_over_env(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    created = _make_config()
    settings = service.llm_settings("assistant")
    assert settings.source == "user"
    assert settings.api_key == TEST_KEY
    assert settings.model == "deepseek-chat"
    assert settings.config_id == created["id"]


def test_env_fallback_is_reported(monkeypatch):
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://gateway.example/v1")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    settings = service.llm_settings("assistant")
    assert settings.source == "env"
    assert settings.api_key == "sk-from-env"

    status = service.status()
    assert status["configured"] is True
    assert status["env_fallback_active"] is True
    assert status["env_warning"]  # 页面要提示「当前用的是 .env，不是你保存的模型」


def test_skip_model_configuration_still_usable():
    status = service.status()
    assert status["configured"] is False
    with pytest.raises(ModelNotConfiguredError) as exc:
        service.llm_settings("resume")
    assert "本地功能" in str(exc.value) or "设置" in str(exc.value)


def test_module_assignment_overrides_default():
    main_config = _make_config(name="通用")
    assistant_config = _make_config(name="顺顺专用", model_id="deepseek-reasoner")
    service.activate_config(main_config["id"])
    service.set_assignments({"assistant": assistant_config["id"]})

    assert service.llm_settings("assistant").model == "deepseek-reasoner"
    assert service.llm_settings("resume").model == "deepseek-chat"


def test_switching_config_applies_to_assistant_and_resume():
    _make_config(name="旧", model_id="model-a")
    new_config = _make_config(name="新", model_id="model-b")
    service.activate_config(new_config["id"])
    assert service.llm_settings("assistant").model == "model-b"
    assert service.llm_settings("resume").model == "model-b"


# ---------------------------------------------------------------------------
# 5. 安全：存储、备份、跨站访问
# ---------------------------------------------------------------------------


def test_secret_is_not_stored_in_plaintext():
    _make_config()
    raw = service.config_path().read_text(encoding="utf-8")
    assert TEST_KEY not in raw
    assert "sk-" not in raw  # 连服务商前缀格式都不暴露
    assert base64.b64decode(json.loads(raw)["configs"][0]["secret"]["data"])  # 密文存在


def test_config_file_lives_outside_datasets(tmp_path):
    _make_config()
    path = service.config_path()
    assert "datasets" not in path.parts
    assert path.parent == tmp_path


def test_backup_archive_has_no_key(tmp_path):
    """备份只包含数据库快照，不含任何密钥。"""
    from app import backup_service

    _make_config()
    db_path = tmp_path / "career.db"
    import sqlite3

    connection = sqlite3.connect(str(db_path))
    connection.execute("CREATE TABLE profiles (id TEXT)")
    connection.commit()
    connection.close()

    _name, blob = backup_service.build_archive(f"sqlite:///{db_path.as_posix()}")
    assert TEST_KEY.encode("utf-8") not in blob
    with zipfile.ZipFile(io.BytesIO(blob)) as archive:
        names = archive.namelist()
        assert not any("model_config" in name for name in names)
        manifest = json.loads(archive.read("manifest.json"))
    assert any("密钥" in item for item in manifest["excluded"])


def test_restoring_other_dataset_does_not_import_keys(tmp_path):
    """恢复备份 = 新建数据集；密钥不在备份里，因此也不会被带过来。"""
    from app import local_mode

    _make_config()
    own_fingerprint = service.list_configs()[0]["key_fingerprint"]

    other = local_mode.new_dataset_id()
    local_mode.set_active_dataset(other)
    # 切换数据集后，配置仍在（属于本机用户，不随数据集走），但仍是用户自己的那份
    assert service.list_configs()[0]["key_fingerprint"] == own_fingerprint
    assert service.llm_settings("assistant").api_key == TEST_KEY


def test_dpapi_failure_never_falls_back_to_plaintext(monkeypatch):
    monkeypatch.delenv("AI_CAREER_ALLOW_PLAINTEXT_SECRETS", raising=False)
    monkeypatch.setattr(service.secret_store, "is_windows", lambda: True)
    monkeypatch.setattr(service.secret_store, "_dpapi_available", lambda: True)

    def _boom(_data: bytes) -> bytes:
        raise secret_store.SecretStoreError("DPAPI 失败")

    monkeypatch.setattr(service.secret_store, "_protect", _boom)
    with pytest.raises(secret_store.SecretStoreError):
        _make_config()
    assert service.list_configs() == []  # 绝不静默保存明文


def test_unauthorized_web_page_cannot_read_or_write(client):
    _make_config()
    response = client.get("/api/v1/model-configs", headers=EVIL_HEADERS)
    assert response.status_code == 403

    response = client.post(
        "/api/v1/model-configs",
        json={"name": "x", "provider_id": "deepseek", "base_url": "https://api.deepseek.com", "model_id": "m", "api_key": "k"},
        headers=EVIL_HEADERS,
    )
    assert response.status_code == 403
    assert len(service.list_configs()) == 1  # 没被写入


def test_write_without_client_header_is_rejected(client):
    response = client.post(
        "/api/v1/model-configs",
        json={"name": "x", "provider_id": "deepseek", "base_url": "https://api.deepseek.com", "model_id": "m", "api_key": "k"},
        headers={"Origin": "http://127.0.0.1:3001"},
    )
    assert response.status_code == 403


def test_local_ui_can_manage_configs(client, fake_http):
    response = client.post(
        "/api/v1/model-configs",
        json={"name": "主力", "provider_id": "deepseek", "base_url": "https://api.deepseek.com", "model_id": "deepseek-chat", "api_key": TEST_KEY},
        headers=LOCAL_HEADERS,
    )
    assert response.status_code == 200
    body = response.json()
    assert TEST_KEY not in json.dumps(body, ensure_ascii=False)

    status = client.get("/api/v1/model-configs/status").json()
    assert status["configured"] is True
    assert status["modules"][0]["source"] == "user"

    test_response = client.post("/api/v1/model-configs/test", json=_test_payload(config_id=body["id"]), headers=LOCAL_HEADERS)
    assert test_response.status_code == 200
    assert test_response.json()["ok"] is True


def test_status_endpoint_never_returns_plaintext(client):
    _make_config()
    body = client.get("/api/v1/model-configs/status").json()
    assert TEST_KEY not in json.dumps(body, ensure_ascii=False)
    assert body["configs"][0]["key_masked"].endswith(TEST_KEY[-4:]) is False or "***" in body["configs"][0]["key_masked"]


def test_broken_user_config_falls_back_to_env_with_reason(monkeypatch):
    """用户配置坏了不能拖垮 AI：回退 .env，并把原因带到页面提示。"""
    monkeypatch.setenv("OPENAI_API_KEY", "sk-from-env")
    monkeypatch.setenv("OPENAI_MODEL", "env-model")
    _make_config()  # 默认配置
    service.update_config(service.list_configs()[0]["id"], {"clear_key": True})

    settings = service.llm_settings("assistant")
    assert settings.source == "env"
    assert settings.model == "env-model"
    assert settings.fallback_reason

    status = service.status()
    module = next(item for item in status["modules"] if item["key"] == "assistant")
    assert module["source"] == "user-broken"
    assert "回退" in module["note"]


def test_broken_user_config_without_env_raises():
    _make_config()
    service.update_config(service.list_configs()[0]["id"], {"clear_key": True})
    with pytest.raises(ModelUnusableError):
        service.llm_settings("assistant")


@pytest.mark.parametrize(
    "origin,expected",
    [
        ("http://127.0.0.1:3002", True),
        ("http://localhost:47821", True),
        ("http://[::1]:3100", True),
        ("https://evil.example.com", False),
        ("http://192.168.1.9:3000", False),
        ("http://127.0.0.1.evil.com:3000", False),
    ],
)
def test_loopback_ports_are_trusted_but_lan_and_hostnames_are_not(origin, expected):
    """端口漂移（3001/3002…）不影响本机使用，但局域网和伪装主机名必须拒绝。"""
    assert local_access.is_trusted_origin(origin) is expected


def test_frontend_cors_allows_drifted_loopback_port(client):
    """前端被挤到任意端口后预检仍要通过，否则整页 Failed to fetch。"""
    response = client.options(
        "/api/v1/model-configs/status",
        headers={
            "Origin": "http://127.0.0.1:47821",
            "Access-Control-Request-Method": "GET",
        },
    )
    assert response.headers.get("access-control-allow-origin") == "http://127.0.0.1:47821"
