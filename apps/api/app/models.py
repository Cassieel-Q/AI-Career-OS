from __future__ import annotations

from datetime import datetime
from uuid import UUID, uuid4

from sqlalchemy import DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import JSON, Uuid

from app.database import Base


class UserProfile(Base):
    __tablename__ = "user_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT")
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    email: Mapped[str | None] = mapped_column(String(255), nullable=True)
    city: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    education: Mapped[list[Education]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    skills: Mapped[list[ProfileSkill]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    experiences: Mapped[list[Experience]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    certifications: Mapped[list[Certification]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    career_preference: Mapped[CareerPreference | None] = relationship(
        "CareerPreference",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
    )
    role_exploration: Mapped[RoleExploration | None] = relationship(
        "RoleExploration",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
    )
    target_role: Mapped[TargetRole | None] = relationship(
        "TargetRole",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
    )
    target_jobs: Mapped[list[TargetJob]] = relationship(
        "TargetJob",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (TargetJob.created_at, TargetJob.id),
    )
    job_missions: Mapped[list[JobMission]] = relationship(
        "JobMission",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (JobMission.created_at, JobMission.id),
    )


class ProfileChild:
    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    evidence_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    source_type: Mapped[str] = mapped_column(String(16), nullable=False, default="USER_ENTERED")
    raw_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    canonical_value: Mapped[str | None] = mapped_column(String(255), nullable=True)
    evidence_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    evidence_end: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Education(ProfileChild, Base):
    __tablename__ = "education"

    institution: Mapped[str] = mapped_column(String(255), nullable=False)
    degree: Mapped[str | None] = mapped_column(String(255), nullable=True)
    field_of_study: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dates: Mapped[str | None] = mapped_column(String(255), nullable=True)
    relevant_courses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    profile: Mapped[UserProfile] = relationship(back_populates="education")


class ProfileSkill(ProfileChild, Base):
    __tablename__ = "profile_skills"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    proficiency: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="skills")


class Experience(ProfileChild, Base):
    __tablename__ = "experiences"

    title: Mapped[str] = mapped_column(String(255), nullable=False)
    organization: Mapped[str | None] = mapped_column(String(255), nullable=True)
    dates: Mapped[str | None] = mapped_column(String(255), nullable=True)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    experience_type: Mapped[str] = mapped_column(String(16), nullable=False, default="OTHER", server_default="OTHER")
    profile: Mapped[UserProfile] = relationship(back_populates="experiences")


class Certification(ProfileChild, Base):
    __tablename__ = "certifications"

    name: Mapped[str] = mapped_column(String(255), nullable=False)
    issuer: Mapped[str | None] = mapped_column(String(255), nullable=True)
    date: Mapped[str | None] = mapped_column(String(255), nullable=True)
    score: Mapped[str | None] = mapped_column(String(64), nullable=True)
    status: Mapped[str | None] = mapped_column(String(32), nullable=True)
    profile: Mapped[UserProfile] = relationship(back_populates="certifications")


class CareerPreference(Base):
    __tablename__ = "career_preferences"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    priority_1: Mapped[str] = mapped_column(String(32), nullable=False)
    priority_2: Mapped[str] = mapped_column(String(32), nullable=False)
    weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    @property
    def priority_order(self) -> list[str]:
        return [self.priority_1, self.priority_2]

    profile: Mapped[UserProfile] = relationship(
        "UserProfile", back_populates="career_preference"
    )


class RoleExploration(Base):
    __tablename__ = "role_explorations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    role_profile_version: Mapped[str] = mapped_column(String(32), nullable=False)
    result: Mapped[dict] = mapped_column(JSON, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[UserProfile] = relationship(
        "UserProfile", back_populates="role_exploration"
    )


class TargetRole(Base):
    __tablename__ = "target_roles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    role_code: Mapped[str] = mapped_column(String(64), nullable=False)
    role_profile_version: Mapped[str] = mapped_column(String(32), nullable=False)
    role_exploration_id: Mapped[UUID] = mapped_column(
        ForeignKey("role_explorations.id", ondelete="CASCADE"),
        nullable=False,
        unique=True,
        index=True,
    )
    selected_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    profile: Mapped[UserProfile] = relationship(
        "UserProfile", back_populates="target_role"
    )
    role_exploration: Mapped[RoleExploration] = relationship(
        "RoleExploration"
    )
    job_descriptions: Mapped[list[JobDescription]] = relationship(
        "JobDescription",
        back_populates="target_role",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (JobDescription.created_at, JobDescription.id),
    )
    market_profile: Mapped[MarketProfile | None] = relationship(
        "MarketProfile",
        back_populates="target_role",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class JobDescription(Base):
    __tablename__ = "job_descriptions"
    __table_args__ = (
        # Hash uniqueness is scoped to the current Target Role collection.
        UniqueConstraint(
            "target_role_id", "content_hash", name="uq_job_descriptions_target_role_content_hash"
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_role_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_roles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    target_role: Mapped[TargetRole] = relationship(
        "TargetRole", back_populates="job_descriptions"
    )
    market_evidence: Mapped[list[MarketRequirementEvidence]] = relationship(
        "MarketRequirementEvidence",
        back_populates="job_description",
        passive_deletes=True,
    )


class MarketProfile(Base):
    __tablename__ = "market_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_role_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_roles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    sample_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sample_count: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="VALID")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    target_role: Mapped[TargetRole] = relationship("TargetRole", back_populates="market_profile")
    requirements: Mapped[list[MarketRequirement]] = relationship(
        "MarketRequirement", back_populates="market_profile", cascade="all, delete-orphan", order_by="MarketRequirement.sort_order"
    )
    gap_analysis: Mapped[GapAnalysis | None] = relationship(
        "GapAnalysis", back_populates="market_profile", uselist=False, cascade="all, delete-orphan", passive_deletes=True
    )


class MarketRequirement(Base):
    __tablename__ = "market_requirements"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    market_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False)
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    occurrence_count: Mapped[int] = mapped_column(Integer, nullable=False)
    frequency_ratio: Mapped[float] = mapped_column(Float, nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    market_profile: Mapped[MarketProfile] = relationship("MarketProfile", back_populates="requirements")
    evidence: Mapped[list[MarketRequirementEvidence]] = relationship(
        "MarketRequirementEvidence", back_populates="requirement", cascade="all, delete-orphan", order_by="MarketRequirementEvidence.id"
    )
    gaps: Mapped[list[Gap]] = relationship("Gap", back_populates="market_requirement", passive_deletes=True)


class MarketRequirementEvidence(Base):
    __tablename__ = "market_requirement_evidence"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    requirement_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_requirements.id", ondelete="CASCADE"), nullable=False, index=True
    )
    job_description_id: Mapped[UUID] = mapped_column(
        ForeignKey("job_descriptions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    evidence_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)

    requirement: Mapped[MarketRequirement] = relationship("MarketRequirement", back_populates="evidence")
    job_description: Mapped[JobDescription] = relationship("JobDescription", back_populates="market_evidence")


class GapAnalysis(Base):
    __tablename__ = "gap_analyses"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    market_profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("market_profiles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    profile_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="VALID")
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")
    market_profile: Mapped[MarketProfile] = relationship("MarketProfile", back_populates="gap_analysis")
    gaps: Mapped[list[Gap]] = relationship("Gap", back_populates="gap_analysis", cascade="all, delete-orphan", order_by="Gap.sort_order")
    priorities: Mapped[list[GapPriority]] = relationship("GapPriority", back_populates="gap_analysis", cascade="all, delete-orphan")
    roadmaps: Mapped[list[Roadmap]] = relationship("Roadmap", back_populates="gap_analysis", cascade="all, delete-orphan")


class Gap(Base):
    __tablename__ = "gaps"
    __table_args__ = (UniqueConstraint("gap_analysis_id", "market_requirement_id", name="uq_gaps_analysis_requirement"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    gap_analysis_id: Mapped[UUID] = mapped_column(ForeignKey("gap_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    market_requirement_id: Mapped[UUID] = mapped_column(ForeignKey("market_requirements.id", ondelete="CASCADE"), nullable=False, index=True)
    state: Mapped[str] = mapped_column(String(16), nullable=False)
    severity: Mapped[str] = mapped_column(String(16), nullable=False)
    proximity: Mapped[str] = mapped_column(String(16), nullable=False)
    feasibility: Mapped[str] = mapped_column(String(16), nullable=False)
    rationale: Mapped[str] = mapped_column(Text, nullable=False)
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    gap_analysis: Mapped[GapAnalysis] = relationship("GapAnalysis", back_populates="gaps")
    market_requirement: Mapped[MarketRequirement] = relationship("MarketRequirement", back_populates="gaps")
    priority: Mapped[GapPriority | None] = relationship("GapPriority", back_populates="gap", uselist=False, cascade="all, delete-orphan")
    roadmap_tasks: Mapped[list[RoadmapTask]] = relationship("RoadmapTask", back_populates="gap", passive_deletes=True)


class GapPriority(Base):
    __tablename__ = "gap_priorities"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    gap_analysis_id: Mapped[UUID] = mapped_column(ForeignKey("gap_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    gap_id: Mapped[UUID] = mapped_column(ForeignKey("gaps.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    system_rank: Mapped[int] = mapped_column(Integer, nullable=False)
    user_rank: Mapped[int | None] = mapped_column(Integer, nullable=True)
    lane: Mapped[str] = mapped_column(String(16), nullable=False)
    system_reason: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    gap_analysis: Mapped[GapAnalysis] = relationship("GapAnalysis", back_populates="priorities")
    gap: Mapped[Gap] = relationship("Gap", back_populates="priority")


class Roadmap(Base):
    __tablename__ = "roadmaps"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    gap_analysis_id: Mapped[UUID] = mapped_column(ForeignKey("gap_analyses.id", ondelete="CASCADE"), nullable=False, index=True)
    revision: Mapped[int] = mapped_column(Integer, nullable=False)
    weekly_hours: Mapped[int] = mapped_column(Integer, nullable=False)
    priority_fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="VALID")
    supersedes_id: Mapped[UUID | None] = mapped_column(ForeignKey("roadmaps.id", ondelete="SET NULL"), nullable=True)
    generated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    invalidated_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")
    gap_analysis: Mapped[GapAnalysis] = relationship("GapAnalysis", back_populates="roadmaps")
    weeks: Mapped[list[RoadmapWeek]] = relationship("RoadmapWeek", back_populates="roadmap", cascade="all, delete-orphan", order_by="RoadmapWeek.week_number")


class RoadmapWeek(Base):
    __tablename__ = "roadmap_weeks"
    __table_args__ = (UniqueConstraint("roadmap_id", "week_number", name="uq_roadmap_weeks_number"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    roadmap_id: Mapped[UUID] = mapped_column(ForeignKey("roadmaps.id", ondelete="CASCADE"), nullable=False, index=True)
    week_number: Mapped[int] = mapped_column(Integer, nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    focus_gap_ids: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    measurable_outcome: Mapped[str] = mapped_column(Text, nullable=False)

    roadmap: Mapped[Roadmap] = relationship("Roadmap", back_populates="weeks")
    tasks: Mapped[list[RoadmapTask]] = relationship("RoadmapTask", back_populates="week", cascade="all, delete-orphan", order_by="RoadmapTask.sort_order")


class RoadmapTask(Base):
    __tablename__ = "roadmap_tasks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    roadmap_week_id: Mapped[UUID] = mapped_column(ForeignKey("roadmap_weeks.id", ondelete="CASCADE"), nullable=False, index=True)
    gap_id: Mapped[UUID | None] = mapped_column(ForeignKey("gaps.id", ondelete="SET NULL"), nullable=True, index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    objective: Mapped[str] = mapped_column(Text, nullable=False)
    estimated_minutes: Mapped[int] = mapped_column(Integer, nullable=False)
    completion_criteria: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="TODO")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    week: Mapped[RoadmapWeek] = relationship("RoadmapWeek", back_populates="tasks")
    gap: Mapped[Gap | None] = relationship("Gap", back_populates="roadmap_tasks")


class TargetJob(Base):
    __tablename__ = "target_jobs"
    __table_args__ = (
        UniqueConstraint("profile_id", "content_hash", name="uq_target_jobs_profile_content_hash"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    raw_text: Mapped[str] = mapped_column(Text, nullable=False)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="CURRENT", server_default="CURRENT")
    requirements: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="target_jobs")
    claims: Mapped[list[ResumeClaim]] = relationship(
        "ResumeClaim",
        back_populates="target_job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (ResumeClaim.sort_order, ResumeClaim.id),
    )
    missions: Mapped[list[JobMission]] = relationship(
        "JobMission",
        back_populates="target_job",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (JobMission.created_at, JobMission.id),
    )


class ResumeClaim(Base):
    __tablename__ = "resume_claims"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim: Mapped[str] = mapped_column(Text, nullable=False)
    current_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    suggested_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    jd_relevance: Mapped[str] = mapped_column(Text, nullable=False)
    matched_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    readiness_status: Mapped[str] = mapped_column(String(32), nullable=False)
    confidence: Mapped[float] = mapped_column(Float, nullable=False)
    risk_reason: Mapped[str] = mapped_column(Text, nullable=False)
    attack_surface: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    fingerprint: Mapped[str] = mapped_column(String(64), nullable=False)
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    target_job: Mapped[TargetJob] = relationship("TargetJob", back_populates="claims")
    profile: Mapped[UserProfile] = relationship("UserProfile")
    interview_sessions: Mapped[list[InterviewSession]] = relationship(
        "InterviewSession", back_populates="claim", cascade="all, delete-orphan", passive_deletes=True
    )
    proof_actions: Mapped[list[ProofAction]] = relationship(
        "ProofAction", back_populates="claim", cascade="all, delete-orphan", passive_deletes=True
    )
    proof_artifacts: Mapped[list[ProofArtifact]] = relationship(
        "ProofArtifact", back_populates="claim", cascade="all, delete-orphan", passive_deletes=True
    )


class InterviewSession(Base):
    __tablename__ = "interview_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    round_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    next_question: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_skill_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    strong_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    weak_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    gap_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gap_why: Mapped[str | None] = mapped_column(Text, nullable=True)
    gap_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    recommended_next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")
    target_job: Mapped[TargetJob] = relationship("TargetJob")
    claim: Mapped[ResumeClaim] = relationship("ResumeClaim", back_populates="interview_sessions")
    mission: Mapped[JobMission | None] = relationship("JobMission", back_populates="interview_sessions")
    turns: Mapped[list[InterviewTurn]] = relationship(
        "InterviewTurn", back_populates="session", cascade="all, delete-orphan", passive_deletes=True, order_by=lambda: InterviewTurn.round_number
    )
    proof_actions: Mapped[list[ProofAction]] = relationship("ProofAction", back_populates="session")


class InterviewTurn(Base):
    __tablename__ = "interview_turns"
    __table_args__ = (UniqueConstraint("session_id", "round_number", name="uq_interview_turns_round"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    skill_id: Mapped[str] = mapped_column(String(64), nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    followup_dimensions: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    session: Mapped[InterviewSession] = relationship("InterviewSession", back_populates="turns")


class ProofAction(Base):
    __tablename__ = "proof_actions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    session_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("interview_sessions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    why_now: Mapped[str] = mapped_column(Text, nullable=False)
    target_claim: Mapped[str] = mapped_column(Text, nullable=False)
    target_gap: Mapped[str] = mapped_column(String(32), nullable=False)
    estimated_hours: Mapped[float] = mapped_column(Float, nullable=False)
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    definition_of_done: Mapped[str] = mapped_column(Text, nullable=False)
    expected_evidence: Mapped[str] = mapped_column(Text, nullable=False)
    target_capability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    existing_project_reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED", server_default="PROPOSED")
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")
    claim: Mapped[ResumeClaim] = relationship("ResumeClaim", back_populates="proof_actions")
    session: Mapped[InterviewSession | None] = relationship("InterviewSession", back_populates="proof_actions")
    mission: Mapped[JobMission | None] = relationship("JobMission", back_populates="proof_actions")
    artifacts: Mapped[list[ProofArtifact]] = relationship(
        "ProofArtifact", back_populates="action", cascade="all, delete-orphan", passive_deletes=True
    )


class ProofArtifact(Base):
    __tablename__ = "proof_artifacts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    claim_id: Mapped[UUID] = mapped_column(
        ForeignKey("resume_claims.id", ondelete="CASCADE"), nullable=False, index=True
    )
    action_id: Mapped[UUID] = mapped_column(
        ForeignKey("proof_actions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    artifact_type: Mapped[str] = mapped_column(String(64), nullable=False)
    artifact_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    artifact_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    manually_confirmed: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    verified_fields: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")
    claim: Mapped[ResumeClaim] = relationship("ResumeClaim", back_populates="proof_artifacts")
    action: Mapped[ProofAction] = relationship("ProofAction", back_populates="artifacts")


class JobMission(Base):
    __tablename__ = "job_missions"
    __table_args__ = (
        UniqueConstraint("profile_id", "target_job_id", name="uq_job_missions_profile_target_job"),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    target_job_id: Mapped[UUID] = mapped_column(
        ForeignKey("target_jobs.id", ondelete="CASCADE"), nullable=False, index=True
    )
    display_name: Mapped[str] = mapped_column(String(255), nullable=False)
    company: Mapped[str] = mapped_column(String(255), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    role: Mapped[str] = mapped_column(String(255), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    role_family: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    seniority: Mapped[str] = mapped_column(String(64), nullable=False, default="UNKNOWN", server_default="UNKNOWN")
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")

    # --- PRODUCT STATE MACHINE (012_workflow_state) ---
    workflow_state: Mapped[str] = mapped_column(String(64), nullable=False, default="ROLE_UNDERSTOOD", server_default="ROLE_UNDERSTOOD")
    resume_source: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    parsed_jd: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    what_matters: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    resume_strategy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    interview_intel: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="job_missions")
    target_job: Mapped[TargetJob] = relationship("TargetJob", back_populates="missions")
    selections: Mapped[list[MissionExperienceSelection]] = relationship(
        "MissionExperienceSelection", back_populates="mission", cascade="all, delete-orphan", passive_deletes=True
    )
    target_resumes: Mapped[list[TargetResume]] = relationship(
        "TargetResume", back_populates="mission", cascade="all, delete-orphan", passive_deletes=True,
        order_by=lambda: (TargetResume.version, TargetResume.id),
    )
    red_team_reports: Mapped[list[RedTeamReport]] = relationship(
        "RedTeamReport", back_populates="mission", cascade="all, delete-orphan", passive_deletes=True,
        order_by=lambda: (RedTeamReport.created_at, RedTeamReport.id),
    )
    interview_packs: Mapped[list[InterviewPack]] = relationship(
        "InterviewPack", back_populates="mission", cascade="all, delete-orphan", passive_deletes=True,
        order_by=lambda: (InterviewPack.version, InterviewPack.id),
    )
    outcomes: Mapped[list[InterviewOutcome]] = relationship(
        "InterviewOutcome", back_populates="mission", cascade="all, delete-orphan", passive_deletes=True,
        order_by=lambda: (InterviewOutcome.created_at, InterviewOutcome.id),
    )
    interview_sessions: Mapped[list[InterviewSession]] = relationship("InterviewSession", back_populates="mission")
    proof_actions: Mapped[list[ProofAction]] = relationship("ProofAction", back_populates="mission")


class MissionExperienceSelection(Base):
    __tablename__ = "mission_experience_selections"
    __table_args__ = (UniqueConstraint("mission_id", "experience_id", name="uq_mission_experience_selection"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    experience_id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), nullable=False, index=True)
    decision: Mapped[str] = mapped_column(String(24), nullable=False)
    why: Mapped[str] = mapped_column(Text, nullable=False)
    related_capabilities: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    supporting_evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    confidence: Mapped[float] = mapped_column(Float, nullable=False, default=0.0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    mission: Mapped[JobMission] = relationship("JobMission", back_populates="selections")


class TargetResume(Base):
    __tablename__ = "target_resumes"
    __table_args__ = (UniqueConstraint("mission_id", "version", name="uq_target_resumes_mission_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    positioning_statement: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_experience_order: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    strategy: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    mission: Mapped[JobMission] = relationship("JobMission", back_populates="target_resumes")
    bullets: Mapped[list[TargetResumeBullet]] = relationship(
        "TargetResumeBullet", back_populates="target_resume", cascade="all, delete-orphan", passive_deletes=True,
        order_by=lambda: (TargetResumeBullet.sort_order, TargetResumeBullet.id),
    )


class TargetResumeBullet(Base):
    __tablename__ = "target_resume_bullets"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    target_resume_id: Mapped[UUID] = mapped_column(ForeignKey("target_resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    source_experience_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    original_text: Mapped[str] = mapped_column(Text, nullable=False)
    suggested_text: Mapped[str] = mapped_column(Text, nullable=False)
    final_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    reason: Mapped[str] = mapped_column(Text, nullable=False)
    jd_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    resume_skill_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="SUGGESTED", server_default="SUGGESTED")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    target_resume: Mapped[TargetResume] = relationship("TargetResume", back_populates="bullets")


class RedTeamReport(Base):
    __tablename__ = "red_team_reports"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    target_resume_id: Mapped[UUID] = mapped_column(ForeignKey("target_resumes.id", ondelete="CASCADE"), nullable=False, index=True)
    findings: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    mission: Mapped[JobMission] = relationship("JobMission", back_populates="red_team_reports")
    target_resume: Mapped[TargetResume] = relationship("TargetResume")


class InterviewPack(Base):
    __tablename__ = "interview_packs"
    __table_args__ = (UniqueConstraint("mission_id", "version", name="uq_interview_packs_mission_version"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    topics: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    mission: Mapped[JobMission] = relationship("JobMission", back_populates="interview_packs")


class InterviewOutcome(Base):
    __tablename__ = "interview_outcomes"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, index=True)
    application_status: Mapped[str] = mapped_column(String(32), nullable=False)
    interview_round: Mapped[str | None] = mapped_column(String(64), nullable=True)
    questions_asked: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    where_struggled: Mapped[str | None] = mapped_column(Text, nullable=True)
    interviewer_feedback: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    confirmed_for_intel: Mapped[bool] = mapped_column(nullable=False, default=False, server_default="false")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    mission: Mapped[JobMission] = relationship("JobMission", back_populates="outcomes")
