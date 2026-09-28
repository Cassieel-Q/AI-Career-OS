from __future__ import annotations

from datetime import datetime, timezone
import logging
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .gap_service import _current_context
from .market_profile_service import market_profile_capabilities
from .priority_service import _ensure_priorities, _load_analysis
from .roadmap_provider import (
    RoadmapProviderConnectionError,
    RoadmapProviderInvalidResponseError,
    RoadmapProviderNotConfiguredError,
    RoadmapProviderAuthenticationError,
    RoadmapProviderTimeoutError,
    get_roadmap_provider,
)
from .roadmap_schemas import RoadmapRead, RoadmapTaskRead, RoadmapWeekRead, RoadmapProposal, RoadmapTaskUpdate, TaskStatus
from .derived_state import priority_fingerprint


ROADMAP_TOLERANCE = 1.15
logger = logging.getLogger(__name__)


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def validate_roadmap_workload(proposal: RoadmapProposal, weekly_hours: int) -> None:
    total = sum(task.estimated_minutes for week in proposal.weeks for task in week.tasks)
    allowed = weekly_hours * 60 * 4 * ROADMAP_TOLERANCE
    if total > allowed:
        raise _http(422, f"Roadmap workload exceeds the {weekly_hours}-hour weekly budget")


def _read(roadmap: models.Roadmap) -> RoadmapRead:
    tasks = [task for week in roadmap.weeks for task in week.tasks]
    done = sum(task.status == TaskStatus.DONE.value for task in tasks)
    progress = done / len(tasks) if tasks else 0.0
    return RoadmapRead(
        id=roadmap.id,
        profile_id=roadmap.profile_id,
        revision=roadmap.revision,
        weekly_hours=roadmap.weekly_hours,
        status=roadmap.status,
        progress_ratio=progress,
        weeks=[RoadmapWeekRead(
            id=week.id,
            week_number=week.week_number,
            objective=week.objective,
            focus_gap_ids=[UUID(str(value)) for value in (week.focus_gap_ids or [])],
            measurable_outcome=week.measurable_outcome,
            tasks=[RoadmapTaskRead(
                id=task.id,
                gap_id=task.gap_id,
                title=task.title,
                objective=task.objective,
                estimated_minutes=task.estimated_minutes,
                completion_criteria=task.completion_criteria,
                status=task.status,
                sort_order=task.sort_order,
                completed_at=task.completed_at,
            ) for task in week.tasks],
        ) for week in roadmap.weeks],
    )


def _inputs(
    db: Session,
    profile_id: UUID,
    *,
    for_update: bool = False,
) -> tuple[models.UserProfile, models.TargetRole, models.GapAnalysis, list[models.GapPriority], int, str]:
    profile, market, _profile_fingerprint = _current_context(db, profile_id)
    target = market.target_role
    analysis = _load_analysis(db, profile_id)
    if for_update:
        # Serialize initial/retry generation per analysis in PostgreSQL. The
        # lock is held through provider validation and the final insert, so a
        # second tab reuses the persisted roadmap instead of calling the model.
        analysis = db.scalar(
            select(models.GapAnalysis)
            .where(models.GapAnalysis.id == analysis.id)
            .with_for_update()
        ) or analysis
    priorities = _ensure_priorities(db, analysis, profile.career_preference)
    db.flush()
    weekly_hours = profile.career_preference.weekly_hours if profile.career_preference else 1
    return profile, target, analysis, priorities, weekly_hours, priority_fingerprint(priorities)


def _profile_evidence(profile: models.UserProfile) -> list[dict[str, str]]:
    evidence: list[dict[str, str]] = []
    for collection, kind, fields in (
        (profile.education, "education", ("institution", "degree", "field_of_study")),
        (profile.skills, "skill", ("name", "proficiency")),
        (profile.experiences, "experience", ("title", "organization", "description")),
        (profile.certifications, "certification", ("name", "issuer", "date")),
    ):
        for row in collection:
            value = " | ".join(str(getattr(row, field)) for field in fields if getattr(row, field, None)).strip()
            if value:
                evidence.append({"id": str(row.id), "kind": kind, "value": value[:600]})
    return evidence[:50]


