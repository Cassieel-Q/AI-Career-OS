from __future__ import annotations

from datetime import date, datetime
from uuid import UUID, uuid4

from sqlalchemy import Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint, func
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
    # 025_job_insight：简历原始文字（上传 PDF 提取到的原文 / 用户粘贴的文本），
    # 供「简历中心 · 简历工作台」直接编辑；与逐条事实解耦，改完可重新解析。
    resume_text: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    education: Mapped[list[Education]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    skills: Mapped[list[ProfileSkill]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    experiences: Mapped[list[Experience]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    certifications: Mapped[list[Certification]] = relationship(back_populates="profile", cascade="all, delete-orphan")
    interview_records: Mapped[list["InterviewRecord"]] = relationship(
        "InterviewRecord", back_populates="profile", cascade="all, delete-orphan", passive_deletes=True
    )
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
    applications: Mapped[list["JobApplication"]] = relationship(
        "JobApplication",
        back_populates="profile",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (JobApplication.created_at, JobApplication.id),
    )
    candidate_jobs: Mapped[list["CandidateJob"]] = relationship(
        "CandidateJob",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (CandidateJob.created_at, CandidateJob.id),
    )
    application_profile: Mapped["ApplicationProfile | None"] = relationship(
        "ApplicationProfile",
        back_populates="profile",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
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
    # CET-4/6 分数：不能只保存「已通过」，否则丢失分数（目标四）。
    cet4_score: Mapped[str | None] = mapped_column(String(32), nullable=True)
    cet6_score: Mapped[str | None] = mapped_column(String(32), nullable=True)
    relevant_courses: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    honors: Mapped[list[str]] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
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


class ApplicationProfile(Base):
    """网申资料（ApplicationProfile）：身份证、家庭、健康、档案、紧急联系人、到岗信息等。

    与 ResumeProfile 严格分界：
    - 简历生成**只读** ResumeProfile（UserProfile + 子表），绝不读本表；
    - 网申填表可读 ResumeProfile + 本表；
    - 助手默认**不读**本表敏感字段。
    """

    __tablename__ = "application_profiles"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    id_number: Mapped[str | None] = mapped_column(String(64), nullable=True)
    family_info: Mapped[str | None] = mapped_column(Text, nullable=True)
    health_status: Mapped[str | None] = mapped_column(Text, nullable=True)
    archive_location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_contact: Mapped[str | None] = mapped_column(String(255), nullable=True)
    emergency_phone: Mapped[str | None] = mapped_column(String(64), nullable=True)
    availability: Mapped[str | None] = mapped_column(String(255), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="application_profile")


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
    # 第七阶段：模拟面试启动参数（mission_id/target_resume_id/interview_type/difficulty/interviewer_style/rounds）。
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
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
    # --- 025_job_insight：岗位关键词分析 / 简历×岗位匹配度（模型生成后缓存，避免每次进列表都调用） ---
    analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    match_analysis: Mapped[dict | None] = mapped_column(JSON, nullable=True)
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


class ResumeStudioDocument(Base):
    __tablename__ = "resume_studio_documents"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    mission_id: Mapped[UUID] = mapped_column(ForeignKey("job_missions.id", ondelete="CASCADE"), nullable=False, unique=True, index=True)
    source_target_resume_id: Mapped[UUID] = mapped_column(ForeignKey("target_resumes.id", ondelete="CASCADE"), nullable=False)
    schema_version: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    revision: Mapped[int] = mapped_column(Integer, nullable=False, default=1, server_default="1")
    language: Mapped[str] = mapped_column(String(2), nullable=False, default="zh", server_default="zh")
    template_id: Mapped[str] = mapped_column(String(64), nullable=False, default="zh-classic", server_default="zh-classic")
    document_json: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    # 版式配置（单一事实来源）：Preview/PDF/Word/Markdown 统一读取本字段（目标五）。
    layout_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    confirmed_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


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
class InterviewRecord(Base):
    """User-authored real interview log (not mock claim drills; not intel outcomes)."""

    __tablename__ = "interview_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    interview_round: Mapped[str] = mapped_column(String(64), nullable=False)
    interviewed_on: Mapped[date] = mapped_column(Date, nullable=False)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="DRAFT", server_default="DRAFT")
    strong_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    weak_points: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    gap_type: Mapped[str | None] = mapped_column(String(32), nullable=True)
    gap_why: Mapped[str | None] = mapped_column(Text, nullable=True)
    recommended_next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    coaching: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="interview_records")
    mission: Mapped[JobMission | None] = relationship("JobMission")
    items: Mapped[list[InterviewRecordItem]] = relationship(
        "InterviewRecordItem",
        back_populates="record",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: InterviewRecordItem.sort_order,
    )


class InterviewRecordItem(Base):
    __tablename__ = "interview_record_items"
    __table_args__ = (UniqueConstraint("record_id", "sort_order", name="uq_interview_record_items_order"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    record_id: Mapped[UUID] = mapped_column(
        ForeignKey("interview_records.id", ondelete="CASCADE"), nullable=False, index=True
    )
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    question: Mapped[str] = mapped_column(Text, nullable=False)
    context: Mapped[str | None] = mapped_column(Text, nullable=True)
    my_answer: Mapped[str] = mapped_column(Text, nullable=False)
    evaluation: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    record: Mapped[InterviewRecord] = relationship("InterviewRecord", back_populates="items")


class JobApplication(Base):
    """投递记录：一家公司一个岗位一条投递动作记录，状态可单向推进。

    与 InterviewOutcome（面试结果沉淀）分开：本表记录「投递动作 + 状态流转」，
    是「自动投递台 / 求职进度」的单一事实来源。
    """

    __tablename__ = "job_applications"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    role: Mapped[str] = mapped_column(String(255), nullable=False)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    channel: Mapped[str] = mapped_column(String(64), nullable=False, default="官网", server_default="官网")
    # PENDING / APPLIED / SCREENING / ASSESSMENT / INTERVIEW / OFFER / CLOSED
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    applied_at: Mapped[date | None] = mapped_column(Date, nullable=True)
    next_action: Mapped[str | None] = mapped_column(Text, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    # --- M3 投递版本绑定：回答「我当初投的是哪份简历」---
    jd_source: Mapped[str | None] = mapped_column(String(512), nullable=True)
    resume_version_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("target_resumes.id", ondelete="SET NULL"), nullable=True
    )
    studio_revision: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pdf_snapshot_path: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # --- M3 打招呼话术（简洁/详细，可编辑；系统只生成草稿，不自动发送）---
    greeting_short: Mapped[str | None] = mapped_column(Text, nullable=True)
    greeting_long: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile", back_populates="applications")
    mission: Mapped[JobMission | None] = relationship("JobMission")
    resume_version: Mapped["TargetResume | None"] = relationship("TargetResume")


class CandidateJob(Base):
    """候选岗位草稿（批量导入暂存区）。

    链路从「粘贴 → 直接建正式岗位」改为「粘贴 → 生成候选草稿 → 用户逐条确认 → 导入正式 JobMission」。
    - `source_text` 保存本次粘贴的完整原文，`source_excerpt` 必须是原文里能查到的摘录（可回溯）；
    - `source_hash` + `source_excerpt_hash` 做批次幂等，同批同段不重复生产草稿；
    - `imported_mission_id` 非空即已导入，二次导入直接返回该 mission（幂等）。
    """

    __tablename__ = "candidate_jobs"
    __table_args__ = (
        UniqueConstraint(
            "profile_id",
            "source_hash",
            "source_excerpt_hash",
            name="uq_candidate_jobs_profile_source_excerpt",
        ),
    )

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    source_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="PASTE", server_default="PASTE")
    recognition_source: Mapped[str] = mapped_column(
        String(32), nullable=False, default="HEURISTIC_SPLIT", server_default="HEURISTIC_SPLIT"
    )
    source_excerpt: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    source_excerpt_hash: Mapped[str] = mapped_column(String(64), nullable=False, default="", server_default="")
    company: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str | None] = mapped_column(String(255), nullable=True)
    location: Mapped[str | None] = mapped_column(String(255), nullable=True)
    # --- 026_webform_and_ingest：岗位统一入口的来源与采集元数据 ---
    source_url: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    collected_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    parse_status: Mapped[str] = mapped_column(String(32), nullable=False, default="PARSED", server_default="PARSED")
    dedupe_key: Mapped[str | None] = mapped_column(String(64), nullable=True, index=True)
    raw_payload: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    imported_mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class WebFormRecord(Base):
    """网申填表历史（只记录字段填写，不记录密码/验证码，永不自动提交）。

    一条记录 = 一次「读取表单 → 预览 → 用户确认填写」的操作。
    ``assignments`` 保存逐字段的填写结果（含跳过项与原因）；
    ``summary`` 保存成功/失败/待确认的数量统计。
    """

    __tablename__ = "web_form_records"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    page_url: Mapped[str] = mapped_column(String(1024), nullable=False, default="", server_default="")
    page_title: Mapped[str | None] = mapped_column(String(512), nullable=True)
    # PREVIEW / FILLED / FAILED / ABORTED
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PREVIEW", server_default="PREVIEW")
    assignments: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    summary: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    profile: Mapped[UserProfile] = relationship("UserProfile")


class AssistantConversation(Base):
    """AI 求职助手「顺顺」会话。surface 区分「侧栏页(page)」与「顺顺浮窗(orb)」两套独立记录。"""

    __tablename__ = "assistant_conversations"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    surface: Mapped[str] = mapped_column(String(16), nullable=False, default="page", server_default="page", index=True)
    title: Mapped[str] = mapped_column(String(255), nullable=False, default="新对话", server_default="新对话")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    messages: Mapped[list["AssistantMessage"]] = relationship(
        "AssistantMessage",
        back_populates="conversation",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (AssistantMessage.created_at, AssistantMessage.id),
    )


class AssistantMessage(Base):
    """助手会话里的一条消息（用户提问 / 助手回答）。"""

    __tablename__ = "assistant_messages"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID] = mapped_column(
        ForeignKey("assistant_conversations.id", ondelete="CASCADE"), nullable=False, index=True
    )
    role: Mapped[str] = mapped_column(String(16), nullable=False)  # user | assistant
    content: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    tool_calls: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    conversation: Mapped[AssistantConversation] = relationship("AssistantConversation", back_populates="messages")


class Referral(Base):
    """内推记录：一次人脉带来的推荐机会。"""

    __tablename__ = "referrals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    company: Mapped[str] = mapped_column(String(255), nullable=False)
    contact: Mapped[str | None] = mapped_column(String(255), nullable=True)   # 内推人
    channel: Mapped[str | None] = mapped_column(String(128), nullable=True)   # 渠道/关系
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="进行中", server_default="进行中")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


