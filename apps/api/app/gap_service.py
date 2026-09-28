from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .derived_state import derived_state_fingerprint, profile_fingerprint
from .gap_provider import (
    GapProviderConnectionError,
    GapProviderInvalidResponseError,
    GapProviderNotConfiguredError,
    GapProviderTimeoutError,
    get_gap_analysis_provider,
)
from .gap_schemas import GapAnalysisRead, GapRead, GapState
from .market_profile_service import market_profile_capabilities


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _read(analysis: models.GapAnalysis) -> GapAnalysisRead:
    capabilities = {capability.id: capability for capability in market_profile_capabilities(analysis.market_profile)}
    gaps = []
    for gap in sorted(analysis.gaps, key=lambda row: row.sort_order):
        requirement = gap.market_requirement
        capability = capabilities.get(requirement.id)
        if capability is None:
            continue
        gaps.append(
            GapRead(
                id=gap.id,
                requirement_id=requirement.id,
                capability_id=capability.id,
                requirement_name=capability.name,
                capability_name=capability.name,
                capability_summary=capability.summary,
                category="CAPABILITY",
                occurrence_count=capability.occurrence_count,
                frequency_ratio=capability.frequency_ratio,
                source_jd_ids=capability.source_jd_ids,
                atomic_requirement_ids=capability.atomic_requirement_ids,
                atomic_requirement_names=[item.name for item in capability.atomic_requirements],
                market_evidence=capability.evidence,
                state=gap.state,
                severity=gap.severity,
                proximity=gap.proximity,
                feasibility=gap.feasibility,
                rationale=gap.rationale,
                evidence_refs=list(gap.evidence_refs or []),
                sort_order=gap.sort_order,
            )
        )
    return GapAnalysisRead(
        id=analysis.id,
        profile_id=analysis.profile_id,
        market_profile_id=analysis.market_profile_id,
        profile_fingerprint=analysis.profile_fingerprint,
        status=analysis.status,
        generated_at=analysis.generated_at,
        updated_at=analysis.updated_at,
        gaps=gaps,
    )


def _current_context(db: Session, profile_id: UUID) -> tuple[models.UserProfile, models.MarketProfile, str]:
    profile = db.scalar(select(models.UserProfile).where(models.UserProfile.id == profile_id))
    if profile is None:
        raise _http(404, "Profile not found")
    if profile.status != "CONFIRMED":
        raise _http(409, "Gap analysis requires a confirmed profile")
    target = db.scalar(select(models.TargetRole).where(models.TargetRole.profile_id == profile_id))
    if target is None:
        raise _http(409, "A current target role is required before gap analysis")
    jds = db.scalars(select(models.JobDescription).where(models.JobDescription.target_role_id == target.id)).all()
    if len(jds) < 3:
        raise _http(409, "至少需要 3 条 JD 才能生成市场画像")
    market = db.scalar(select(models.MarketProfile).where(models.MarketProfile.target_role_id == target.id))
    if market is None:
        raise _http(409, "请先生成市场画像")
    fingerprint = derived_state_fingerprint(target.id, jds)
    if market.status != "VALID" or market.sample_fingerprint != fingerprint:
        raise _http(409, "市场画像已过期，请重新分析")
    return profile, market, profile_fingerprint(profile)


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, GapProviderNotConfiguredError):
        return _http(503, "差距分析服务尚未配置")
    if isinstance(exc, GapProviderTimeoutError):
        return _http(504, "差距分析暂时超时，请重试")
    if isinstance(exc, (GapProviderConnectionError, GapProviderInvalidResponseError)):
        return _http(502, "差距分析暂时失败，请重试")
    return _http(502, "差距分析暂时失败，请重试")


def _is_capability_analysis(analysis: models.GapAnalysis, market: models.MarketProfile) -> bool:
    capability_ids = {capability.id for capability in market_profile_capabilities(market)}
    return bool(capability_ids) and {gap.market_requirement_id for gap in analysis.gaps} == capability_ids


def get_gap_analysis(db: Session, profile_id: UUID) -> GapAnalysisRead:
    _profile, market, fingerprint = _current_context(db, profile_id)
    analysis = db.scalar(select(models.GapAnalysis).where(models.GapAnalysis.market_profile_id == market.id))
    if analysis is None:
        raise _http(404, "差距分析尚未生成")
    if analysis.status != "VALID" or analysis.profile_fingerprint != fingerprint:
        raise _http(409, "差距分析已过期，请重新分析")
    if not _is_capability_analysis(analysis, market):
        raise _http(409, "差距分析需要按能力维度重新生成")
    return _read(analysis)


