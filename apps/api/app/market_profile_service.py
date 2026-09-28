from __future__ import annotations

from collections import OrderedDict
from datetime import datetime, timezone
import re
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .derived_state import derived_state_fingerprint
from .jd_analysis_provider import (
    JDAnalysisProviderConnectionError,
    JDAnalysisProviderInvalidResponseError,
    JDAnalysisProviderNotConfiguredError,
    JDAnalysisProviderTimeoutError,
    get_jd_analysis_provider,
)
from .jd_analysis_schemas import (
    JdExtraction,
    MarketCapabilityRead,
    MarketProfileRead,
    MarketRequirementEvidenceRead,
    MarketRequirementRead,
    RequirementCategory,
)
from .job_description_service import _load_current_target


_ALIASES = {
    "python programming": "Python",
    "python development": "Python",
    "python scripting": "Python",
    "sql querying": "SQL",
    "structured query language": "SQL",
    "large language model": "LLM",
    "large language models": "LLM",
    "llm application development": "LLM Application Development",
    "retrieval augmented generation": "RAG",
    "retrieval-augmented generation": "RAG",
    "prompt engineering": "Prompt Engineering",
    "machine learning": "Machine Learning",
    "data analysis": "Data Analysis",
    "product analytics": "Product Analytics",
    "a/b testing": "A/B Testing",
}


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def normalize_requirement(value: str, category: RequirementCategory) -> str | None:
    value = " ".join(value.split()).strip()
    if not value:
        return None
    alias = _ALIASES.get(value.casefold())
    if alias:
        return alias
    if category in {RequirementCategory.SKILL, RequirementCategory.DOMAIN}:
        return value[:1].upper() + value[1:]
    return value


def aggregate_requirements(extractions: list[JdExtraction], rows_by_id: dict[UUID, models.JobDescription]) -> list[dict]:
    extraction_ids = [extraction.jd_id for extraction in extractions]
    if len(extraction_ids) != len(set(extraction_ids)) or set(extraction_ids) != set(rows_by_id):
        raise ValueError("market analysis must return exactly one extraction for every supplied JD")
    grouped: OrderedDict[str, dict] = OrderedDict()
    for extraction in extractions:
        row = rows_by_id.get(extraction.jd_id)
        if row is None:
            raise ValueError("market analysis returned an unknown JD")
        for item in extraction.items:
            evidence = item.evidence_text.strip()
            if evidence.casefold() not in row.raw_text.casefold():
                raise ValueError("market analysis returned evidence that is not grounded in the source JD")
            name = normalize_requirement(item.name, item.category)
            if not name:
                continue
            key = name.casefold()
            current = grouped.setdefault(key, {"name": name, "category": item.category.value, "jd_ids": [], "evidence": []})
            if extraction.jd_id not in current["jd_ids"]:
                current["jd_ids"].append(extraction.jd_id)
            if not any(entry["job_description_id"] == extraction.jd_id and entry["evidence_text"] == evidence for entry in current["evidence"]):
                current["evidence"].append({
                    "job_description_id": extraction.jd_id,
                    "source_url": row.source_url,
                    "evidence_text": evidence,
                })
    return [value for value in grouped.values() if value["jd_ids"]]


_CAPABILITY_RULES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "Technical capability",
        (
            "ai",
            "llm",
            "language model",
            "machine learning",
            "python",
            "sql",
            "api",
            "prompt",
            "rag",
            "agent",
            "model",
            "evaluation",
            "programming",
            "coding",
        ),
    ),
    (
        "Product execution",
        (
            "product",
            "roadmap",
            "strategy",
            "discovery",
            "priorit",
            "requirement",
            "delivery",
            "launch",
            "backlog",
            "ownership",
        ),
    ),
    (
        "Research and decision-making",
        (
            "user",
            "customer",
            "market",
            "research",
            "analytics",
            "experiment",
            "metric",
            "business",
            "insight",
            "a/b",
            "statistics",
            "data",
        ),
    ),
    (
        "Cross-functional collaboration",
        (
            "stakeholder",
            "cross-functional",
            "collaboration",
            "communication",
            "team",
            "partner",
        ),
    ),
)


def _matches_capability_token(value: str, words: list[str], token: str) -> bool:
    normalized = " ".join(re.sub(r"[^a-z0-9]+", " ", token.casefold()).split())
    parts = normalized.split()
    if len(parts) > 1:
        return normalized in value
    if normalized.endswith("it"):
        return any(word.startswith(normalized) for word in words)
    return normalized in words


