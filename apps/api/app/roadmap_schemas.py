from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TaskStatus(StrEnum):
    TODO = "TODO"
    IN_PROGRESS = "IN_PROGRESS"
    DONE = "DONE"
    SKIPPED = "SKIPPED"


class RoadmapTaskProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str = Field(min_length=1, max_length=255)
    objective: str = Field(min_length=1, max_length=600)
    estimated_minutes: int = Field(gt=0, le=600)
    related_gap_id: UUID
    completion_criteria: str = Field(min_length=1, max_length=600)


class RoadmapWeekProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    week_number: int = Field(ge=1, le=4)
    objective: str = Field(min_length=1, max_length=600)
    focus_gap_ids: list[UUID] = Field(default_factory=list, max_length=10)
    measurable_outcome: str = Field(min_length=1, max_length=600)
    tasks: list[RoadmapTaskProposal] = Field(min_length=1, max_length=20)


class RoadmapProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    weeks: list[RoadmapWeekProposal] = Field(min_length=4, max_length=4)

    @model_validator(mode="after")
    def validate_weeks(self) -> "RoadmapProposal":
        if [week.week_number for week in self.weeks] != [1, 2, 3, 4]:
            raise ValueError("roadmap weeks must be numbered 1 through 4")
        return self


class RoadmapTaskRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    gap_id: UUID | None
    title: str
    objective: str
    estimated_minutes: int
    completion_criteria: str
    status: TaskStatus
    sort_order: int
    completed_at: datetime | None


class RoadmapWeekRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    week_number: int
    objective: str
    focus_gap_ids: list[UUID]
    measurable_outcome: str
    tasks: list[RoadmapTaskRead]


class RoadmapRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    profile_id: UUID
    revision: int
    weekly_hours: int
    status: str
    progress_ratio: float
    weeks: list[RoadmapWeekRead]


class RoadmapTaskUpdate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: TaskStatus


class ReplanRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    remaining_weeks: int = Field(default=4, ge=1, le=4)
