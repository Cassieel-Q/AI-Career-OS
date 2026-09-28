from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field

from .gap_schemas import GapRead
from .priority_schemas import PriorityRead
from .roadmap_schemas import RoadmapTaskRead


class DashboardTargetRole(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    role_code: str
    role_name: str


class DashboardRequirement(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str
    category: str
    occurrence_count: int
    frequency_ratio: float


class DashboardRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    target_role: DashboardTargetRole | None
    jd_sample_count: int
    market_ready: bool
    top_requirements: list[DashboardRequirement] = Field(default_factory=list)
    top_gaps: list[GapRead] = Field(default_factory=list)
    confirmed_priorities: list[PriorityRead] = Field(default_factory=list)
    current_week: int | None
    upcoming_tasks: list[RoadmapTaskRead] = Field(default_factory=list)
    progress_ratio: float
    roadmap_id: str | None
    replan_available: bool
