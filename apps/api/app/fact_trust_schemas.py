"""事实核对接口的输入输出契约。

「核对这段经历」页面需要三件东西：原始文字、事实来源、还缺什么。
这里的结构与前端一一对应，避免出现前端自己推导状态的情况。
"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class FactItem(_StrictModel):
    """一条待核对的候选事实（通常是一段经历）。"""

    fact_key: str = Field(min_length=1, max_length=200)
    title: str = Field(default="", max_length=255)
    original_text: str = Field(default="", max_length=4_000)
    suggested_text: str | None = Field(default=None, max_length=4_000)
    source_kind: str = Field(default="SOURCE_EXTRACTED", max_length=32)
    source_id: str | None = Field(default=None, max_length=120)
    source_type: str | None = Field(default=None, max_length=32)
    verification_status: str = Field(default="UNREVIEWED", max_length=16)
    verified_at: datetime | None = None
    present_aspects: list[str] = Field(default_factory=list, max_length=8)
    missing_aspects: list[str] = Field(default_factory=list, max_length=8)
    risk: str = Field(default="LOW", max_length=8)
    note: str | None = Field(default=None, max_length=1_000)
    #: 受控修正可改字段的当前值（P1-A），前端据此展示旧值并组装修改框。
    field_values: dict[str, str] = Field(default_factory=dict)


class FactListRead(_StrictModel):
    profile_id: UUID
    facts: list[FactItem] = Field(default_factory=list)
    attested_count: int = 0
    rejected_count: int = 0
    pending_count: int = 0


class FactFieldChange(_StrictModel):
    """一次受控字段修正的新旧值对照（让用户看到改了什么）。"""

    field: str = Field(min_length=1, max_length=32)
    old_value: str = Field(default="", max_length=4_000)
    new_value: str = Field(default="", max_length=4_000)


#: 受控修正允许写回源档案的字段（按事实类型）。
CONTROLLED_FIELDS: dict[str, tuple[str, ...]] = {
    "experience": ("title", "organization", "dates", "description"),
    "skill": ("name",),
}


class FactAttestCreate(_StrictModel):
    """一次明确的用户核对动作。

    ``status`` 只接受 ``USER_ATTESTED`` / ``REJECTED`` / ``UNREVIEWED``（撤回核对）。
    不接受 ``CONFIRMED`` 之类的旧值——系统状态不能冒充用户核对。

    ``field_updates`` 是受控字段修正（FINAL FREEZE P1-A）：已确认档案不允许整体
    PUT，但允许通过这里修正单项事实。只开放 CONTROLLED_FIELDS 列出的字段，
    且必须与 ``apply_to_source=True`` 一起提交——「修正」与「写回」是同一次
    用户确认动作。
    """

    fact_key: str = Field(min_length=1, max_length=200)
    status: str = Field(min_length=1, max_length=16)
    fact_text: str | None = Field(default=None, max_length=4_000)
    note: str | None = Field(default=None, max_length=1_000)
    apply_to_source: bool = False
    field_updates: dict[str, str] | None = Field(default=None)


class FactAttestRead(_StrictModel):
    fact_key: str
    status: str
    verification_status: str
    fact_text: str
    source_kind: str
    verified_at: datetime | None
    applied_to_source: bool
    applied_fields: list[str] = Field(default_factory=list)
    field_changes: list[FactFieldChange] = Field(default_factory=list)
    note: str | None = None