def capability_group(name: str, category: str) -> str:
    """Return a stable, evidence-derived bucket without inventing market facts."""

    value = re.sub(r"[^a-z0-9]+", " ", name.casefold()).strip()
    words = value.split()
    for label, tokens in _CAPABILITY_RULES:
        if any(_matches_capability_token(value, words, token) for token in tokens):
            return label
    return {
        RequirementCategory.RESPONSIBILITY.value: "Product execution",
        RequirementCategory.COLLABORATION.value: "Cross-functional collaboration",
        RequirementCategory.EXPERIENCE.value: "Relevant experience",
        RequirementCategory.EDUCATION.value: "Education baseline",
        RequirementCategory.DOMAIN.value: "Domain context",
    }.get(category, "Other role capability")


def synthesize_capabilities(requirements: list[MarketRequirementRead], sample_count: int) -> list[MarketCapabilityRead]:
    """Project normalized atomic requirements into grounded decision-level capabilities.

    The projection only combines existing atomic rows. Counts, source IDs, and evidence
    are unions calculated here; no provider output is trusted for those fields.
    """

    grouped: OrderedDict[str, list[MarketRequirementRead]] = OrderedDict()
    for requirement in requirements:
        grouped.setdefault(capability_group(requirement.name, requirement.category.value), []).append(requirement)

    capabilities: list[MarketCapabilityRead] = []
    denominator = max(sample_count, 1)
    for label, atomics in grouped.items():
        source_jd_ids: list[UUID] = []
        evidence: list[MarketRequirementEvidenceRead] = []
        for atomic in atomics:
            for jd_id in atomic.source_jd_ids:
                if jd_id not in source_jd_ids:
                    source_jd_ids.append(jd_id)
            for row in atomic.evidence:
                if not any(existing.job_description_id == row.job_description_id and existing.evidence_text == row.evidence_text for existing in evidence):
                    evidence.append(row)
        occurrence_count = len(source_jd_ids)
        names = ", ".join(atomic.name for atomic in atomics[:3])
        if len(atomics) > 3:
            names = f"{names} 等 {len(atomics)} 项要求"
        summary = f"由 {names} 综合，覆盖 {occurrence_count} / {sample_count} 条 JD。"
        capabilities.append(
            MarketCapabilityRead(
                id=atomics[0].id,
                name=label,
                summary=summary,
                occurrence_count=occurrence_count,
                frequency_ratio=occurrence_count / denominator,
                source_jd_ids=source_jd_ids,
                atomic_requirement_ids=[atomic.id for atomic in atomics],
                atomic_requirements=atomics,
                evidence=evidence,
            )
        )
    return capabilities


def market_requirement_read(requirement: models.MarketRequirement) -> MarketRequirementRead:
    evidence = [MarketRequirementEvidenceRead.model_validate(row) for row in requirement.evidence]
    return MarketRequirementRead(
        id=requirement.id,
        name=requirement.name,
        category=requirement.category,
        occurrence_count=requirement.occurrence_count,
        frequency_ratio=requirement.frequency_ratio,
        source_jd_ids=[row.job_description_id for row in evidence],
        evidence=evidence,
    )


def market_profile_capabilities(profile: models.MarketProfile) -> list[MarketCapabilityRead]:
    requirements = [
        market_requirement_read(requirement)
        for requirement in sorted(profile.requirements, key=lambda row: row.sort_order)
    ]
    return synthesize_capabilities(requirements, profile.sample_count)


def _read(profile: models.MarketProfile) -> MarketProfileRead:
    requirements: list[MarketRequirementRead] = []
    for requirement in sorted(profile.requirements, key=lambda row: row.sort_order):
        evidence = [MarketRequirementEvidenceRead.model_validate(row) for row in requirement.evidence]
        requirements.append(
            MarketRequirementRead(
                id=requirement.id,
                name=requirement.name,
                category=requirement.category,
                occurrence_count=requirement.occurrence_count,
                frequency_ratio=requirement.frequency_ratio,
                source_jd_ids=[row.job_description_id for row in evidence],
                evidence=evidence,
            )
        )
    return MarketProfileRead(
        id=profile.id,
        target_role_id=profile.target_role_id,
        sample_count=profile.sample_count,
        sample_fingerprint=profile.sample_fingerprint,
        status=profile.status,
        generated_at=profile.generated_at,
        updated_at=profile.updated_at,
        requirements=requirements,
        capabilities=synthesize_capabilities(requirements, profile.sample_count),
    )


