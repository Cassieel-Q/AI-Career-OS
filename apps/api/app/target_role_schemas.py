from __future__ import annotations

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field

from .role_exploration_schemas import RoleCode


class TargetRoleInput(BaseModel):
    model_config = ConfigDict(extra="forbid")

    role_code: RoleCode


class TargetRoleRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    profile_id: UUID
    role_code: RoleCode
    role_name: str = Field(min_length=1, max_length=120)
    role_profile_version: str = Field(min_length=1, max_length=32)
    role_exploration_id: UUID
    selected_at: datetime
    updated_at: datetime