def get_roadmap(db: Session, profile_id: UUID) -> RoadmapRead:
    _profile, _target, analysis, _priorities, weekly_hours, fingerprint = _inputs(db, profile_id)
    roadmap = db.scalar(select(models.Roadmap).where(
        models.Roadmap.profile_id == profile_id,
        models.Roadmap.gap_analysis_id == analysis.id,
        models.Roadmap.status == "VALID",
        models.Roadmap.weekly_hours == weekly_hours,
        models.Roadmap.priority_fingerprint == fingerprint,
    ).order_by(models.Roadmap.revision.desc()))
    if roadmap is None:
        raise _http(404, "四周计划尚未生成")
    return _read(roadmap)


def generate_roadmap(db: Session, profile_id: UUID, provider=None, remaining_context: dict | None = None, *, force_new: bool = False) -> RoadmapRead:
    profile, target, analysis, priorities, weekly_hours, fingerprint = _inputs(db, profile_id, for_update=True)
    existing = db.scalar(select(models.Roadmap).where(
        models.Roadmap.profile_id == profile_id,
        models.Roadmap.gap_analysis_id == analysis.id,
        models.Roadmap.status == "VALID",
        models.Roadmap.weekly_hours == weekly_hours,
        models.Roadmap.priority_fingerprint == fingerprint,
    ).order_by(models.Roadmap.revision.desc()))
    if existing is not None and not force_new:
        return _read(existing)
    provider = provider or get_roadmap_provider()
    capabilities = {capability.id: capability for capability in market_profile_capabilities(target.market_profile)}
    priority_rows = []
    for priority in sorted(priorities, key=lambda row: (row.user_rank is None, row.user_rank if row.user_rank is not None else row.system_rank)):
        capability = capabilities.get(priority.gap.market_requirement.id)
        if capability is None:
            continue
        priority_rows.append({
            "gap_id": str(priority.gap_id),
            "capability_id": str(capability.id),
            "capability_name": capability.name,
            "capability_summary": capability.summary,
            "state": priority.gap.state,
            "lane": priority.lane,
            "system_reason": priority.system_reason,
            "source_jd_count": capability.occurrence_count,
            "atomic_requirements": [
                {"id": str(item.id), "name": item.name, "category": item.category.value}
                for item in capability.atomic_requirements
            ],
        })
    compact_context = {
        "profile_evidence": _profile_evidence(profile),
        "capability_count": len(capabilities),
        "requested_weeks": 4,
    }
    if remaining_context:
        compact_context.update(remaining_context)
    try:
        proposal = provider.plan(target_role=target.role_code, weekly_hours=weekly_hours, priorities=priority_rows, remaining_context=compact_context)
        validate_roadmap_workload(proposal, weekly_hours)
    except HTTPException:
        raise
    except Exception as exc:
        if isinstance(exc, RoadmapProviderNotConfiguredError):
            raise _http(503, "四周计划服务尚未配置") from exc
        if isinstance(exc, RoadmapProviderTimeoutError):
            raise _http(504, "四周计划暂时超时，请重试") from exc
        if isinstance(exc, RoadmapProviderAuthenticationError):
            logger.warning("roadmap_provider_failure category=authentication")
            raise _http(502, "四周计划服务认证失败，请检查服务配置后重试") from exc
        if isinstance(exc, RoadmapProviderInvalidResponseError):
            logger.warning("roadmap_provider_failure category=invalid_response reason=%s", exc.reason)
            raise _http(502, f"四周计划返回内容未通过校验（{exc.reason}），请重试") from exc
        if isinstance(exc, RoadmapProviderConnectionError):
            logger.warning("roadmap_provider_failure category=connection")
            raise _http(502, "四周计划暂时失败，请重试") from exc
        logger.warning("roadmap_provider_failure category=unexpected type=%s", type(exc).__name__)
        raise _http(502, "四周计划暂时失败，请重试") from exc
    priority_gap_ids = {priority.gap_id for priority in priorities}
    focus_gap_ids = {focus_gap_id for week in proposal.weeks for focus_gap_id in week.focus_gap_ids}
    task_gap_ids = {task.related_gap_id for week in proposal.weeks for task in week.tasks}
    if not task_gap_ids <= priority_gap_ids or not focus_gap_ids <= priority_gap_ids:
        logger.warning("roadmap_provider_failure category=unknown_gap_reference")
        raise _http(502, "四周计划包含无法核验的差距")
    try:
        previous = db.scalar(select(models.Roadmap).where(models.Roadmap.profile_id == profile_id).order_by(models.Roadmap.revision.desc()))
        revision = (previous.revision + 1) if previous else 1
        if previous and previous.status == "VALID":
            previous.status = "SUPERSEDED"
        roadmap = models.Roadmap(
            profile_id=profile_id,
            gap_analysis_id=analysis.id,
            revision=revision,
            weekly_hours=weekly_hours,
            priority_fingerprint=fingerprint,
            status="VALID",
            supersedes_id=previous.id if previous else None,
        )
        db.add(roadmap)
        db.flush()
        for week_proposal in proposal.weeks:
            week = models.RoadmapWeek(
                roadmap_id=roadmap.id,
                week_number=week_proposal.week_number,
                objective=week_proposal.objective,
                focus_gap_ids=[str(value) for value in week_proposal.focus_gap_ids],
                measurable_outcome=week_proposal.measurable_outcome,
            )
            db.add(week)
            db.flush()
            for sort_order, task_proposal in enumerate(week_proposal.tasks, start=1):
                db.add(models.RoadmapTask(
                    roadmap_week_id=week.id,
                    gap_id=task_proposal.related_gap_id,
                    title=task_proposal.title,
                    objective=task_proposal.objective,
                    estimated_minutes=task_proposal.estimated_minutes,
                    completion_criteria=task_proposal.completion_criteria,
                    status=TaskStatus.TODO.value,
                    sort_order=sort_order,
                ))
        db.commit()
        db.refresh(roadmap)
        return _read(roadmap)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "四周计划保存失败") from exc


