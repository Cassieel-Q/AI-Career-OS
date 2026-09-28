"""Seed one synthetic, repeatable v0.2 Job Mission for local dogfood.

The script only inserts rows with a visible ``[DOGFOOD]`` marker and refuses to
reuse a profile that contains non-dogfood target jobs. It does not create or
alter schema; run Alembic before using it.
"""

from __future__ import annotations

import hashlib
import os
from pathlib import Path
from uuid import UUID

from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker

from app import models
from app.interview_intelligence import InterviewIntelRetriever
from app.knowledge_packs import load_default_registry, sync_knowledge_packs


MARKER = "[DOGFOOD]"
JD_TEXT = (
    f"{MARKER} Baidu AI Product Manager Intern\n"
    "Own AI feature discovery, define product metrics, partner with engineering, "
    "and evaluate model quality with reproducible experiments."
)


def _database_url() -> str:
    value = os.getenv("DATABASE_URL", "").strip()
    if not value:
        raise SystemExit("DATABASE_URL is required; no rows were changed")
    return value


def _hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _session() -> Session:
    engine = create_engine(_database_url(), pool_pre_ping=True)
    return sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)()


def _existing(session: Session) -> tuple[models.UserProfile | None, models.TargetJob | None]:
    job = session.scalar(select(models.TargetJob).where(models.TargetJob.raw_text == JD_TEXT))
    return (job.profile if job else None), job


def seed() -> tuple[UUID, UUID]:
    registry = load_default_registry()
    if registry.errors:
        raise SystemExit(f"knowledge pack validation failed: {len(registry.errors)} files")
    sync = sync_knowledge_packs()
    session = _session()
    try:
        profile, job = _existing(session)
        if job is not None and profile is not None:
            mission = session.scalar(select(models.JobMission).where(models.JobMission.target_job_id == job.id))
            if mission is None:
                raise SystemExit("dogfood target job exists without a mission; run reset first")
            print(f"DOGFOOD_ALREADY_SEEDED profile_id={profile.id} mission_id={mission.id} packs={sync['pack_count']}")
            return profile.id, mission.id

        profile = models.UserProfile(status="CONFIRMED")
        profile.education.append(models.Education(
            institution=f"{MARKER} Synthetic University",
            degree="BSc",
            field_of_study="Information Systems",
            evidence_text=f"{MARKER} synthetic education",
            source_type="USER_ENTERED",
        ))
        profile.skills.extend([
            models.ProfileSkill(name="Product analytics", proficiency="PROJECT_READY", evidence_text=f"{MARKER} metric design", source_type="USER_ENTERED"),
            models.ProfileSkill(name="LLM evaluation", proficiency="PROJECT_READY", evidence_text=f"{MARKER} evaluation workflow", source_type="USER_ENTERED"),
        ])
        profile.experiences.extend([
            models.Experience(
                title=f"{MARKER} AI Career OS evaluation",
                organization="Synthetic project",
                dates="2026",
                description="Designed a labeled evaluation workflow, compared false matches, and documented rubric decisions.",
                experience_type="PROJECT",
                evidence_text=f"{MARKER} Designed a labeled evaluation workflow and documented rubric decisions.",
                source_type="USER_ENTERED",
            ),
            models.Experience(
                title=f"{MARKER} product discovery study",
                organization="Synthetic project",
                dates="2025",
                description="Interviewed users, synthesized needs, and prioritized a small product experiment.",
                experience_type="PROJECT",
                evidence_text=f"{MARKER} Interviewed users and prioritized a product experiment.",
                source_type="USER_ENTERED",
            ),
            models.Experience(
                title=f"{MARKER} operations support",
                organization="Synthetic student organization",
                dates="2024",
                description="Maintained an operations checklist and coordinated weekly tasks.",
                experience_type="OTHER",
                evidence_text=f"{MARKER} Maintained an operations checklist.",
                source_type="USER_ENTERED",
            ),
        ])
        session.add(profile)
        session.flush()

        job = models.TargetJob(
            profile_id=profile.id,
            raw_text=JD_TEXT,
            source_url="https://example.test/dogfood/baidu-ai-pm",
            content_hash=_hash(JD_TEXT),
            status="CURRENT",
            requirements=[
                {"id": "dogfood-req-1", "text": "Define product metrics", "category": "PRODUCT_METRICS"},
                {"id": "dogfood-req-2", "text": "Evaluate model quality", "category": "LLM_EVALUATION"},
                {"id": "dogfood-req-3", "text": "Partner with engineering", "category": "CROSS_FUNCTIONAL"},
            ],
            capabilities=["PRODUCT_METRICS", "LLM_EVALUATION", "CROSS_FUNCTIONAL"],
        )
        session.add(job)
        session.flush()

        intel = InterviewIntelRetriever(registry).retrieve(
            company="Baidu", role="AI Product Manager", role_family="AI_PRODUCT",
            competencies=["PRODUCT_METRICS", "LLM_EVALUATION"], limit=6,
        )
        mission = models.JobMission(
            profile_id=profile.id,
            target_job_id=job.id,
            display_name="DOGFOOD · Baidu · AI Product Manager Intern",
            company="Baidu",
            role="AI Product Manager Intern",
            role_family="AI_PRODUCT",
            seniority="INTERN",
            location="Synthetic / remote",
            status="DRAFT",
            parsed_jd={
                "company": "Baidu", "role": "AI Product Manager Intern", "role_family": "AI_PRODUCT",
                "seniority": "INTERN", "location": "Synthetic / remote",
                "responsibilities": ["Define product metrics", "Partner with engineering", "Evaluate model quality"],
                "requirements": job.requirements, "preferred_requirements": [],
                "capabilities": job.capabilities, "keywords": ["AI", "metrics", "evaluation"],
            },
            what_matters={
                "core_capabilities": ["Product metrics", "LLM evaluation", "Cross-functional delivery"],
                "high_importance_requirements": job.requirements,
                "evidence_expected": ["metric definition", "evaluation rubric", "engineering trade-off"],
                "likely_success_signals": ["clear ownership", "explicit decision criteria"],
                "bonus_capabilities": ["experimentation"],
                "potential_interview_focus": ["metric diagnosis", "model quality trade-offs"],
                "confidence": 0.82,
                "jd_evidence_refs": ["dogfood-req-1", "dogfood-req-2", "dogfood-req-3"],
            },
            interview_intel=[{
                "skill_id": item.skill_id,
                "name": item.name,
                "company_relevance": item.company_relevance,
                "role_relevance": item.role_relevance,
                "competency": item.competency,
                "source_count": item.source_count,
                "recency": item.recency,
                "confidence": item.confidence,
                "source_refs": item.source_refs,
                "observed_label": item.observed_label,
            } for item in intel],
        )
        session.add(mission)
        session.commit()
        print(f"DOGFOOD_SEEDED profile_id={profile.id} mission_id={mission.id} packs={sync['pack_count']}")
        return profile.id, mission.id
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


if __name__ == "__main__":
    seed()
