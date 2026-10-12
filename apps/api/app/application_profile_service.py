"""ResumeProfile / ApplicationProfile 边界（目标四）。

- ResumeProfile：可用于简历的内容（UserProfile + education/skills/experiences/certifications）。
- ApplicationProfile：网申字段（身份证、家庭、健康、档案、紧急联系人、到岗信息）。

读取矩阵：
| 场景 | ResumeProfile | ApplicationProfile |
|---|---|---|
| 简历生成 | ✅ 唯一来源 | ❌ |
| 网申填表 | ✅ | ✅ |
| 助手默认 | ✅（非敏感） | ❌ |
"""
from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models

# 网申专属敏感字段：简历生成与助手默认都不可读。
SENSITIVE_FIELDS = (
    "id_number",
    "family_info",
    "health_status",
    "archive_location",
    "emergency_contact",
    "emergency_phone",
    "availability",
)

_WRITABLE_FIELDS = SENSITIVE_FIELDS


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


def get_application_profile(db: Session, profile_id: UUID) -> models.ApplicationProfile | None:
    _profile(db, profile_id)
    return db.scalar(
        select(models.ApplicationProfile).where(models.ApplicationProfile.profile_id == profile_id)
    )


def upsert_application_profile(db: Session, profile_id: UUID, payload: dict) -> models.ApplicationProfile:
    _profile(db, profile_id)
    row = get_application_profile(db, profile_id)
    if row is None:
        row = models.ApplicationProfile(profile_id=profile_id)
        db.add(row)
    for field in _WRITABLE_FIELDS:
        if field in payload:
            value = payload.get(field)
            value = value.strip() if isinstance(value, str) else value
            setattr(row, field, value or None)
    db.commit()
    db.refresh(row)
    return row


def application_profile_read(row: models.ApplicationProfile | None) -> dict:
    data = {field: None for field in _WRITABLE_FIELDS}
    if row is not None:
        for field in _WRITABLE_FIELDS:
            data[field] = getattr(row, field, None)
    return data


def _resume_profile_facts(db: Session, profile_id: UUID) -> dict:
    """按 id 排序的简历可用事实（含 CET 分数）。只读 ResumeProfile 相关表。"""
    profile = _profile(db, profile_id)
    education = list(
        db.scalars(
            select(models.Education)
            .where(models.Education.profile_id == profile_id)
            .order_by(models.Education.id)
        ).all()
    )
    skills = list(
        db.scalars(select(models.ProfileSkill).where(models.ProfileSkill.profile_id == profile_id)).all()
    )
    experiences = list(
        db.scalars(select(models.Experience).where(models.Experience.profile_id == profile_id)).all()
    )
    certifications = list(
        db.scalars(select(models.Certification).where(models.Certification.profile_id == profile_id)).all()
    )
    return {
        "full_name": profile.full_name,
        "phone": profile.phone,
        "email": profile.email,
        "city": profile.city,
        "education": [
            {
                "institution": item.institution,
                "degree": item.degree,
                "field_of_study": item.field_of_study,
                "dates": item.dates,
                "cet4_score": item.cet4_score,
                "cet6_score": item.cet6_score,
                "relevant_courses": list(item.relevant_courses or []),
                "honors": list(item.honors or []),
            }
            for item in education
        ],
        "skills": [{"name": item.name, "proficiency": item.proficiency} for item in skills],
        "experiences": [
            {
                "title": item.title,
                "organization": item.organization,
                "dates": item.dates,
                "description": item.description,
                "experience_type": item.experience_type,
            }
            for item in experiences
        ],
        "certifications": [
            {"name": item.name, "issuer": item.issuer, "date": item.date, "score": item.score, "status": item.status}
            for item in certifications
        ],
    }


def resume_visible_facts(db: Session, profile_id: UUID) -> dict:
    """简历生成唯一可读的事实集合；**不含**任何 ApplicationProfile 字段。"""
    return _resume_profile_facts(db, profile_id)


def application_fill_facts(db: Session, profile_id: UUID) -> dict:
    """网申填表可读：ResumeProfile + ApplicationProfile。"""
    data = _resume_profile_facts(db, profile_id)
    row = get_application_profile(db, profile_id)
    data["application"] = application_profile_read(row)
    return data


def assert_resume_payload_has_no_sensitive_fields(payload: object) -> None:
    """边界守卫：简历生成载荷里不得出现网申敏感字段（供导出前自检/单测调用）。"""
    import json

    try:
        blob = json.dumps(payload, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        blob = str(payload)
    for field in SENSITIVE_FIELDS:
        if f'"{field}"' in blob:
            raise ValueError(f"简历载荷包含网申敏感字段：{field}")


__all__ = [
    "SENSITIVE_FIELDS",
    "get_application_profile",
    "upsert_application_profile",
    "application_profile_read",
    "resume_visible_facts",
    "application_fill_facts",
    "assert_resume_payload_has_no_sensitive_fields",
]
