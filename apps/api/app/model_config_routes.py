"""AI 模型中心路由（设置 → AI 模型）。

安全约定：
- 列表 / 状态接口**只返回脱敏元数据**（masked / fingerprint），永远不返回密钥明文；
- 写接口（增 / 改 / 删 / 激活 / 测试）都要过 :func:`app.local_access.assert_trusted_request`；
- 测试连接必须显式 ``confirm=true``（页面不自动触发，避免产生费用）。
"""
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel, Field

from . import model_config_service as service
from . import secret_store
from .local_access import CLIENT_HEADER, CLIENT_HEADER_VALUE, assert_trusted_request

router = APIRouter(prefix="/api/v1")


class ConfigIn(BaseModel):
    name: str = ""
    provider_id: str = ""
    base_url: str | None = None
    model_id: str = ""
    timeout_seconds: float = 60
    api_key: str | None = None
    clear_key: bool = False
    enabled: bool = True


class ActivateIn(BaseModel):
    config_id: str


class TestIn(BaseModel):
    config_id: str | None = None
    provider_id: str | None = None
    base_url: str | None = None
    model_id: str | None = None
    api_key: str | None = None
    timeout_seconds: float | None = None
    confirm: bool = False
    probe_tools: bool = True
    probe_stream: bool = True


class AssignmentsIn(BaseModel):
    assignments: dict[str, str] = Field(default_factory=dict)


def _guard(request: Request) -> None:
    assert_trusted_request(request)


def _error(exc: BaseException) -> HTTPException:
    if isinstance(exc, service.ModelConfigError):
        return HTTPException(400, str(exc))
    if isinstance(exc, service.ModelUnusableError):
        return HTTPException(409, str(exc))
    if isinstance(exc, secret_store.SecretStoreError):
        return HTTPException(500, f"密钥处理失败：{exc}")
    if isinstance(exc, service.ModelNotConfiguredError):
        return HTTPException(503, str(exc))
    raise exc


@router.get("/model-configs/status")
def read_status(request: Request) -> dict:
    _guard(request)
    return service.status()


@router.get("/model-configs")
def read_configs(request: Request) -> dict:
    _guard(request)
    return {"configs": service.list_configs(), "client_header": {"name": CLIENT_HEADER, "value": CLIENT_HEADER_VALUE}}


@router.post("/model-configs")
def create(payload: ConfigIn, request: Request) -> dict:
    _guard(request)
    try:
        return service.create_config(payload.model_dump())
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc


@router.patch("/model-configs/{config_id}")
def update(config_id: str, payload: ConfigIn, request: Request) -> dict:
    _guard(request)
    data = payload.model_dump(exclude_unset=True)
    try:
        return service.update_config(config_id, data)
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc


@router.delete("/model-configs/{config_id}")
def remove(config_id: str, request: Request) -> dict:
    _guard(request)
    try:
        return service.delete_config(config_id)
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc


@router.post("/model-configs/{config_id}/activate")
def activate(config_id: str, request: Request) -> dict:
    _guard(request)
    try:
        return service.activate_config(config_id)
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc


@router.put("/model-configs/assignments")
def assign(payload: AssignmentsIn, request: Request) -> dict:
    _guard(request)
    try:
        return service.set_assignments(payload.assignments)
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc


@router.post("/model-configs/test")
def test(payload: TestIn, request: Request) -> dict:
    _guard(request)
    try:
        return service.test_connection(payload.model_dump())
    except BaseException as exc:  # noqa: BLE001
        raise _error(exc) from exc