def update_roadmap_task(db: Session, task_id: UUID, payload: RoadmapTaskUpdate) -> RoadmapTaskRead:
    task = db.get(models.RoadmapTask, task_id)
    if task is None:
        raise _http(404, "Roadmap task not found")
    if task.week.roadmap.status != "VALID":
        raise _http(409, "This roadmap is no longer current")
    task.status = payload.status.value
    task.completed_at = datetime.now(timezone.utc) if payload.status == TaskStatus.DONE else None
    task.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(task)
        return RoadmapTaskRead(
            id=task.id,
            gap_id=task.gap_id,
            title=task.title,
            objective=task.objective,
            estimated_minutes=task.estimated_minutes,
            completion_criteria=task.completion_criteria,
            status=task.status,
            sort_order=task.sort_order,
            completed_at=task.completed_at,
        )
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Roadmap task could not be updated") from exc


def replan_roadmap(db: Session, profile_id: UUID, remaining_weeks: int, provider=None) -> RoadmapRead:
    current = get_roadmap(db, profile_id)
    context = {
        "remaining_weeks": remaining_weeks,
        "completed_tasks": [task.title for week in current.weeks for task in week.tasks if task.status == TaskStatus.DONE],
        "skipped_tasks": [task.title for week in current.weeks for task in week.tasks if task.status == TaskStatus.SKIPPED],
        "incomplete_tasks": [task.title for week in current.weeks for task in week.tasks if task.status in {TaskStatus.TODO, TaskStatus.IN_PROGRESS}],
    }
    return generate_roadmap(db, profile_id, provider=provider, remaining_context=context, force_new=True)
