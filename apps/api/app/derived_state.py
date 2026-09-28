from __future__ import annotations

import hashlib
import json
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def derived_state_fingerprint(target_role_id: UUID, job_descriptions: Iterable[object]) -> str:
    samples = []
    for row in job_descriptions:
        samples.append(
            {
                "id": str(getattr(row, "id", "")),
                "content_hash": str(getattr(row, "content_hash", "")),
            }
        )
    payload = {"target_role_id": str(target_role_id), "job_descriptions": sorted(samples, key=lambda item: item["id"])}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def profile_fingerprint(profile: models.UserProfile) -> str:
    payload = {
        "profile_id": str(profile.id),
        "status": profile.status,
        "education": [
            {"institution": row.institution, "degree": row.degree, "field": row.field_of_study}
            for row in profile.education
        ],
        "skills": [
            {"name": row.name, "proficiency": row.proficiency}
            for row in profile.skills
        ],
        "experiences": [
            {"title": row.title, "organization": row.organization, "description": row.description}
            for row in profile.experiences
        ],
        "certifications": [{"name": row.name, "issuer": row.issuer} for row in profile.certifications],
    }
    return hashlib.sha256(json.dumps(payload, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode("utf-8")).hexdigest()


def priority_fingerprint(priorities: Iterable[models.GapPriority]) -> str:
    values = [
        {
            "gap_id": str(row.gap_id),
            "system_rank": row.system_rank,
            "user_rank": row.user_rank,
            "lane": row.lane,
        }
        for row in priorities
    ]
    return hashlib.sha256(json.dumps(sorted(values, key=lambda item: item["gap_id"]), sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def invalidate_target_derived_state(db: Session, target_role_id: UUID) -> None:
    """Invalidate current derived records while preserving roadmap task history."""
    now = _utcnow()
    try:
        market = db.scalar(select(models.MarketProfile).where(models.MarketProfile.target_role_id == target_role_id))
        if market is None:
            return
        market.status = "INVALIDATED"
        market.invalidated_at = now
        if market.gap_analysis is not None:
            market.gap_analysis.status = "INVALIDATED"
            market.gap_analysis.invalidated_at = now
            for roadmap in market.gap_analysis.roadmaps:
                roadmap.status = "INVALIDATED"
                roadmap.invalidated_at = now
    except SQLAlchemyError:
        db.rollback()
        raise


def invalidate_profile_derived_state(db: Session, profile_id: UUID) -> None:
    now = _utcnow()
    analyses = db.scalars(select(models.GapAnalysis).where(models.GapAnalysis.profile_id == profile_id)).all()
    for analysis in analyses:
        analysis.status = "INVALIDATED"
        analysis.invalidated_at = now
        for roadmap in analysis.roadmaps:
            roadmap.status = "INVALIDATED"
            roadmap.invalidated_at = now