def _provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, JDAnalysisProviderNotConfiguredError):
        return _http(503, "市场分析服务尚未配置")
    if isinstance(exc, JDAnalysisProviderTimeoutError):
        return _http(504, "市场分析暂时超时，请重试")
    if isinstance(exc, (JDAnalysisProviderConnectionError, JDAnalysisProviderInvalidResponseError)):
        return _http(502, "市场分析暂时失败，请重试")
    return _http(502, "市场分析暂时失败，请重试")


def _load_context(
    db: Session,
    target_role_id: UUID,
    *,
    for_update: bool = False,
) -> tuple[models.TargetRole, list[models.JobDescription], str]:
    target = _load_current_target(db, target_role_id, for_update=for_update)
    rows = db.scalars(
        select(models.JobDescription).where(models.JobDescription.target_role_id == target_role_id).order_by(models.JobDescription.created_at, models.JobDescription.id)
    ).all()
    if len(rows) < 3:
        raise _http(409, "至少需要 3 条 JD 才能生成市场画像")
    return target, list(rows), derived_state_fingerprint(target_role_id, rows)


def get_market_profile(db: Session, target_role_id: UUID) -> MarketProfileRead:
    _target, rows, fingerprint = _load_context(db, target_role_id)
    profile = db.scalar(select(models.MarketProfile).where(models.MarketProfile.target_role_id == target_role_id))
    if profile is None:
        raise _http(404, "市场画像尚未生成")
    if profile.status != "VALID" or profile.sample_fingerprint != fingerprint:
        raise _http(409, "市场画像已过期，请重新分析")
    return _read(profile)


def generate_market_profile(db: Session, target_role_id: UUID, provider=None) -> MarketProfileRead:
    # Serialize generation per current target in PostgreSQL so two tabs cannot
    # invoke the expensive provider before either one persists the profile.
    target, rows, fingerprint = _load_context(db, target_role_id, for_update=True)
    existing = db.scalar(select(models.MarketProfile).where(models.MarketProfile.target_role_id == target_role_id))
    if existing is not None and existing.status == "VALID" and existing.sample_fingerprint == fingerprint:
        return _read(existing)
    provider = provider or get_jd_analysis_provider()
    try:
        extraction = provider.analyze(
            target_role=target.role_code,
            job_descriptions=[{"id": str(row.id), "raw_text": row.raw_text, "source_url": row.source_url} for row in rows],
        )
    except Exception as exc:
        raise _provider_error(exc) from exc
    rows_by_id = {row.id: row for row in rows}
    try:
        aggregated = aggregate_requirements(extraction.items, rows_by_id)
    except ValueError as exc:
        raise _http(502, "市场分析返回无法核验的证据，请重试") from exc
    if not aggregated:
        raise _http(502, "市场分析未返回可核验的岗位要求，请重试")
    now = datetime.now(timezone.utc)
    try:
        if existing is None:
            existing = models.MarketProfile(
                target_role_id=target_role_id,
                sample_fingerprint=fingerprint,
                sample_count=len(rows),
                status="VALID",
            )
            db.add(existing)
            db.flush()
        else:
            for requirement in list(existing.requirements):
                db.delete(requirement)
            db.flush()
            existing.sample_fingerprint = fingerprint
            existing.sample_count = len(rows)
            existing.status = "VALID"
            existing.invalidated_at = None
            existing.generated_at = now
            existing.updated_at = now
        for index, item in enumerate(aggregated, start=1):
            requirement = models.MarketRequirement(
                market_profile_id=existing.id,
                name=item["name"],
                category=item["category"],
                occurrence_count=len(item["jd_ids"]),
                frequency_ratio=len(item["jd_ids"]) / len(rows),
                sort_order=index,
            )
            db.add(requirement)
            db.flush()
            for evidence in item["evidence"]:
                db.add(models.MarketRequirementEvidence(requirement_id=requirement.id, **evidence))
        db.commit()
        db.refresh(existing)
        return _read(existing)
    except HTTPException:
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "市场画像保存失败") from exc


def get_requirement_evidence(db: Session, requirement_id: UUID) -> list[MarketRequirementEvidenceRead]:
    requirement = db.scalar(select(models.MarketRequirement).where(models.MarketRequirement.id == requirement_id))
    if requirement is None:
        raise _http(404, "市场要求不存在")
    profile = requirement.market_profile
    _target, rows, fingerprint = _load_context(db, profile.target_role_id)
    if profile.status != "VALID" or profile.sample_fingerprint != fingerprint:
        raise _http(409, "市场画像已过期，请重新分析")
    return [MarketRequirementEvidenceRead.model_validate(row) for row in requirement.evidence]
