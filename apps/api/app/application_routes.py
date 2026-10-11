"""投递台（Job Applications）与岗位广场（Job Plaza）聚合。

- JobApplication：一家公司一个岗位一条投递动作记录，状态可单向推进。
- Plaza：跨岗位聚合浏览 + 准备度评分 + 一键加入投递台。
"""
from __future__ import annotations

from datetime import date, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .database import get_db


router = APIRouter(prefix="/api/v1")

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

APPLICATION_STATUSES = (
    "PENDING",      # 待投递
    "APPLIED",      # 已投递
    "SCREENING",    # 筛选中
    "ASSESSMENT",   # 测评 / 笔试
    "INTERVIEW",    # 面试
    "OFFER",        # Offer
    "CLOSED",       # 已结束
)

# workflow_state → 准备度评分（0–100）
_PREP_SCORE: dict[str, int] = {
    "JD_REQUIRED": 5,
    "JOB_ANALYZING": 5,
    "ROLE_UNDERSTOOD": 15,
    "RESUME_REQUIRED": 25,
    "RESUME_SELECTED": 25,
    "EXPERIENCE_SELECTION_REQUIRED": 40,
    "EXPERIENCES_CONFIRMED": 40,
    "RESUME_STRATEGY_REQUIRED": 55,
    "RESUME_STRATEGY_CONFIRMED": 55,
    "TARGET_RESUME_DRAFT": 70,
    "TARGET_RESUME_CONFIRMED": 82,
    "STRESS_TEST_REQUIRED": 85,
    "STRENGTHENING_REQUIRED": 85,
    "PROOF_IN_PROGRESS": 85,
    "CLAIM_REEVALUATION_REQUIRED": 85,
    "RESUME_UPGRADE_AVAILABLE": 85,
    "INTERVIEW_PREP_READY": 92,
    "INTERVIEW_PREP": 88,
    "INTERVIEW_IN_PROGRESS": 96,
    "INTERVIEW_DEBRIEF_READY": 96,
    "OUTCOME": 96,
}

# 投递状态 → 推进阶段（用于与 tracker 对齐展示）
APPLICATION_STAGE: dict[str, str] = {
    "PENDING": "PREPARING",
    "APPLIED": "APPLIED",
    "SCREENING": "APPLIED",
    "ASSESSMENT": "APPLIED",
    "INTERVIEW": "INTERVIEW",
    "OFFER": "INTERVIEW",
    "CLOSED": "COMPLETED",
}


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------


class ApplicationCreate(BaseModel):
    mission_id: UUID | None = None
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    channel: str = Field(default="官网", max_length=64)
    status: str = Field(default="PENDING", max_length=24)
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None


class ApplicationUpdate(BaseModel):
    company: str | None = Field(default=None, max_length=255)
    role: str | None = Field(default=None, max_length=255)
    location: str | None = Field(default=None, max_length=255)
    channel: str | None = Field(default=None, max_length=64)
    status: str | None = Field(default=None, max_length=24)
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None


class ApplicationRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    profile_id: str
    mission_id: str | None = None
    company: str
    role: str
    location: str | None = None
    channel: str
    status: str
    stage: str
    applied_at: date | None = None
    next_action: str | None = None
    notes: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None


class ApplicationsRead(BaseModel):
    total: int = 0
    pending: int = 0
    applied: int = 0
    interviewing: int = 0
    offer: int = 0
    applications: list[ApplicationRead] = Field(default_factory=list)


class PlazaItem(BaseModel):
    model_config = ConfigDict(extra="ignore")

    mission_id: str
    profile_id: str
    company: str
    role: str
    location: str | None = None
    seniority: str = "UNKNOWN"
    workflow_state: str = "JD_REQUIRED"
    prep_score: int = 0
    resume_ready: bool = False
    target_resume_confirmed: bool = False
    application_id: str | None = None
    application_status: str | None = None
    updated_at: datetime | None = None


class PlazaRead(BaseModel):
    total: int = 0
    applied: int = 0
    ready: int = 0
    items: list[PlazaItem] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


def _application_read(row: models.JobApplication) -> ApplicationRead:
    return ApplicationRead(
        id=str(row.id),
        profile_id=str(row.profile_id),
        mission_id=str(row.mission_id) if row.mission_id else None,
        company=row.company,
        role=row.role,
        location=row.location,
        channel=row.channel,
        status=row.status,
        stage=APPLICATION_STAGE.get(row.status, "PREPARING"),
        applied_at=row.applied_at,
        next_action=row.next_action,
        notes=row.notes,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _prep_score(workflow_state: str, *, target_resume_confirmed: bool = False) -> int:
    score = _PREP_SCORE.get((workflow_state or "JD_REQUIRED").upper(), 30)
    # 岗位版本已确认是「简历已备」的硬指标，准备度至少 82。
    if target_resume_confirmed:
        score = max(score, 82)
    return score


# ---------------------------------------------------------------------------
# Applications CRUD
# ---------------------------------------------------------------------------


@router.get("/profiles/{profile_id}/applications", response_model=ApplicationsRead)
def list_applications(profile_id: UUID, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            select(models.JobApplication)
            .where(models.JobApplication.profile_id == profile_id)
            .order_by(models.JobApplication.updated_at.desc())
        ).all()
    )
    applications = [_application_read(row) for row in rows]
    return ApplicationsRead(
        total=len(applications),
        pending=sum(1 for a in applications if a.status == "PENDING"),
        applied=sum(1 for a in applications if a.status in {"APPLIED", "SCREENING", "ASSESSMENT"}),
        interviewing=sum(1 for a in applications if a.status in {"INTERVIEW", "OFFER"}),
        offer=sum(1 for a in applications if a.status == "OFFER"),
        applications=applications,
    )


