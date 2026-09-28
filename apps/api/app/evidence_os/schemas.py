from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class OrmModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# --- Sources / Evidence / Claims ---

class SourceCreate(BaseModel):
    source_type: str
    locator: str
    notes: str = ""
    captured_at: datetime | None = None


class SourceOut(OrmModel):
    id: UUID
    profile_id: UUID
    source_type: str
    locator: str
    notes: str
    captured_at: datetime | None
    created_at: datetime


class MetricPayload(BaseModel):
    value: float | int | str
    unit: str | None = None
    period: str | None = None
    source_confirmed: bool = False


class EvidenceCreate(BaseModel):
    fact_text: str
    evidence_type: str
    org_or_project: str | None = None
    identity_lock: bool = False
    metric: MetricPayload | dict[str, Any] | None = None
    source_ids: list[UUID] = Field(default_factory=list)


class EvidenceOut(OrmModel):
    id: UUID
    profile_id: UUID
    fact_text: str
    evidence_type: str
    org_or_project: str | None
    identity_lock: bool
    metric: dict[str, Any] | None
    source_ids: list
    created_at: datetime
    updated_at: datetime


class ClaimCreate(BaseModel):
    source_fact: str
    candidate_wording: str
    verification_status: str = "pending"
    responsibility_level: str = "contributed"
    boundary: str = ""
    interview_details: str = ""
    risk_notes: list[str] = Field(default_factory=list)
    evidence_ids: list[UUID] = Field(default_factory=list)
    competency_ids: list[str] = Field(default_factory=list)


class ClaimUpdate(BaseModel):
    candidate_wording: str | None = None
    verification_status: str | None = None
    responsibility_level: str | None = None
    boundary: str | None = None
    interview_details: str | None = None
    risk_notes: list[str] | None = None
    evidence_ids: list[UUID] | None = None
    competency_ids: list[str] | None = None


class ClaimOut(OrmModel):
    id: UUID
    profile_id: UUID
    source_fact: str
    candidate_wording: str
    verification_status: str
    responsibility_level: str
    boundary: str
    interview_details: str
    risk_notes: list
    evidence_ids: list
    competency_ids: list
    last_verified_at: datetime | None
    created_at: datetime
    updated_at: datetime


# --- JD / Requirements / Match ---

class JdCreate(BaseModel):
    title: str = "Untitled role"
    company: str | None = None
    raw_text: str
    language: str = "en"
    source_url: str | None = None


class RequirementOut(OrmModel):
    id: UUID
    jd_id: UUID
    raw_text: str
    normalized_text: str
    priority: str
    keywords: list
    competency_ids: list
    sort_order: int


class JdOut(OrmModel):
    id: UUID
    profile_id: UUID
    title: str
    company: str | None
    raw_text: str
    language: str
    source_url: str | None
    created_at: datetime
    requirements: list[RequirementOut] = Field(default_factory=list)


class MatchRowOut(OrmModel):
    id: UUID
    profile_id: UUID
    jd_id: UUID
    requirement_id: UUID
    match_status: str
    claim_ids: list
    evidence_ids: list
    rationale: str
    excavation_questions: list


class MatchRunResult(BaseModel):
    jd_id: UUID
    rows: list[MatchRowOut]
    covered: int
    weak: int
    missing: int
    needs_excavation: int


# --- Positioning / Version / Audit / Render ---

class PositionRequest(BaseModel):
    jd_id: UUID
    positioning_mode: str = "conservative"
    title: str | None = None
    claim_ids: list[UUID] | None = None


class BulletOut(BaseModel):
    claim_id: UUID
    section: str
    text: str
    verification_status: str


class VersionOut(OrmModel):
    id: UUID
    profile_id: UUID
    jd_id: UUID | None
    positioning_mode: str
    title: str
    full_text: str
    full_text_hash: str | None
    status: str
    bullets: list
    excluded: list
    audit_safe: bool
    created_at: datetime
    updated_at: datetime


class AuditResult(BaseModel):
    version_id: UUID
    audit_safe: bool
    blockers: list[str]
    warnings: list[str]


class ApproveRequest(BaseModel):
    full_text_hash: str


class ApprovalOut(OrmModel):
    id: UUID
    version_id: UUID
    full_text_hash: str
    approved_at: datetime
    approver: str


class RenderResult(BaseModel):
    version_id: UUID
    status: str
    full_text: str
    message: str


class EvalReportOut(OrmModel):
    id: UUID
    version_id: UUID
    kind: str
    score: float
    label: str
    is_heuristic: bool
    missing_items: list
    notes: str
    created_at: datetime


class GateErrorDetail(BaseModel):
    code: str
    message: str
    field: str | None = None
