"""Validated edit commands shared by browser and agents."""
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class StudioOperation(BaseModel):
    model_config = ConfigDict(extra="forbid")

    type: Literal[
        "set_text", "add_entry", "add_bullet", "omit", "restore", "move",
        "set_template", "confirm_fact", "set_language", "set_evidence", "set_layout",
    ]
    node_id: UUID | None = None
    section_id: UUID | None = None
    entry_id: UUID | None = None
    before_id: UUID | None = None
    text: str | None = Field(default=None, max_length=4_000)
    title: str | None = Field(default=None, max_length=255)
    template_id: str | None = Field(default=None, max_length=64)
    language: Literal["zh", "en"] | None = None
    evidence_refs: list[UUID] | None = Field(default=None, max_length=20)
    # 版式配置（目标五）：颜色/字号/间距/分栏/照片/栏目顺序，统一走归一化白名单。
    layout_config: dict | None = None