class Reminder(Base):
    """求职提醒：什么时候该做什么（面试/测评截止/跟进 HR）。"""

    __tablename__ = "reminders"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    title: Mapped[str] = mapped_column(String(255), nullable=False)
    due_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    status: Mapped[str] = mapped_column(String(24), nullable=False, default="PENDING", server_default="PENDING")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 题库（目标三）：独立于 mission 的模拟面试流程，可复用、可保存
# ---------------------------------------------------------------------------


class QuestionBank(Base):
    """题库容器：可挂某个岗位（mission_id 非空）或作为通用题库（mission_id 为空）。"""

    __tablename__ = "question_banks"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    name: Mapped[str] = mapped_column(String(255), nullable=False, default="默认题库", server_default="默认题库")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    items: Mapped[list["QuestionItem"]] = relationship(
        "QuestionItem",
        back_populates="bank",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (QuestionItem.sort_order, QuestionItem.id),
    )


class QuestionItem(Base):
    """一道题：三分类 BASIC / PROJECT_DEEP_DIVE / HR_QUESTIONS；来源 MODEL 或 REAL_INTERVIEW。

    第六阶段扩展字段：每道题都必须能回答「为什么问这题 / 和 JD 哪条要求有关 /
    用简历哪段经历回答 / 哪些事实可以说 / 哪些不能编造 / 面试官可能怎么追问」。
    """

    __tablename__ = "question_items"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    bank_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_banks.id", ondelete="CASCADE"), nullable=False, index=True
    )
    category: Mapped[str] = mapped_column(String(32), nullable=False)
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    interviewer_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    question_text: Mapped[str] = mapped_column(Text, nullable=False)
    # MODEL / REAL_INTERVIEW
    source: Mapped[str] = mapped_column(String(24), nullable=False, default="MODEL", server_default="MODEL")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    # --- 第六阶段：题目必须回答的问题 ---
    jd_requirement_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    experience_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    why_asked: Mapped[str | None] = mapped_column(Text, nullable=True)
    expected_evidence: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    followup_paths: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    sample_answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_flags: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    sort_order: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    bank: Mapped[QuestionBank] = relationship("QuestionBank", back_populates="items")
    reference_answers: Mapped[list["ReferenceAnswer"]] = relationship(
        "ReferenceAnswer",
        back_populates="question_item",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (ReferenceAnswer.created_at, ReferenceAnswer.id),
    )


