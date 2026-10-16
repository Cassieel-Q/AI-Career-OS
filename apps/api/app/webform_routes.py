"""网申填表路由：读取表单 → 匹配资料 → 预览 → 用户确认填写 → 记录历史。

安全约束（硬性）：
- 只在用户显式启动的本地受控浏览器会话里操作；
- **永不点击最终提交**；不填写密码 / 验证码；
- 填表历史**只记录字段名与值来源**，不记录任何凭据。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from . import webform_browser as browser
from . import webform_matching as matching
from .application_profile_service import application_fill_facts
from .database import get_db

router = APIRouter(prefix="/api/v1")

#: 这些控件类型在写入前被再次拦截（双保险，浏览器桥里也拦一次）。
_NEVER_FILL = {"password", "hidden", "submit", "button", "captcha"}


class SessionStartRequest(BaseModel):
    url: str | None = None


class SessionOpenRequest(BaseModel):
    url: str = Field(min_length=4)


class Assignment(BaseModel):
    model_config = ConfigDict(extra="ignore")

    index: int | None = None
    selector: str = ""
    control: str = "text"
    label: str = ""
    value: str = ""


class FillRequest(BaseModel):
    page_url: str = ""
    page_title: str | None = None
    assignments: list[Assignment] = Field(default_factory=list)


@router.get("/webform/status")
def webform_status() -> dict:
    return browser.health()


@router.post("/webform/session/start")
def webform_session_start(payload: SessionStartRequest) -> dict:
    try:
        return browser.start_session(payload.url)
    except browser.BrowserBridgeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/webform/session/open")
def webform_session_open(payload: SessionOpenRequest) -> dict:
    try:
        return browser.open_url(payload.url)
    except browser.BrowserBridgeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.post("/webform/session/close")
def webform_session_close() -> dict:
    try:
        return browser.close_session()
    except browser.BrowserBridgeError as exc:
        raise HTTPException(409, str(exc)) from exc


@router.get("/profiles/{profile_id}/webform/read")
def webform_read(profile_id: UUID, db: Session = Depends(get_db)) -> dict:
    """读取当前受控浏览器页面的表单，并用已保存资料生成填写计划（预览）。"""
    try:
        page = browser.read_page()
    except browser.BrowserBridgeError as exc:
        raise HTTPException(409, str(exc)) from exc

    facts = application_fill_facts(db, profile_id)
    plan = matching.build_plan(page.get("fields", []), facts)

    # 已保存资料里可用的字段概览（用于界面提示「哪些资料会发送」）。
    sensitive_keys = {"id_number", "family_info", "health_status", "archive_location", "emergency_contact", "emergency_phone", "availability"}
    available = set(plan["fact_keys_available"])
    return {
        "page_url": page.get("pageUrl", ""),
        "page_title": page.get("pageTitle", ""),
        "fields": page.get("fields", []),
        "plans": plan["plans"],
        "summary": plan["summary"],
        "fact_keys_available": sorted(available),
        "sensitive_keys_used": sorted(available & sensitive_keys),
        "note": "仅在你点击「执行填写」后才会写入页面；系统永不点击最终提交按钮。",
    }


@router.post("/profiles/{profile_id}/webform/fill")
def webform_fill(profile_id: UUID, payload: FillRequest, db: Session = Depends(get_db)) -> dict:
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise HTTPException(404, "档案不存在")

    accepted: list[dict] = []
    rejected: list[dict] = []
    for item in payload.assignments:
        control = (item.control or "text").lower()
        if control in _NEVER_FILL:
            rejected.append({"label": item.label, "control": control, "reason": "该控件类型永不自动填写"})
            continue
        if not (item.value or "").strip():
            rejected.append({"label": item.label, "control": control, "reason": "值为空，已跳过"})
            continue
        accepted.append(
            {
                "index": item.index,
                "selector": item.selector,
                "control": control,
                "label": item.label,
                "value": item.value,
            }
        )

    if not accepted:
        raise HTTPException(422, "没有可执行填写的字段（可能全被跳过或为空）。")

    try:
        result = browser.fill_page(accepted)
    except browser.BrowserBridgeError as exc:
        record = models.WebFormRecord(
            profile_id=profile_id,
            page_url=payload.page_url[:1024],
            page_title=payload.page_title,
            status="FAILED",
            assignments=accepted,
            summary={"total": len(accepted), "filled": 0, "failed": len(accepted)},
            notes=str(exc),
        )
        db.add(record)
        db.commit()
        raise HTTPException(409, str(exc)) from exc

    filled = [item for item in result.get("results", []) if item.get("ok")]
    failed = [item for item in result.get("results", []) if not item.get("ok")]
    summary = {
        "total": len(accepted),
        "filled": len(filled),
        "failed": len(failed) + len(rejected),
        "skipped": len(rejected),
        "submitted": False,
    }
    record = models.WebFormRecord(
        profile_id=profile_id,
        page_url=(result.get("pageUrl") or payload.page_url)[:1024],
        page_title=result.get("pageTitle") or payload.page_title,
        status="FILLED" if filled else "FAILED",
        assignments=[*result.get("results", []), *rejected],
        summary=summary,
        notes="仅填写，未提交；请人工复核后再自行提交。",
    )
    db.add(record)
    db.commit()
    db.refresh(record)

    return {
        "record_id": str(record.id),
        "page_url": record.page_url,
        "page_title": record.page_title,
        "results": result.get("results", []),
        "rejected": rejected,
        "summary": summary,
        "note": "填写完成，**未提交**。系统不会点击提交按钮，请自行核对后手动提交。",
    }


@router.get("/profiles/{profile_id}/webform/records")
def webform_records(profile_id: UUID, limit: int = 20, db: Session = Depends(get_db)) -> dict:
    rows = db.scalars(
        select(models.WebFormRecord)
        .where(models.WebFormRecord.profile_id == profile_id)
        .order_by(models.WebFormRecord.created_at.desc())
        .limit(max(1, min(limit, 100)))
    ).all()
    return {
        "records": [
            {
                "id": str(row.id),
                "page_url": row.page_url,
                "page_title": row.page_title,
                "status": row.status,
                "summary": row.summary,
                "assignments": row.assignments,
                "notes": row.notes,
                "created_at": row.created_at.isoformat() if row.created_at else None,
            }
            for row in rows
        ]
    }
