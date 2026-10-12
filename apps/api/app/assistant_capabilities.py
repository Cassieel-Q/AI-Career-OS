"""助手写入安全（目标七）：能力目录 + 提案 + 回执。

三层：
- ``CapabilityCatalog``：声明助手能做哪些**写**操作，每个能力带参数 schema（Pydantic 校验）
  与权限标记（是否可写、是否敏感）；
- ``WriteProposal``：助手要写数据时**先产提案**（status=PROPOSED），此时**不写目标数据**；
- ``WriteReceipt``：用户确认 → 执行 → 生成回执（做了什么、改了哪条、时间、来源）。

硬约束：
- 不提供删除类能力（本模块只有 create_* 三个）；
- 参数校验复用 Pydantic 模型（与 HTTP 层同一套字段约束语义）；
- 来源可回溯到 conversation / message / profile。
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from typing import Any

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

ALLOWED_ROUNDS = ("一面", "二面", "三面", "其他")


class _Strict(BaseModel):
    model_config = ConfigDict(extra="ignore")


class CreateInterviewExperienceArgs(_Strict):
    """记一条面经（面试记录）。

    与 HTTP ``InterviewRecordCreate`` 共用字段约束（公司必填、轮次受控）；助手版不含
    逐题 items——面经正文写入 notes，后续可在「面试」页补题。
    """

    company: str = Field(min_length=1, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    round: str = Field(default="其他", max_length=64)
    date: str | None = Field(default=None, max_length=32)
    notes: str | None = Field(default=None, max_length=8_000)

    @field_validator("company", "round", mode="before")
    @classmethod
    def strip_required(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value

    @field_validator("role", "notes", "date", mode="before")
    @classmethod
    def strip_optional(cls, value: object) -> object:
        if isinstance(value, str):
            return value.strip() or None
        return value


class CreateReferralArgs(_Strict):
    company: str = Field(min_length=1, max_length=255)
    contact: str | None = Field(default=None, max_length=255)
    channel: str | None = Field(default=None, max_length=128)
    note: str | None = Field(default=None, max_length=2_000)

    @field_validator("company", mode="before")
    @classmethod
    def strip_company(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


class CreateReminderArgs(_Strict):
    title: str = Field(min_length=1, max_length=255)
    due_at: str | None = Field(default=None, max_length=32)

    @field_validator("title", mode="before")
    @classmethod
    def strip_title(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def _parse_date(text: str | None):
    if not text:
        return None
    for fmt in ("%Y-%m-%d", "%Y/%m/%d", "%Y年%m月%d日"):
        try:
            return datetime.strptime(text.strip(), fmt).date()
        except ValueError:
            continue
    return None


def _parse_datetime(text: str | None):
    if not text:
        return None
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d", "%Y/%m/%d %H:%M", "%Y年%m月%d日"):
        try:
            return datetime.strptime(text.strip(), fmt)
        except ValueError:
            continue
    return None


@dataclass
class Capability:
    name: str
    description: str
    args_model: type[BaseModel]
    target_table: str
    sensitive: bool
    summary: Any  # Callable[[BaseModel], str]
    execute: Any  # Callable[[Session, Any, BaseModel], tuple[str, dict]]


# ---------------------------------------------------------------------------
# 各能力的执行体：返回 (target_id, diff)
# ---------------------------------------------------------------------------


def _execute_interview(db: Session, profile_id: Any, args: CreateInterviewExperienceArgs) -> tuple[str, dict]:
    interviewed_on = _parse_date(args.date) or date.today()
    row = models.InterviewRecord(
        profile_id=profile_id,
        company=args.company,
        role=args.role,
        interview_round=args.round,
        interviewed_on=interviewed_on,
        notes=args.notes,
        status="DRAFT",
    )
    db.add(row)
    db.flush()
    diff = {"company": args.company, "role": args.role, "round": args.round, "interviewed_on": interviewed_on.isoformat()}
    return str(row.id), diff


def _execute_referral(db: Session, profile_id: Any, args: CreateReferralArgs) -> tuple[str, dict]:
    row = models.Referral(
        profile_id=profile_id,
        company=args.company,
        contact=args.contact,
        channel=args.channel,
        note=args.note,
    )
    db.add(row)
    db.flush()
    diff = {"company": args.company, "contact": args.contact, "channel": args.channel}
    return str(row.id), diff


def _execute_reminder(db: Session, profile_id: Any, args: CreateReminderArgs) -> tuple[str, dict]:
    row = models.Reminder(profile_id=profile_id, title=args.title, due_at=_parse_datetime(args.due_at))
    db.add(row)
    db.flush()
    diff = {"title": args.title, "due_at": row.due_at.isoformat() if row.due_at else None}
    return str(row.id), diff


_CAPABILITIES: dict[str, Capability] = {
    "create_interview_experience": Capability(
        name="create_interview_experience",
        description="记一条面经（面试记录）。用户明确要求时才提案。",
        args_model=CreateInterviewExperienceArgs,
        target_table="interview_records",
        sensitive=False,
        summary=lambda a: f"记面经：{a.company} {a.role or ''} {a.round}".strip(),
        execute=_execute_interview,
    ),
    "create_referral": Capability(
        name="create_referral",
        description="记一条内推记录。用户明确要求时才提案。",
        args_model=CreateReferralArgs,
        target_table="referrals",
        sensitive=False,
        summary=lambda a: f"记内推：{a.company}",
        execute=_execute_referral,
    ),
    "create_reminder": Capability(
        name="create_reminder",
        description="记一条求职提醒。时间必须来自用户原话。",
        args_model=CreateReminderArgs,
        target_table="reminders",
        sensitive=False,
        summary=lambda a: f"记提醒：{a.title}",
        execute=_execute_reminder,
    ),
}


def capability_catalog() -> list[dict[str, Any]]:
    """对外暴露的能力目录（含参数 JSON schema 与权限标记）。"""
    catalog: list[dict[str, Any]] = []
    for cap in _CAPABILITIES.values():
        catalog.append(
            {
                "name": cap.name,
                "description": cap.description,
                "target_table": cap.target_table,
                "sensitive": cap.sensitive,
                "parameters": cap.args_model.model_json_schema(),
            }
        )
    return catalog


def get_capability(name: str) -> Capability:
    cap = _CAPABILITIES.get(name)
    if cap is None:
        raise HTTPException(422, f"未知能力：{name}（不提供删除类能力）。")
    return cap


def validate_args(name: str, args: dict[str, Any]) -> BaseModel:
    cap = get_capability(name)
    return cap.args_model.model_validate(args or {})


# ---------------------------------------------------------------------------
# 提案 / 回执
# ---------------------------------------------------------------------------

PROPOSAL_STATUSES = ("PROPOSED", "CONFIRMED", "REJECTED", "EXECUTED")


def propose_write(
    db: Session,
    name: str,
    args: dict[str, Any],
    *,
    conversation_id: Any = None,
    message_id: Any = None,
    profile_id: Any = None,
) -> models.WriteProposal:
    """生成写入提案：校验参数后落 status=PROPOSED 的提案，**不写目标数据**。"""
    cap = get_capability(name)
    parsed = cap.args_model.model_validate(args or {})
    row = models.WriteProposal(
        conversation_id=conversation_id,
        message_id=message_id,
        profile_id=profile_id,
        capability=name,
        args=parsed.model_dump(mode="json"),
        summary=cap.summary(parsed),
        status="PROPOSED",
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_proposals(db: Session, *, conversation_id: Any = None, status: str | None = None) -> list[models.WriteProposal]:
    stmt = select(models.WriteProposal).order_by(models.WriteProposal.created_at.asc())
    if conversation_id is not None:
        stmt = stmt.where(models.WriteProposal.conversation_id == conversation_id)
    if status is not None:
        stmt = stmt.where(models.WriteProposal.status == status)
    return list(db.scalars(stmt).all())


def get_proposal(db: Session, proposal_id: Any) -> models.WriteProposal:
    row = db.get(models.WriteProposal, proposal_id)
    if row is None:
        raise HTTPException(404, "写入提案不存在。")
    return row


def confirm_proposal(db: Session, proposal_id: Any, *, profile_id: Any = None) -> models.WriteReceipt:
    """用户确认 → 执行 → 生成回执。执行前必须先落 PROPOSED 且未执行过。"""
    row = get_proposal(db, proposal_id)
    if row.status == "EXECUTED":
        raise HTTPException(409, "该提案已执行，不能重复写入。")
    if row.status == "REJECTED":
        raise HTTPException(409, "该提案已被拒绝，不能执行。")
    cap = get_capability(row.capability)
    parsed = cap.args_model.model_validate(row.args or {})
    profile = profile_id or row.profile_id
    if profile is None:
        raise HTTPException(409, "提案缺少简历档案，无法写入。请先在页面选择简历档案。")
    target_id, diff = cap.execute(db, profile, parsed)
    row.status = "EXECUTED"
    receipt = models.WriteReceipt(
        proposal_id=row.id,
        target_table=cap.target_table,
        target_id=target_id,
        diff=diff,
    )
    db.add(receipt)
    db.commit()
    db.refresh(receipt)
    return receipt


def reject_proposal(db: Session, proposal_id: Any) -> models.WriteProposal:
    row = get_proposal(db, proposal_id)
    if row.status == "EXECUTED":
        raise HTTPException(409, "该提案已执行，无法拒绝。")
    row.status = "REJECTED"
    db.commit()
    db.refresh(row)
    return row


def proposal_read(row: models.WriteProposal) -> dict:
    return {
        "id": str(row.id),
        "conversation_id": str(row.conversation_id) if row.conversation_id else None,
        "message_id": str(row.message_id) if row.message_id else None,
        "profile_id": str(row.profile_id) if row.profile_id else None,
        "capability": row.capability,
        "args": row.args,
        "summary": row.summary,
        "status": row.status,
        "created_at": row.created_at.isoformat() if row.created_at else None,
        "receipt": receipt_read(row.receipt) if row.receipt else None,
    }


def receipt_read(row: models.WriteReceipt) -> dict:
    return {
        "id": str(row.id),
        "proposal_id": str(row.proposal_id),
        "target_table": row.target_table,
        "target_id": row.target_id,
        "diff": row.diff,
        "executed_at": row.executed_at.isoformat() if row.executed_at else None,
    }


__all__ = [
    "capability_catalog",
    "get_capability",
    "validate_args",
    "propose_write",
    "list_proposals",
    "get_proposal",
    "confirm_proposal",
    "reject_proposal",
    "proposal_read",
    "receipt_read",
    "PROPOSAL_STATUSES",
]