class ReferenceAnswer(Base):
    """参考答案：只能基于已确认 ResumeClaim + confirmed target resume。

    事实门控失败时 grounding 落 UNKNOWN / NEEDS_CONFIRMATION，且不得编造事实。
    """

    __tablename__ = "reference_answers"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    question_item_id: Mapped[UUID] = mapped_column(
        ForeignKey("question_items.id", ondelete="CASCADE"), nullable=False, index=True
    )
    answer_text: Mapped[str] = mapped_column(Text, nullable=False)
    # BULLETS / TARGET_RESUME / UNKNOWN / NEEDS_CONFIRMATION
    grounding: Mapped[str] = mapped_column(String(32), nullable=False, default="NEEDS_CONFIRMATION", server_default="NEEDS_CONFIRMATION")
    evidence_refs: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    question_item: Mapped[QuestionItem] = relationship("QuestionItem", back_populates="reference_answers")


# ---------------------------------------------------------------------------
# 第七阶段：任务级模拟面试（围绕岗位版简历 + 已确认事实，逐轮追问与评分）
# ---------------------------------------------------------------------------


class MockInterviewSession(Base):
    """任务级模拟面试会话（不绑定单条 claim）。

    启动参数：mission_id / target_resume_id / interview_type / difficulty /
    interviewer_style / rounds。
    """

    __tablename__ = "mock_interview_sessions"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mission_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("job_missions.id", ondelete="SET NULL"), nullable=True, index=True
    )
    target_resume_id: Mapped[UUID | None] = mapped_column(
        ForeignKey("target_resumes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    interview_type: Mapped[str] = mapped_column(String(32), nullable=False, default="TECHNICAL", server_default="TECHNICAL")
    difficulty: Mapped[str] = mapped_column(String(16), nullable=False, default="MEDIUM", server_default="MEDIUM")
    interviewer_style: Mapped[str | None] = mapped_column(String(64), nullable=True)
    rounds: Mapped[int] = mapped_column(Integer, nullable=False, default=3, server_default="3")
    current_round: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="ACTIVE", server_default="ACTIVE")
    config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    report: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    turns: Mapped[list["MockInterviewTurn"]] = relationship(
        "MockInterviewTurn",
        back_populates="session",
        cascade="all, delete-orphan",
        passive_deletes=True,
        order_by=lambda: (MockInterviewTurn.round_number, MockInterviewTurn.id),
    )


class MockInterviewTurn(Base):
    __tablename__ = "mock_interview_turns"
    __table_args__ = (UniqueConstraint("session_id", "round_number", name="uq_mock_interview_turns_round"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    session_id: Mapped[UUID] = mapped_column(
        ForeignKey("mock_interview_sessions.id", ondelete="CASCADE"), nullable=False, index=True
    )
    round_number: Mapped[int] = mapped_column(Integer, nullable=False)
    question: Mapped[str] = mapped_column(Text, nullable=False)
    question_source: Mapped[str] = mapped_column(String(32), nullable=False, default="JD_DERIVED", server_default="JD_DERIVED")
    answer: Mapped[str | None] = mapped_column(Text, nullable=True)
    # 回答评估：answer_coverage / evidence_status / missing_evidence / unsupported_claims /
    # jd_alignment / next_followup / improvement_tip
    evaluation: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    session: Mapped[MockInterviewSession] = relationship("MockInterviewSession", back_populates="turns")


# ---------------------------------------------------------------------------
# 模板草稿（目标五）：参考模板识别后先落草稿，用户确认后才作为可用模板
# ---------------------------------------------------------------------------


class ResumeTemplateDraft(Base):
    """参考模板（HTML/图片/PDF/DOCX）识别后的模板草稿。"""

    __tablename__ = "resume_template_drafts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(
        ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True
    )
    # IMAGE / PDF / DOCX / HTML
    source_kind: Mapped[str] = mapped_column(String(16), nullable=False)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    layout_config: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    sanitized_html: Mapped[str | None] = mapped_column(Text, nullable=True)
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="DRAFT", server_default="DRAFT")
    warnings: Mapped[list] = mapped_column(JSON, nullable=False, default=list, server_default="[]")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())