@router.post("/profiles/{profile_id}/applications", response_model=ApplicationRead, status_code=201)
def create_application(profile_id: UUID, payload: ApplicationCreate, db: Session = Depends(get_db)):
    _profile(db, profile_id)
    status = payload.status.upper()
    if status not in APPLICATION_STATUSES:
        raise HTTPException(status_code=422, detail=f"无效的投递状态：{payload.status}")
    row = models.JobApplication(
        profile_id=profile_id,
        mission_id=payload.mission_id,
        company=payload.company.strip(),
        role=payload.role.strip(),
        location=payload.location,
        channel=payload.channel.strip() or "官网",
        status=status,
        applied_at=payload.applied_at,
        next_action=payload.next_action,
        notes=payload.notes,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return _application_read(row)


@router.patch("/applications/{application_id}", response_model=ApplicationRead)
def update_application(application_id: UUID, payload: ApplicationUpdate, db: Session = Depends(get_db)):
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    updates = payload.model_dump(exclude_unset=True)
    if "status" in updates and updates["status"] is not None:
        status = str(updates["status"]).upper()
        if status not in APPLICATION_STATUSES:
            raise HTTPException(status_code=422, detail=f"无效的投递状态：{updates['status']}")
        updates["status"] = status
    for key, value in updates.items():
        if value is None and key not in {"location", "applied_at", "next_action", "notes"}:
            continue
        setattr(row, key, value)
    row.updated_at = datetime.now()
    db.commit()
    db.refresh(row)
    return _application_read(row)


@router.delete("/applications/{application_id}", status_code=204)
def delete_application(application_id: UUID, db: Session = Depends(get_db)):
    row = db.get(models.JobApplication, application_id)
    if row is None:
        raise HTTPException(status_code=404, detail="投递记录不存在")
    db.delete(row)
    db.commit()
    return None


# ---------------------------------------------------------------------------
# Plaza（岗位广场）
# ---------------------------------------------------------------------------


@router.get("/plaza", response_model=PlazaRead)
def read_plaza(profile_id: UUID | None = None, db: Session = Depends(get_db)):
    query = select(models.JobMission).where(models.JobMission.status != "ARCHIVED")
    if profile_id is not None:
        query = query.where(models.JobMission.profile_id == profile_id)
    missions = list(db.scalars(query.order_by(models.JobMission.updated_at.desc())).all())

    mission_ids = [m.id for m in missions]
    applications_by_mission: dict[UUID, models.JobApplication] = {}
    if mission_ids:
        app_rows = db.scalars(
            select(models.JobApplication)
            .where(models.JobApplication.mission_id.in_(mission_ids))
            .order_by(models.JobApplication.updated_at.desc())
        ).all()
        for row in app_rows:
            if row.mission_id not in applications_by_mission:
                applications_by_mission[row.mission_id] = row

    target_resumes_by_mission: dict[UUID, bool] = {}
    if mission_ids:
        resume_rows = db.scalars(
            select(models.TargetResume).where(models.TargetResume.mission_id.in_(mission_ids))
        ).all()
        for row in resume_rows:
            if row.status == "CONFIRMED":
                target_resumes_by_mission[row.mission_id] = True

    items: list[PlazaItem] = []
    for mission in missions:
        application = applications_by_mission.get(mission.id)
        confirmed = bool(target_resumes_by_mission.get(mission.id))
        items.append(
            PlazaItem(
                mission_id=str(mission.id),
                profile_id=str(mission.profile_id),
                company=mission.company,
                role=mission.role,
                location=mission.location,
                seniority=mission.seniority,
                workflow_state=mission.workflow_state,
                prep_score=_prep_score(mission.workflow_state, target_resume_confirmed=confirmed),
                resume_ready=bool(mission.resume_source),
                target_resume_confirmed=confirmed,
                application_id=str(application.id) if application else None,
                application_status=application.status if application else None,
                updated_at=mission.updated_at,
            )
        )

    return PlazaRead(
        total=len(items),
        applied=sum(1 for i in items if i.application_id),
        ready=sum(1 for i in items if i.target_resume_confirmed),
        items=items,
    )
