"""Mission-scoped structured final resume, imported from approved rewrite choices."""
from __future__ import annotations

from collections import defaultdict
from datetime import datetime, timezone
from uuid import UUID, uuid4

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .mission_service import _effective_profile_for_mission


def _node(
    text: str | None,
    *,
    source_kind: str,
    source_id: UUID | None = None,
    evidence_refs: list[str] | None = None,
    risk_level: str = "LOW",
    claim_status: str = "CONFIRMED",
    node_id: UUID | None = None,
) -> dict:
    return {
        "id": str(node_id or uuid4()),
        "text": (text or "").strip(),
        "source_kind": source_kind,
        "source_id": str(source_id) if source_id else None,
        "evidence_refs": list(evidence_refs or []),
        "risk_level": risk_level,
        "claim_status": claim_status,
    }


def _entry(source_id: UUID, *, title: dict, subtitle: dict, date: dict, location: dict, bullets: list[dict]) -> dict:
    return {
        "id": str(source_id),
        "status": "INCLUDED",
        "title": title,
        "subtitle": subtitle,
        "date": date,
        "location": location,
        "bullets": bullets,
    }


def _section(kind: str, title: str, entries: list[dict]) -> dict:
    return {"id": str(uuid4()), "kind": kind, "title": _node(title, source_kind="system"), "entries": entries}


def _import_document(profile: models.UserProfile, resume: models.TargetResume, mission: models.JobMission) -> dict:
    basics = {
        "name": _node(profile.full_name, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "phone": _node(profile.phone, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "email": _node(profile.email, source_kind="profile", source_id=profile.id, risk_level="HIGH"),
        "location": _node(profile.city, source_kind="profile", source_id=profile.id),
    }
    education = [
        _entry(
            item.id,
            title=_node(item.institution, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            subtitle=_node(" · ".join(filter(None, [item.degree, item.field_of_study])), source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            date=_node(item.dates, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            location=_node("", source_kind="profile", source_id=item.id),
            bullets=[_node(course, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]) for course in item.relevant_courses or []],
        )
        for item in profile.education
    ]
    accepted = [bullet for bullet in resume.bullets if bullet.status in {"ACCEPTED", "EDITED"}]
    by_experience: dict[UUID, list[models.TargetResumeBullet]] = defaultdict(list)
    for bullet in accepted:
        if bullet.source_experience_id:
            by_experience[bullet.source_experience_id].append(bullet)
    order = {str(value): idx for idx, value in enumerate(resume.recommended_experience_order or [])}
    experiences = []
    omitted = {item.experience_id for item in mission.selections if item.decision == "OMIT"}
    for item in sorted(profile.experiences, key=lambda exp: (order.get(str(exp.id), 9999), str(exp.id))):
        if item.id in omitted or item.id not in by_experience:
            continue
        bullets = []
        for bullet in sorted(by_experience[item.id], key=lambda row: (row.sort_order, str(row.id))):
            flags = {str(flag).upper() for flag in bullet.risk_flags or []}
            needs_confirmation = "GROUNDING:NEEDS_CONFIRMATION" in flags or "SYNTHETIC_PROJECT" in flags
            bullets.append(_node(
                bullet.final_text or bullet.suggested_text,
                source_kind="target_bullet",
                source_id=bullet.id,
                node_id=bullet.id,
                evidence_refs=[str(ref) for ref in bullet.evidence_refs or []],
                risk_level="HIGH" if needs_confirmation else "LOW",
                claim_status="NEEDS_CONFIRMATION" if needs_confirmation and "FACT_CONFIRMED" not in flags else "CONFIRMED",
            ))
        experiences.append(_entry(
            item.id,
            title=_node(item.title, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            subtitle=_node(item.organization, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            date=_node(item.dates, source_kind="experience", source_id=item.id, evidence_refs=[str(item.id)], risk_level="HIGH"),
            location=_node("", source_kind="experience", source_id=item.id),
            bullets=bullets,
        ))
    skills = [
        _entry(
            item.id,
            title=_node(item.name, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]),
            subtitle=_node(item.proficiency, source_kind="profile", source_id=item.id),
            date=_node("", source_kind="system"),
            location=_node("", source_kind="system"),
            bullets=[],
        )
        for item in profile.skills
    ]
    certifications = [
        _entry(
            item.id,
            title=_node(item.name, source_kind="profile", source_id=item.id, evidence_refs=[str(item.id)]),
            subtitle=_node(item.issuer, source_kind="profile", source_id=item.id),
            date=_node(item.date, source_kind="profile", source_id=item.id, risk_level="HIGH"),
            location=_node("", source_kind="system"),
            bullets=[],
        )
        for item in profile.certifications
    ]
    return {"schema_version": 1, "basics": basics, "sections": [
        _section("education", "教育经历", education),
        _section("experience", "工作与项目经历", experiences),
        _section("skills", "技能", skills),
        _section("certifications", "证书", certifications),
    ]}


def get_or_create_document(db: Session, mission_id: UUID) -> models.ResumeStudioDocument:
    existing = db.scalar(select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id))
    if existing:
        return existing
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(404, "岗位任务不存在。")
    resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission_id, models.TargetResume.status == "CONFIRMED").order_by(models.TargetResume.version.desc()))
    if resume is None:
        raise HTTPException(409, "请先确认岗位定向简历。")
    profile = _effective_profile_for_mission(db, mission)
    row = models.ResumeStudioDocument(
        mission_id=mission.id,
        source_target_resume_id=resume.id,
        revision=1,
        language="zh",
        template_id="zh-classic",
        document_json=_import_document(profile, resume, mission),
        updated_at=datetime.now(timezone.utc),
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def read_document(row: models.ResumeStudioDocument) -> dict:
    return {
        "id": str(row.id),
        "mission_id": str(row.mission_id),
        "source_target_resume_id": str(row.source_target_resume_id),
        "schema_version": row.schema_version,
        "revision": row.revision,
        "confirmed_revision": row.confirmed_revision,
        "language": row.language,
        "template_id": row.template_id,
        "document": row.document_json,
    }
