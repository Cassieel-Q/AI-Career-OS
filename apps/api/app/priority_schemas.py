from __future__ import annotations

from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator


class PriorityLane(StrEnum):
    NOW = "NOW"
    NEXT = "NEXT"
    NOT_NOW = "NOT_NOW"


class PriorityRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_id: UUID
    requirement_name: str
    state: str
    severity: str
    proximity: str
    feasibility: str
    frequency_ratio: float
    system_rank: int
    user_rank: int | None
    effective_rank: int
    lane: PriorityLane
    system_reason: str


class PriorityListRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gap_analysis_id: UUID
    overridden: bool
    items: list[PriorityRead]


class PriorityUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    order: list[UUID] = Field(min_length=1, max_length=100)

    @model_validator(mode="after")
    def no_duplicates(self) -> "PriorityUpdate":
        if len(set(self.order)) != len(self.order):
            raise ValueError("order must not contain duplicate gap IDs")
        return self