# ---------------------------------------------------------------------------
# 助手写入安全（目标七）：提案 → 用户确认 → 执行 → 回执
# ---------------------------------------------------------------------------


class WriteProposal(Base):
    """助手写入提案：助手不直接落库，先产提案等待用户确认。"""

    __tablename__ = "write_proposals"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    conversation_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    message_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    profile_id: Mapped[UUID | None] = mapped_column(Uuid(as_uuid=True), nullable=True, index=True)
    capability: Mapped[str] = mapped_column(String(64), nullable=False)
    args: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    summary: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # PROPOSED / CONFIRMED / REJECTED / EXECUTED
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="PROPOSED", server_default="PROPOSED")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    receipt: Mapped["WriteReceipt | None"] = relationship(
        "WriteReceipt",
        back_populates="proposal",
        uselist=False,
        cascade="all, delete-orphan",
        passive_deletes=True,
    )


class WriteReceipt(Base):
    """操作回执：确认执行后留痕——做了什么、改了哪条、时间、来源。"""

    __tablename__ = "write_receipts"

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    proposal_id: Mapped[UUID] = mapped_column(
        ForeignKey("write_proposals.id", ondelete="CASCADE"), nullable=False, unique=True, index=True
    )
    target_table: Mapped[str] = mapped_column(String(64), nullable=False)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    diff: Mapped[dict] = mapped_column(JSON, nullable=False, default=dict, server_default="{}")
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())

    proposal: Mapped[WriteProposal] = relationship("WriteProposal", back_populates="receipt")


