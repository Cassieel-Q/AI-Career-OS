"""Career hub aggregates: 求职进度 / 事实台账 / 简历中心。

复用现有 JobMission / InterviewOutcome / ResumeClaim / TargetResume 表，
只做跨 mission 的聚合读取，不新增 schema、不引入新迁移。
"""
from __future__ import annotations

from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from . import models
from .database import get_db


router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class TrackerItemRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission_id: str
    company: str
    role: str
    location: str | None = None
    seniority: str = "UNKNOWN"
    stage: str = "PREPARING"
    outcome_status: str | None = None
    resume_ready: bool = False
    outcome_count: int = 0
    updated_at: datetime | None = None


class TrackerRead(BaseModel):
    profile_id: str
    total: int = 0
    preparing: int = 0
    applied: int = 0
    interviewing: int = 0
    completed: int = 0
    applications: list[TrackerItemRead] = Field(default_factory=list)


class ClaimRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    mission_id: str | None = None
    company: str = "未知"
    role: str = "未知"
    claim: str
    current_text: str | None = None
    suggested_text: str | None = None
    readiness_status: str
    confidence: float = 0.0
    risk_reason: str = ""
    evidence_refs: list = Field(default_factory=list)
    matched_capabilities: list = Field(default_factory=list)


class ClaimsRead(BaseModel):
    profile_id: str
    total: int = 0
    confirmed: int = 0
    needs_confirmation: int = 0
    claims: list[ClaimRead] = Field(default_factory=list)


class ResumeOverviewItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission_id: str
    resume_id: str
    company: str
    role: str
    version: int
    status: str
    bullet_count: int = 0
    confirmed: bool = False
    updated_at: datetime | None = None


