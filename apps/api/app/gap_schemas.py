from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator

from .jd_analysis_schemas import MarketRequirementEvidenceRead


class GapState(StrEnum):
    MATCHED = "MATCHED"
    PARTIAL = "PARTIAL"
    MISSING = "MISSING"
    UNCERTAIN = "UNCERTAIN"


class GapProposal(BaseModel):
    model_config = ConfigDict(extra="forbid")

    requirement_id: UUID
    state: GapState
    severity: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH)$")
    proximity: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH)$")
    feasibility: str = Field(default="MEDIUM", pattern="^(LOW|MEDIUM|HIGH)$")
    rationale: str = Field(min_length=1, max_length=600)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=12)

    @field_validator("rationale")
    @classmethod
    def clean_rationale(cls, value: str) -> str:
        return value.strip()


class GapProposalPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[GapProposal] = Field(default_factory=list, max_length=100)


class GapRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    requirement_id: UUID
    capability_id: UUID
    requirement_name: str
    capability_name: str
    capability_summary: str
    category: str
    occurrence_count: int
    frequency_ratio: float
    source_jd_ids: list[UUID]
    atomic_requirement_ids: list[UUID]
    atomic_requirement_names: list[str]
    market_evidence: list[MarketRequirementEvidenceRead]
    state: GapState
    severity: str
    proximity: str
    feasibility: str
    rationale: str
    evidence_refs: list[UUID]
    sort_order: int


class GapAnalysisRead(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: UUID
    profile_id: UUID
    market_profile_id: UUID
    profile_fingerprint: str
    status: str
    generated_at: datetime
    updated_at: datetime
    gaps: list[GapRead]
