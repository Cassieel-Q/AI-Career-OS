from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .dashboard_schemas import DashboardRead, DashboardRequirement, DashboardTargetRole
from .derived_state import derived_state_fingerprint
from .gap_service import get_gap_analysis
from .market_profile_service import market_profile_capabilities
from .priority_service import get_priorities
from .roadmap_service import get_roadmap


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def get_dashboard(db: Session, profile_id: UUID) -> DashboardRead:
    profile = db.get(models.UserProfile, profile_id)
    if profile is None:
        raise _http(404, "Profile not found")
    target = db.scalar(select(models.TargetRole).where(models.TargetRole.profile_id == profile_id))
    if target is None:
        return DashboardRead(
            target_role=None,
            jd_sample_count=0,
            market_ready=False,
            current_week=None,
            progress_ratio=0.0,
            roadmap_id=None,
            replan_available=False,
        )
    jds = db.scalars(select(models.JobDescription).where(models.JobDescription.target_role_id == target.id)).all()
    market = db.scalar(select(models.MarketProfile).where(models.MarketProfile.target_role_id == target.id))
    market_current = bool(market and market.status == "VALID" and market.sample_fingerprint == derived_state_fingerprint(target.id, jds))
    top_requirements = [
        DashboardRequirement(
            name=capability.name,
            category="CAPABILITY",
            occurrence_count=capability.occurrence_count,
            frequency_ratio=capability.frequency_ratio,
        )
        for capability in sorted(market_profile_capabilities(market), key=lambda row: (-row.frequency_ratio, row.name.casefold()))[:5]
    ] if market_current and market else []
    top_gaps = []
    priorities = []
    roadmap = None
    if market_current and profile.status == "CONFIRMED":
        try:
            gap = get_gap_analysis(db, profile_id)
            top_gaps = gap.gaps[:5]
            priorities = get_priorities(db, profile_id).items[:7]
            try:
                roadmap = get_roadmap(db, profile_id)
            except HTTPException:
                roadmap = None
        except HTTPException:
            pass
    upcoming = []
    current_week = None
    progress_ratio = 0.0
    if roadmap:
        for week in roadmap.weeks:
            pending = [task for task in week.tasks if task.status.value in {"TODO", "IN_PROGRESS"}]
            if pending and current_week is None:
                current_week = week.week_number
            upcoming.extend(pending)
        upcoming = upcoming[:5]
        current_week = current_week or 4
        progress_ratio = roadmap.progress_ratio
    return DashboardRead(
        target_role=DashboardTargetRole(id=str(target.id), role_code=target.role_code, role_name=dict({
            "AI_PRODUCT_MANAGER": "AI Product Manager",
            "AI_APPLICATION_ENGINEER": "AI Application Engineer",
            "AI_SOLUTION_CONSULTANT": "AI Solution Consultant",
            "LLM_ALGORITHM_ENGINEER": "LLM Algorithm Engineer",
            "AI_DATA_ANALYST": "AI Data Analyst",
            "AI_PRODUCT_OPERATIONS": "AI Product Operations",
        }).get(target.role_code, target.role_code)),
        jd_sample_count=len(jds),
        market_ready=market_current,
        top_requirements=top_requirements,
        top_gaps=top_gaps,
        confirmed_priorities=priorities,
        current_week=current_week,
        upcoming_tasks=upcoming,
        progress_ratio=progress_ratio,
        roadmap_id=str(roadmap.id) if roadmap else None,
        replan_available=roadmap is not None,
    )