class ResumesOverviewRead(BaseModel):
    profile_id: str
    total: int = 0
    resumes: list[ResumeOverviewItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


_PREPARING_STATES = {"DRAFT", "RESUME_PREP", "STRENGTHENING", "INTERVIEW_PREP", "APPLIED"}


def _stage_of(status: str) -> str:
    status = (status or "").upper()
    if status in {"APPLIED"}:
        return "APPLIED"
    if status == "INTERVIEWING":
        return "INTERVIEW"
    if status == "COMPLETED":
        return "COMPLETED"
    if status == "ARCHIVED":
        return "ARCHIVED"
    return "PREPARING"


# ---------------------------------------------------------------------------
# Tracker
# ---------------------------------------------------------------------------


def get_tracker(db: Session, profile_id: UUID) -> TrackerRead:
    _profile(db, profile_id)

    missions = list(
        db.scalars(
            select(models.JobMission)
            .where(models.JobMission.profile_id == profile_id, models.JobMission.status != "ARCHIVED")
            .order_by(models.JobMission.updated_at.desc())
        ).all()
    )

    # 每个 mission 最新的投递结果
    outcomes_by_mission: dict[UUID, list[models.InterviewOutcome]] = {}
    if missions:
        outcome_rows = db.scalars(
            select(models.InterviewOutcome)
            .where(models.InterviewOutcome.mission_id.in_([m.id for m in missions]))
            .order_by(models.InterviewOutcome.created_at.desc())
        ).all()
        for row in outcome_rows:
            outcomes_by_mission.setdefault(row.mission_id, []).append(row)

    applications: list[TrackerItemRead] = []
    for mission in missions:
        outcomes = outcomes_by_mission.get(mission.id, [])
        latest = outcomes[0] if outcomes else None
        applications.append(
            TrackerItemRead(
                mission_id=str(mission.id),
                company=mission.company,
                role=mission.role,
                location=mission.location,
                seniority=mission.seniority,
                stage=_stage_of(mission.status),
                outcome_status=latest.application_status if latest else None,
                resume_ready=bool(mission.resume_source),
                outcome_count=len(outcomes),
                updated_at=mission.updated_at,
            )
        )

    def _count(stage: str) -> int:
        return sum(1 for item in applications if item.stage == stage)

    return TrackerRead(
        profile_id=str(profile_id),
        total=len(applications),
        preparing=_count("PREPARING"),
        applied=_count("APPLIED"),
        interviewing=_count("INTERVIEW"),
        completed=_count("COMPLETED"),
        applications=applications,
    )


# ---------------------------------------------------------------------------
# Claims（事实台账）
# ---------------------------------------------------------------------------


def get_claims(db: Session, profile_id: UUID) -> ClaimsRead:
    _profile(db, profile_id)

    claims = list(
        db.scalars(
            select(models.ResumeClaim)
            .where(models.ResumeClaim.profile_id == profile_id)
            .order_by(models.ResumeClaim.updated_at.desc())
        ).all()
    )

    missions = list(
        db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all()
    )
    mission_by_target_job: dict[UUID, models.JobMission] = {}
    for mission in missions:
        mission_by_target_job[mission.target_job_id] = mission

    items: list[ClaimRead] = []
    for claim in claims:
        mission = mission_by_target_job.get(claim.target_job_id)
        items.append(
            ClaimRead(
                id=str(claim.id),
                mission_id=str(mission.id) if mission else None,
                company=mission.company if mission else "未知",
                role=mission.role if mission else "未知",
                claim=claim.claim,
                current_text=claim.current_text,
                suggested_text=claim.suggested_text,
                readiness_status=claim.readiness_status,
                confidence=claim.confidence,
                risk_reason=claim.risk_reason,
                evidence_refs=list(claim.evidence_refs or []),
                matched_capabilities=list(claim.matched_capabilities or []),
            )
        )

    confirmed = sum(
        1 for item in items if (item.readiness_status or "").upper() in {"READY", "CONFIRMED", "SUPPORTED"}
    )
    needs = sum(
        1 for item in items if (item.readiness_status or "").upper() in {"NEEDS_CONFIRMATION", "UNSUPPORTED", "NEEDS_EVIDENCE"}
    )

    return ClaimsRead(
        profile_id=str(profile_id),
        total=len(items),
        confirmed=confirmed,
        needs_confirmation=needs,
        claims=items,
    )


# ---------------------------------------------------------------------------
# Resumes overview（简历中心）
# ---------------------------------------------------------------------------


def get_resumes_overview(db: Session, profile_id: UUID) -> ResumesOverviewRead:
    _profile(db, profile_id)

    resumes = list(
        db.scalars(
            select(models.TargetResume)
            .join(models.JobMission, models.TargetResume.mission_id == models.JobMission.id)
            .where(models.JobMission.profile_id == profile_id)
            .options(selectinload(models.TargetResume.bullets))
            .order_by(models.TargetResume.updated_at.desc())
        ).all()
    )

    mission_ids = {resume.mission_id for resume in resumes}
    missions = list(
        db.scalars(select(models.JobMission).where(models.JobMission.id.in_(mission_ids))).all()
    ) if mission_ids else []
    mission_by_id = {mission.id: mission for mission in missions}

    studio_docs = {
        doc.mission_id: doc
        for doc in db.scalars(
            select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id.in_(mission_ids))
        ).all()
    } if mission_ids else {}

    items: list[ResumeOverviewItem] = []
    for resume in resumes:
        mission = mission_by_id.get(resume.mission_id)
        studio = studio_docs.get(resume.mission_id)
        items.append(
            ResumeOverviewItem(
                mission_id=str(resume.mission_id),
                resume_id=str(resume.id),
                company=mission.company if mission else "未知",
                role=mission.role if mission else "未知",
                version=resume.version,
                status=resume.status,
                bullet_count=len(resume.bullets),
                confirmed=bool(studio and studio.confirmed_revision == resume.version),
                updated_at=resume.updated_at,
            )
        )

    return ResumesOverviewRead(profile_id=str(profile_id), total=len(items), resumes=items)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/tracker", response_model=TrackerRead)
def read_tracker(profile_id: UUID, db: Session = Depends(get_db)):
    return get_tracker(db, profile_id)


@router.get("/profiles/{profile_id}/claims", response_model=ClaimsRead)
def read_claims(profile_id: UUID, db: Session = Depends(get_db)):
    return get_claims(db, profile_id)


@router.get("/profiles/{profile_id}/resumes", response_model=ResumesOverviewRead)
def read_resumes_overview(profile_id: UUID, db: Session = Depends(get_db)):
    return get_resumes_overview(db, profile_id)
