from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Annotated, Self
from uuid import UUID

from pydantic import AliasChoices, BaseModel, ConfigDict, Field, field_validator, model_validator

from .profile_schemas import CareerPreferencePriority


class RoleCode(StrEnum):
    AI_PRODUCT_MANAGER = "AI_PRODUCT_MANAGER"
    AI_APPLICATION_ENGINEER = "AI_APPLICATION_ENGINEER"
    AI_SOLUTION_CONSULTANT = "AI_SOLUTION_CONSULTANT"
    LLM_ALGORITHM_ENGINEER = "LLM_ALGORITHM_ENGINEER"
    AI_DATA_ANALYST = "AI_DATA_ANALYST"
    AI_PRODUCT_OPERATIONS = "AI_PRODUCT_OPERATIONS"


class ExplorationLevel(StrEnum):
    RECOMMENDED = "RECOMMENDED"
    POSSIBLE = "POSSIBLE"
    LOW_PRIORITY = "LOW_PRIORITY"


class CodingIntensity(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


class EntryBarrier(StrEnum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"


BoundedText = Annotated[str, Field(min_length=1, max_length=240)]


def _normalize_bounded_texts(values: list[str]) -> list[str]:
    normalized = [value.strip() for value in values]
    if any(not value for value in normalized):
        raise ValueError("text entries must not be blank")
    return normalized


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class RoleExplorationProviderItem(_StrictModel):
    role_code: RoleCode
    level: ExplorationLevel = Field(
        validation_alias=AliasChoices("level", "exploration_level"),
        serialization_alias="level",
    )
    reasons: list[BoundedText] = Field(min_length=1, max_length=3)
    concerns: list[BoundedText] = Field(default_factory=list, max_length=3)
    evidence_refs: list[UUID] = Field(min_length=1, max_length=8)
    preference_refs: list[CareerPreferencePriority] = Field(default_factory=list, max_length=2)

    @field_validator("reasons", "concerns", mode="after")
    @classmethod
    def normalize_text(cls, values: list[str]) -> list[str]:
        return _normalize_bounded_texts(values)


class RoleExplorationProviderPayload(_StrictModel):
    items: list[RoleExplorationProviderItem] = Field(
        min_length=1,
        max_length=6,
        validation_alias=AliasChoices("items", "roles"),
    )

    @property
    def roles(self) -> list[RoleExplorationProviderItem]:
        return self.items


class RoleExplorationItem(_StrictModel):
    role_code: RoleCode
    role_name: str = Field(min_length=1, max_length=120)
    level: ExplorationLevel = Field(
        validation_alias=AliasChoices("level", "exploration_level"),
        serialization_alias="level",
    )
    reasons: list[BoundedText] = Field(min_length=1, max_length=3)
    concerns: list[BoundedText] = Field(default_factory=list, max_length=3)
    evidence_refs: list[UUID] = Field(min_length=1, max_length=8)
    preference_refs: list[CareerPreferencePriority] = Field(default_factory=list, max_length=2)

    @field_validator("reasons", "concerns", mode="after")
    @classmethod
    def normalize_text(cls, values: list[str]) -> list[str]:
        return _normalize_bounded_texts(values)

    @property
    def exploration_level(self) -> ExplorationLevel:
        return self.level


class RoleExplorationResult(_StrictModel):
    role_profile_version: str = Field(min_length=1, max_length=32)
    items: list[RoleExplorationItem] = Field(
        min_length=1,
        max_length=6,
        validation_alias=AliasChoices("items", "roles"),
    )

    @model_validator(mode="after")
    def validate_role_set_and_recommendation_cap(self) -> Self:
        role_codes = [item.role_code for item in self.items]
        if len(role_codes) != len(set(role_codes)) or set(role_codes) != set(RoleCode):
            raise ValueError("result must contain each supported role exactly once")
        if sum(item.level is ExplorationLevel.RECOMMENDED for item in self.items) > 3:
            raise ValueError("result may contain at most three recommended roles")
        return self

    @property
    def roles(self) -> list[RoleExplorationItem]:
        return self.items


class RoleExplorationRequest(_StrictModel):
    profile_id: UUID


class RoleExplorationRead(_StrictModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    profile_id: UUID
    role_profile_version: str = Field(min_length=1, max_length=32)
    result: RoleExplorationResult
    created_at: datetime
    updated_at: datetime