class FactAttestation(Base):
    """候选事实的核对记录（可信求职 v1.2 · 指令 1.3 / 1.4）。

    存在意义：把「系统提取到 / 用户采纳改写 / 用户核实事实」这三件事分开。
    本表只记录**用户明确核对**的行为；没有本表记录的事实，无论档案状态是
    ``CONFIRMED`` 还是改写状态是 ``ACCEPTED``，都不得视为「用户已核实」。

    ``fact_key`` 是稳定键（如 ``experience:<uuid>:description:0``），同一档案内唯一，
    便于在事实被编辑后重新判定是否需要再次核对。
    """

    __tablename__ = "fact_attestations"
    __table_args__ = (UniqueConstraint("profile_id", "fact_key", name="uq_fact_attestation_profile_key"),)

    id: Mapped[UUID] = mapped_column(Uuid(as_uuid=True), primary_key=True, default=uuid4)
    profile_id: Mapped[UUID] = mapped_column(ForeignKey("user_profiles.id", ondelete="CASCADE"), nullable=False, index=True)
    fact_key: Mapped[str] = mapped_column(String(200), nullable=False)
    fact_text: Mapped[str] = mapped_column(Text, nullable=False, default="", server_default="")
    # 事实来源：SOURCE_EXTRACTED / USER_PROVIDED / AI_PROPOSED（见 app.fact_trust.FactSource）
    source_kind: Mapped[str] = mapped_column(String(32), nullable=False, default="SOURCE_EXTRACTED", server_default="SOURCE_EXTRACTED")
    source_id: Mapped[str | None] = mapped_column(String(120), nullable=True)
    source_revision: Mapped[str | None] = mapped_column(String(64), nullable=True)
    # 核对状态：UNREVIEWED / USER_ATTESTED / REJECTED（见 app.fact_trust.VerificationStatus）
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="UNREVIEWED", server_default="UNREVIEWED")
    verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    verified_by: Mapped[str | None] = mapped_column(String(64), nullable=True)
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, server_default=func.now())
