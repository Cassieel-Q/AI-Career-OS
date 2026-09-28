from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator


class RequirementCategory(StrEnum):
    SKILL = "SKILL"
    RESPONSIBILITY = "RESPONSIBILITY"
    EXPERIENCE = "EXPERIENCE"
    EDUCATION = "EDUCATION"
    DOMAIN = "DOMAIN"
    COLLABORATION = "COLLABORATION"
    OTHER = "OTHER"


class JdExtractionItem(BaseModel):
    model_config = ConfigDict(extra="forbid")

    name: str = Field(min_length=1, max_length=255)
    category: RequirementCategory
    evidence_text: str = Field(min_length=1, max_length=1000)

    @field_validator("name", "evidence_text")
    @classmethod
    def strip_text(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("text must not be blank")
        return value


class JdExtraction(BaseModel):
    model_config = ConfigDict(extra="forbid")

    jd_id: UUID
    items: list[JdExtractionItem] = Field(default_factory=list, max_length=100)


class JdExtractionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[JdExtraction] = Field(min_length=1, max_length=10)


class MarketRequirementEvidenceRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    job_description_id: UUID
    source_url: str | None
    evidence_text: str


class MarketRequirementRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    name: str
    category: RequirementCategory
    occurrence_count: int
    frequency_ratio: float
    source_jd_ids: list[UUID]
    evidence: list[MarketRequirementEvidenceRead]


class MarketCapabilityRead(BaseModel):
    """A decision-facing projection over grounded atomic market requirements."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    name: str
    summary: str
    occurrence_count: int
    frequency_ratio: float
    source_jd_ids: list[UUID]
    atomic_requirement_ids: list[UUID]
    atomic_requirements: list[MarketRequirementRead]
    evidence: list[MarketRequirementEvidenceRead]


class MarketProfileRead(BaseModel):
    model_config = ConfigDict(from_attributes=True, extra="forbid")

    id: UUID
    target_role_id: UUID
    sample_count: int
    sample_fingerprint: str
    status: str
    generated_at: datetime
    updated_at: datetime
    requirements: list[MarketRequirementRead]
    capabilities: list[MarketCapabilityRead]
