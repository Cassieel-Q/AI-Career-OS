"""求职工作台总览（全局口径）。

背景：总览页原先用 `/profiles/{id}/tracker` + `/profiles/{id}/resumes`（按当前档案），
而投递页用 `/applications`（跨档案全部），两套口径混在一起就会「总览说 0 投递、
点进投递页却有 5 条」。这里统一按全局统计，保证与各模块页面数字一致。
"""
from __future__ import annotations

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from . import models
from .database import get_db

router = APIRouter(prefix="/api/v1", tags=["overview"])

_APPLIED_STATUSES = {"APPLIED", "SCREENING", "ASSESSMENT"}
_INTERVIEWING_STATUSES = {"INTERVIEW", "OFFER"}


def _stage_of(application: models.JobApplication | None) -> str:
    """把投递状态收敛成前端既有的 5 档 stage。"""
    status = (application.status or "").upper() if application is not None else ""
    if status == "OFFER":
        return "COMPLETED"
    if status in {"SCREENING", "ASSESSMENT", "INTERVIEW"}:
        return "INTERVIEW"
    if status == "APPLIED":
        return "APPLIED"
    if status == "CLOSED":
        return "ARCHIVED"
    return "PREPARING"


class OverviewTotals(BaseModel):
    missions: int
    resumes: int
    applications: int
    applied: int
    interviewing: int


class OverviewMission(BaseModel):
    mission_id: str
    company: str
    role: str
    location: str | None = None
    stage: str


class OverviewRead(BaseModel):
    totals: OverviewTotals
    recent_missions: list[OverviewMission]


@router.get("/overview", response_model=OverviewRead)
def read_overview(db: Session = Depends(get_db)) -> OverviewRead:
    mission_count = db.scalar(select(func.count()).select_from(models.JobMission)) or 0
    resume_count = db.scalar(select(func.count()).select_from(models.TargetResume)) or 0

    applications = list(db.scalars(select(models.JobApplication)).all())
    applied = sum(1 for row in applications if (row.status or "").upper() in _APPLIED_STATUSES)
    interviewing = sum(1 for row in applications if (row.status or "").upper() in _INTERVIEWING_STATUSES)

    by_mission = {row.mission_id: row for row in applications if row.mission_id is not None}
    recent = [
        OverviewMission(
            mission_id=str(mission.id),
            company=mission.company,
            role=mission.role,
            location=mission.location,
            stage=_stage_of(by_mission.get(mission.id)),
        )
        for mission in db.scalars(
            select(models.JobMission).order_by(models.JobMission.updated_at.desc()).limit(6)
        ).all()
    ]

    return OverviewRead(
        totals=OverviewTotals(
            missions=mission_count,
            resumes=resume_count,
            applications=len(applications),
            applied=applied,
            interviewing=interviewing,
        ),
        recent_missions=recent,
    )