def create_gap_analysis(db: Session, profile_id: UUID, provider=None) -> GapAnalysisRead:
    profile, market, fingerprint = _current_context(db, profile_id)
    existing = db.scalar(select(models.GapAnalysis).where(models.GapAnalysis.market_profile_id == market.id))
    if existing is not None and existing.status == "VALID" and existing.profile_fingerprint == fingerprint and _is_capability_analysis(existing, market):
        return _read(existing)
    profile_facts = []
    for collection, kind, fields in (
        (profile.education, "education", ("institution", "degree", "field_of_study")),
        (profile.skills, "skill", ("name", "proficiency")),
        (profile.experiences, "experience", ("title", "organization", "description")),
        (profile.certifications, "certification", ("name", "issuer", "date")),
    ):
        for row in collection:
            value = " | ".join(str(getattr(row, field)) for field in fields if getattr(row, field, None))
            if value.strip():
                profile_facts.append({"id": str(row.id), "kind": kind, "value": value})
    capabilities = market_profile_capabilities(market)
    requirements = [
        {
            "id": str(capability.id),
            "name": capability.name,
            "summary": capability.summary,
            "frequency_ratio": capability.frequency_ratio,
            "source_jd_count": capability.occurrence_count,
            "source_jd_ids": [str(value) for value in capability.source_jd_ids],
            "atomic_requirement_ids": [str(value) for value in capability.atomic_requirement_ids],
            "atomic_requirements": [
                {"id": str(item.id), "name": item.name, "category": item.category, "frequency_ratio": item.frequency_ratio}
                for item in capability.atomic_requirements
            ],
        }
        for capability in capabilities
    ]
    if not capabilities:
        raise _http(502, "市场画像没有可分析的要求")
    market_id = market.id
    market_sample_fingerprint = market.sample_fingerprint
    # The context above is read-only. End that transaction before the network
    # call so a slow provider does not keep a pooled PostgreSQL connection in
    # an idle transaction while another request is waiting to persist.
    db.rollback()
    provider = provider or get_gap_analysis_provider()
    try:
        proposals = provider.compare(requirements=requirements, profile_facts=profile_facts)
    except Exception as exc:
        raise _provider_error(exc) from exc
    known_capabilities = {capability.id: capability for capability in capabilities}
    atomic_to_capability = {
        atomic_id: capability
        for capability in capabilities
        for atomic_id in capability.atomic_requirement_ids
    }
    known_facts = {UUID(fact["id"]) for fact in profile_facts}
    proposals_by_capability = {}
    for proposal in proposals.items:
        capability = known_capabilities.get(proposal.requirement_id) or atomic_to_capability.get(proposal.requirement_id)
        if capability is not None:
            proposals_by_capability[capability.id] = proposal
    try:
        # Provider calls can be slow or unavailable. Do not hold a PostgreSQL
        # row lock while waiting on the network; a concurrent request should
        # wait only for the short persistence section below. Re-read the
        # current state after taking the lock so an upstream change or a
        # completed concurrent generation cannot be overwritten.
        locked_market = db.scalar(
            select(models.MarketProfile)
            .where(models.MarketProfile.id == market_id)
            .with_for_update()
        )
        if locked_market is None:
            raise _http(409, "市场画像已不存在，请重新分析")
        current_profile, current_market, current_fingerprint = _current_context(db, profile_id)
        if (
            current_market.id != market_id
            or current_market.sample_fingerprint != market_sample_fingerprint
            or current_fingerprint != fingerprint
        ):
            raise _http(409, "上游资料已变化，请重新分析")
        profile = current_profile
        market = locked_market
        existing = db.scalar(select(models.GapAnalysis).where(models.GapAnalysis.market_profile_id == market.id))
        if existing is not None and existing.status == "VALID" and existing.profile_fingerprint == current_fingerprint and _is_capability_analysis(existing, market):
            return _read(existing)
        now = datetime.now(timezone.utc)
        if existing is None:
            existing = models.GapAnalysis(
                profile_id=profile_id,
                market_profile_id=market.id,
                profile_fingerprint=current_fingerprint,
                status="VALID",
            )
            db.add(existing)
            db.flush()
        else:
            for gap in list(existing.gaps):
                db.delete(gap)
            existing.profile_fingerprint = current_fingerprint
            existing.status = "VALID"
            existing.invalidated_at = None
            existing.generated_at = now
            existing.updated_at = now
            db.flush()
        for sort_order, capability in enumerate(capabilities, start=1):
            proposal = proposals_by_capability.get(capability.id)
            evidence_refs = [ref for ref in (proposal.evidence_refs if proposal else []) if ref in known_facts]
            state = proposal.state.value if proposal else GapState.UNCERTAIN.value
            rationale = proposal.rationale if proposal else "系统无法从已确认 Profile 安全判断，需用户补充证据。"
            db.add(
                models.Gap(
                    gap_analysis_id=existing.id,
                    market_requirement_id=capability.id,
                    state=state,
                    severity=proposal.severity if proposal else "MEDIUM",
                    proximity=proposal.proximity if proposal else "MEDIUM",
                    feasibility=proposal.feasibility if proposal else "MEDIUM",
                    rationale=rationale,
                    evidence_refs=[str(ref) for ref in evidence_refs],
                    sort_order=sort_order,
                )
            )
        db.commit()
        db.refresh(existing)
        return _read(existing)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "差距分析保存失败") from exc
