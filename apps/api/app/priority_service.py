from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .derived_state import priority_fingerprint
from .gap_service import _current_context
from .market_profile_service import market_profile_capabilities
from .priority_schemas import PriorityLane, PriorityListRead, PriorityRead, PriorityUpdate


_WEIGHTS = {"LOW": 0.33, "MEDIUM": 0.66, "HIGH": 1.0}


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _score(gap: models.Gap, preference_relevance: float, frequency_ratio: float) -> float:
    return (
        frequency_ratio * 40
        + _WEIGHTS.get(gap.severity, 0.66) * 25
        + preference_relevance * 15
        + _WEIGHTS.get(gap.proximity, 0.66) * 10
        + _WEIGHTS.get(gap.feasibility, 0.66) * 10
    )


def rank_gaps(gaps: list[models.Gap], preferences: models.CareerPreference | None) -> list[tuple[models.Gap, float, str]]:
    preference_relevance = 1.0 if preferences and "CURRENT_FIT" in preferences.priority_order else 0.66
    profile = gaps[0].market_requirement.market_profile if gaps else None
    capabilities = {capability.id: capability for capability in market_profile_capabilities(profile)} if profile else {}
    ranked = []
    for gap in gaps:
        capability = capabilities.get(gap.market_requirement.id)
        frequency_ratio = capability.frequency_ratio if capability else gap.market_requirement.frequency_ratio
        name = capability.name if capability else gap.market_requirement.name
        source_count = capability.occurrence_count if capability else gap.market_requirement.occurrence_count
        score = _score(gap, preference_relevance, frequency_ratio)
        reason = (
            f"{name} appears in {source_count} JDs; "
            f"state={gap.state}, severity={gap.severity}, proximity={gap.proximity}, feasibility={gap.feasibility}."
        )
        ranked.append((gap, score, reason))
    return sorted(
        ranked,
        key=lambda item: (
            -item[1],
            -capabilities.get(item[0].market_requirement.id).frequency_ratio
            if item[0].market_requirement.id in capabilities
            else -item[0].market_requirement.frequency_ratio,
            item[0].market_requirement.name.casefold(),
        ),
    )


def _ensure_priorities(db: Session, analysis: models.GapAnalysis, preferences: models.CareerPreference | None) -> list[models.GapPriority]:
    existing = list(analysis.priorities)
    if len(existing) == len(analysis.gaps) and {row.gap_id for row in existing} == {gap.id for gap in analysis.gaps}:
        return existing
    for row in existing:
        db.delete(row)
    db.flush()
    priorities = []
    for rank, (gap, _score_value, reason) in enumerate(rank_gaps(list(analysis.gaps), preferences), start=1):
        lane = PriorityLane.NOW.value if rank <= 3 else PriorityLane.NEXT.value if rank <= 7 else PriorityLane.NOT_NOW.value
        priority = models.GapPriority(
            gap_analysis_id=analysis.id,
            gap_id=gap.id,
            system_rank=rank,
            user_rank=None,
            lane=lane,
            system_reason=reason,
            updated_at=datetime.now(timezone.utc),
        )
        db.add(priority)
        priorities.append(priority)
    db.flush()
    return priorities


def _load_analysis(db: Session, profile_id: UUID) -> models.GapAnalysis:
    _profile, market, fingerprint = _current_context(db, profile_id)
    analysis = db.scalar(select(models.GapAnalysis).where(models.GapAnalysis.market_profile_id == market.id))
    if analysis is None:
        raise _http(409, "请先生成差距分析")
    if analysis.status != "VALID" or analysis.profile_fingerprint != fingerprint:
        raise _http(409, "差距分析已过期，请重新分析")
    capability_ids = {capability.id for capability in market_profile_capabilities(market)}
    if {gap.market_requirement_id for gap in analysis.gaps} != capability_ids:
        raise _http(409, "差距分析需要按能力维度重新生成")
    return analysis


def _read(analysis: models.GapAnalysis, priorities: list[models.GapPriority]) -> PriorityListRead:
    by_gap = {row.gap_id: row for row in priorities}
    capabilities = {capability.id: capability for capability in market_profile_capabilities(analysis.market_profile)}
    ordered = sorted(priorities, key=lambda row: (row.user_rank is None, row.user_rank if row.user_rank is not None else row.system_rank))
    items = []
    for effective_rank, priority in enumerate(ordered, start=1):
        gap = next(gap for gap in analysis.gaps if gap.id == priority.gap_id)
        capability = capabilities.get(gap.market_requirement.id)
        items.append(PriorityRead(
            gap_id=gap.id,
            requirement_name=capability.name if capability else gap.market_requirement.name,
            state=gap.state,
            severity=gap.severity,
            proximity=gap.proximity,
            feasibility=gap.feasibility,
            frequency_ratio=capability.frequency_ratio if capability else gap.market_requirement.frequency_ratio,
            system_rank=priority.system_rank,
            user_rank=priority.user_rank,
            effective_rank=effective_rank,
            lane=priority.lane,
            system_reason=priority.system_reason,
        ))
    return PriorityListRead(gap_analysis_id=analysis.id, overridden=any(row.user_rank is not None for row in by_gap.values()), items=items)


def get_priorities(db: Session, profile_id: UUID) -> PriorityListRead:
    analysis = _load_analysis(db, profile_id)
    profile = db.get(models.UserProfile, profile_id)
    priorities = _ensure_priorities(db, analysis, profile.career_preference if profile else None)
    db.commit()
    return _read(analysis, priorities)


def update_priorities(db: Session, profile_id: UUID, payload: PriorityUpdate) -> PriorityListRead:
    analysis = _load_analysis(db, profile_id)
    profile = db.get(models.UserProfile, profile_id)
    priorities = _ensure_priorities(db, analysis, profile.career_preference if profile else None)
    expected = {row.gap_id for row in priorities}
    if set(payload.order) != expected:
        raise _http(422, "order must contain every current gap exactly once")
    positions = {gap_id: index for index, gap_id in enumerate(payload.order, start=1)}
    for priority in priorities:
        priority.user_rank = positions[priority.gap_id]
        priority.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Priority ordering could not be saved") from exc
    return _read(analysis, priorities)


def current_priority_fingerprint(db: Session, profile_id: UUID) -> str:
    analysis = _load_analysis(db, profile_id)
    profile = db.get(models.UserProfile, profile_id)
    priorities = _ensure_priorities(db, analysis, profile.career_preference if profile else None)
    db.commit()
    return priority_fingerprint(priorities)
