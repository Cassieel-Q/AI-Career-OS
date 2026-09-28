from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.types import JSON, Uuid

from app.database import Base


class EosSource(Base):
    __tablename__ = "eos_sources"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_type: Mapped[str] = mapped_column(String(32), nullable=False)
    locator: Mapped[str] = mapped_column(Text, nullable=False)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    captured_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EosEvidence(Base):
    __tablename__ = "eos_evidence"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_text: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_type: Mapped[str] = mapped_column(String(32), nullable=False)
    org_or_project: Mapped[str | None] = mapped_column(Text, nullable=True)
    identity_lock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    metric: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    source_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EosClaim(Base):
    __tablename__ = "eos_claims"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    source_fact: Mapped[str] = mapped_column(Text, nullable=False)
    candidate_wording: Mapped[str] = mapped_column(Text, nullable=False)
    verification_status: Mapped[str] = mapped_column(String(16), nullable=False, default="pending")
    responsibility_level: Mapped[str] = mapped_column(String(32), nullable=False, default="contributed")
    boundary: Mapped[str] = mapped_column(Text, nullable=False, default="")
    interview_details: Mapped[str] = mapped_column(Text, nullable=False, default="")
    risk_notes: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competency_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    last_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EosJd(Base):
    __tablename__ = "eos_jds"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="Untitled role")
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    language: Mapped[str] = mapped_column(String(16), nullable=False, default="en")
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)


class EosRequirement(Base):
    __tablename__ = "eos_requirements"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    jd_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_jds.id", ondelete="CASCADE"), nullable=False, index=True)
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    priority: Mapped[str] = mapped_column(String(32), nullable=False, default="core")
    keywords: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    competency_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


class EosMatchRow(Base):
    __tablename__ = "eos_match_rows"
    __table_args__ = (UniqueConstraint("jd_id", "requirement_id", name="uq_eos_match_jd_req"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_jds.id", ondelete="CASCADE"), nullable=False)
    requirement_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_requirements.id", ondelete="CASCADE"), nullable=False)
    match_status: Mapped[str] = mapped_column(String(32), nullable=False)
    claim_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    evidence_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    rationale: Mapped[str] = mapped_column(Text, nullable=False, default="")
    excavation_questions: Mapped[list] = mapped_column(JSON, nullable=False, default=list)


class EosResumeVersion(Base):
    __tablename__ = "eos_resume_versions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    jd_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_jds.id", ondelete="SET NULL"), nullable=True)
    positioning_mode: Mapped[str] = mapped_column(String(16), nullable=False, default="conservative")
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    full_text: Mapped[str] = mapped_column(Text, nullable=False, default="")
    full_text_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="draft")
    bullets: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    excluded: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    audit_safe: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now(), nullable=False)


class EosApproval(Base):
    __tablename__ = "eos_approvals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    full_text_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    approved_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    approver: Mapped[str] = mapped_column(String(32), nullable=False, default="user")


class EosEvalReport(Base):
    __tablename__ = "eos_eval_reports"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    version_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), ForeignKey("eos_resume_versions.id", ondelete="CASCADE"), nullable=False, index=True)
    kind: Mapped[str] = mapped_column(String(32), nullable=False)
    score: Mapped[float] = mapped_column(Float, nullable=False)
    label: Mapped[str] = mapped_column(String(64), nullable=False)
    is_heuristic: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    missing_items: Mapped[list] = mapped_column(JSON, nullable=False, default=list)
    notes: Mapped[str] = mapped_column(Text, nullable=False, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), nullable=False)
