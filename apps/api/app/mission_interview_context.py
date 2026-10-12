"""第二阶段：统一 ``MissionInterviewContext``。

把「岗位 + 岗位版简历 + 已确认事实 + 相关经历 + 面经」聚合成一份受控上下文，
供助手与固定流程 Agent 使用。四个工具都从这里取数：

- ``get_mission_context``           → 岗位上下文（JD 要点 / what_matters / 面经信号）；
- ``get_target_resume_context``     → 岗位版简历正文（bullet 级，带证据与风险标记）；
- ``get_confirmed_claims_context``  → 已确认事实台账；
- ``get_interview_intel_context``    → 真实面经（demo/CURATED 一律剔除）。

硬约束（对齐设计）：
- 不把整份原始简历与私密联系方式默认发给模型；
- 没有 ``evidence_refs`` 的事实不得作为候选人「已完成」的事实输出——
  这类条目统一放进 ``needs_confirmation``，与 ``verified`` 分离。
"""
from __future__ import annotations

from uuid import UUID

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .company_aliases import canonical_company
from .interview_pack_intel import (
    clean_intel_hint,
    is_synthetic_item,
    strip_internal_tags,
    write_up_questions,
    write_up_signals,
)

CONFIRMED_CLAIM_STATUSES = {"READY", "CONFIRMED", "SUPPORTED"}

# 经历分类：哪些算「相关经历」而不是服务型/无关岗位。
_SERVICE_EXPERIENCE_TYPES = {"SERVICE", "PART_TIME_SERVICE"}


def _safe_uuid(value: object) -> UUID | None:
    try:
        return UUID(str(value))
    except (ValueError, TypeError):
        return None


# ---------------------------------------------------------------------------
# 各取数片段
# ---------------------------------------------------------------------------


def get_confirmed_claims_context(db: Session, profile_id: UUID) -> dict:
    """已确认事实台账（只取已确认状态）。"""
    rows = list(
        db.scalars(
            select(models.ResumeClaim)
            .where(models.ResumeClaim.profile_id == profile_id)
            .order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)
        ).all()
    )
    confirmed = []
    needs_confirmation = []
    for row in rows:
        record = {
            "claim_id": str(row.id),
            "claim": (row.claim or "").strip(),
            "current_text": (row.current_text or "").strip() or None,
            "readiness_status": (row.readiness_status or "").upper(),
            "evidence_refs": list(row.evidence_refs or []),
            "risk_reason": (row.risk_reason or "").strip() or None,
        }
        if record["readiness_status"] in CONFIRMED_CLAIM_STATUSES:
            confirmed.append(record)
        else:
            needs_confirmation.append(record)
    return {
        "confirmed_count": len(confirmed),
        "needs_confirmation_count": len(needs_confirmation),
        "confirmed_claims": confirmed,
        "needs_confirmation": needs_confirmation,
        "source_refs": [
            {"kind": "claim", "id": item["claim_id"], "evidence_refs": item["evidence_refs"]}
            for item in confirmed
        ],
    }


def _bullet_claim_status(bullet: models.TargetResumeBullet) -> str:
    status = (bullet.status or "").upper()
    has_evidence = bool(bullet.evidence_refs)
    if status in {"ACCEPTED", "EDITED"} and has_evidence:
        return "CONFIRMED"
    if has_evidence:
        return "SUPPORTED"
    return "NEEDS_CONFIRMATION"


def get_target_resume_context(
    db: Session,
    *,
    mission_id: UUID | None,
    target_resume_id: UUID | None = None,
) -> dict | None:
    """岗位版简历正文（受控切片）。找不到返回 None。"""
    if mission_id is None:
        return None
    row: models.TargetResume | None = None
    if target_resume_id is not None:
        row = db.get(models.TargetResume, target_resume_id)
        if row is not None and row.mission_id != mission_id:
            row = None
    if row is None:
        candidates = list(
            db.scalars(
                select(models.TargetResume)
                .where(models.TargetResume.mission_id == mission_id)
                .order_by(models.TargetResume.version.desc())
            ).all()
        )
        for item in candidates:
            if (item.status or "").upper() == "CONFIRMED":
                row = item
                break
        row = row or (candidates[0] if candidates else None)
    if row is None:
        return None

    studio = db.scalar(
        select(models.ResumeStudioDocument).where(models.ResumeStudioDocument.mission_id == mission_id)
    )
    section_order: list = []
    if studio is not None:
        layout = studio.layout_config or {}
        section_order = list(layout.get("section_order") or [])
        document = studio.document_json or {}
    else:
        document = {}
    if not section_order:
        section_order = list(row.recommended_experience_order or [])
    if not section_order:
        strategy = row.strategy or {}
        gen = strategy.get("_generation") if isinstance(strategy.get("_generation"), dict) else {}
        section_order = list(gen.get("section_order") or [])

    education = _education_from_document(db, document, mission_id)
    skills = _skills_from_document(document, row)

    bullets_out = []
    verified: list[dict] = []
    needs_confirmation: list[dict] = []
    for bullet in row.bullets:
        text = (bullet.final_text or bullet.suggested_text or bullet.original_text or "").strip()
        if not text:
            continue
        item = {
            "bullet_id": str(bullet.id),
            "bullet_text": text,
            "original_text": (bullet.original_text or "").strip() or None,
            "source_experience_id": str(bullet.source_experience_id) if bullet.source_experience_id else None,
            "claim_status": _bullet_claim_status(bullet),
            "evidence_refs": list(bullet.evidence_refs or []),
            "jd_refs": list(bullet.jd_refs or []),
            "risk_flags": [str(f) for f in (bullet.risk_flags or []) if not str(f).startswith("GROUNDING:")],
            "sort_order": bullet.sort_order,
        }
        bullets_out.append(item)
        # 硬约束：无 evidence_refs 的条目不属于「已完成事实」。
        if item["evidence_refs"] and item["claim_status"] in {"CONFIRMED", "SUPPORTED"}:
            verified.append(item)
        else:
            needs_confirmation.append(item)

    return {
        "resume_id": str(row.id),
        "mission_id": str(row.mission_id),
        "version": row.version,
        "status": row.status,
        "positioning_statement": (row.positioning_statement or "").strip() or None,
        "section_order": section_order,
        "education": education,
        "relevant_experiences": verified,
        "bullets": bullets_out,
        "bullet_text": [item["bullet_text"] for item in bullets_out],
        "skills": skills,
        "verified_count": len(verified),
        "needs_confirmation_count": len(needs_confirmation),
        "needs_confirmation": needs_confirmation,
        "source_refs": [
            {"kind": "target_resume_bullet", "id": item["bullet_id"], "evidence_refs": item["evidence_refs"]}
            for item in verified
        ],
    }


def _education_from_document(db: Session, document: dict, mission_id: UUID) -> list[dict]:
    """优先读岗位版简历里的教育板块；没有则回落到 ResumeProfile 教育（非敏感）。"""
    entries: list[dict] = []
    for section in (document or {}).get("sections") or []:
        kind = str(section.get("kind") or section.get("id") or "").lower()
        if "education" not in kind:
            continue
        for entry in section.get("entries") or []:
            fields = entry.get("fields") or {}
            summary = entry.get("summary") or entry.get("title") or ""
            entries.append(
                {
                    "summary": strip_internal_tags(str(summary)),
                    "fields": {k: strip_internal_tags(str(v)) for k, v in fields.items() if v},
                }
            )
    if entries:
        return entries
    mission = db.get(models.JobMission, mission_id)
    profile_id = mission.profile_id if mission is not None else None
    if profile_id is None:
        return []
    rows = list(
        db.scalars(select(models.Education).where(models.Education.profile_id == profile_id).order_by(models.Education.id)).all()
    )
    return [
        {
            "institution": row.institution,
            "degree": row.degree,
            "field_of_study": row.field_of_study,
            "dates": row.dates,
            "cet4_score": row.cet4_score,
            "cet6_score": row.cet6_score,
        }
        for row in rows
    ]


def _skills_from_document(document: dict, row: models.TargetResume) -> list[str]:
    skills: list[str] = []
    for section in (document or {}).get("sections") or []:
        kind = str(section.get("kind") or section.get("id") or "").lower()
        if "skill" not in kind:
            continue
        for entry in section.get("entries") or []:
            for value in (entry.get("fields") or {}).values():
                if value:
                    skills.append(strip_internal_tags(str(value)))
            if entry.get("summary"):
                skills.append(strip_internal_tags(str(entry["summary"])))
    if skills:
        return list(dict.fromkeys(skills))
    strategy = row.strategy or {}
    gen = strategy.get("_generation") if isinstance(strategy.get("_generation"), dict) else {}
    return [str(s) for s in (gen.get("skills") or [])]


def get_interview_intel_context(db: Session, *, mission_id: UUID | None, company: str | None) -> dict:
    """真实面经信号；**demo / CURATED 合成内容一律剔除**，不做正式准备材料。"""
    items: list = []
    mission = db.get(models.JobMission, mission_id) if mission_id is not None else None
    if mission is not None:
        items = list(mission.interview_intel or [])
    company_target = company or (mission.company if mission is not None else None)

    kept: list[dict] = []
    dropped_synthetic = 0
    for item in items:
        if not isinstance(item, dict):
            continue
        if is_synthetic_item(item):
            dropped_synthetic += 1
            continue
        hint = clean_intel_hint(item.get("hint") or item.get("summary") or item.get("note"))
        questions = [
            {"question": strip_internal_tags(q), "why": strip_internal_tags(w)}
            for q, w in write_up_questions(item)
        ]
        signals = [strip_internal_tags(s) for s in write_up_signals(item)]
        if hint is None and not questions and not signals:
            continue
        kept.append(
            {
                "topic": strip_internal_tags(str(item.get("topic") or item.get("title") or "")) or None,
                "hint": hint,
                "signals": signals,
                "questions": questions,
                "refs": [str(r) for r in (item.get("refs") or item.get("source_refs") or [])],
            }
        )

    return {
        "has_intel": bool(kept),
        "company": company_target,
        "items": kept,
        "dropped_synthetic_count": dropped_synthetic,
        "source_refs": [
            {"kind": "interview_intel", "topic": item.get("topic"), "refs": item.get("refs") or []}
            for item in kept
        ],
    }


# ---------------------------------------------------------------------------
# 聚合
# ---------------------------------------------------------------------------


def _parsed_requirements(mission: models.JobMission | None) -> list:
    if mission is None:
        return []
    parsed = mission.parsed_jd or {}
    for key in ("requirements", "must_have", "nice_to_have", "responsibilities"):
        value = parsed.get(key)
        if isinstance(value, list) and value:
            return value
    what = mission.what_matters or {}
    for key in ("must_have", "requirements", "screening"):
        value = what.get(key)
        if isinstance(value, list) and value:
            return value
    return []


def _relevant_experiences(db: Session, mission: models.JobMission | None) -> tuple[list[dict], list[dict]]:
    """返回 (相关经历, 全部经历)。相关经历已剔除服务型/无关岗位经历。"""
    if mission is None:
        return [], []
    rows = list(
        db.scalars(
            select(models.Experience).where(models.Experience.profile_id == mission.profile_id)
        ).all()
    )
    relevant: list[dict] = []
    everything: list[dict] = []
    for row in rows:
        record = {
            "experience_id": str(row.id),
            "title": row.title,
            "organization": row.organization,
            "dates": row.dates,
            "description": (row.description or "").strip() or None,
            "experience_type": row.experience_type,
        }
        everything.append(record)
        if (row.experience_type or "").upper() in _SERVICE_EXPERIENCE_TYPES:
            continue
        relevant.append(record)
    return relevant, everything


def build_mission_interview_context(
    db: Session,
    *,
    profile_id: UUID,
    mission_id: UUID | None = None,
    target_resume_id: UUID | None = None,
    raw_jd: str | None = None,
    company: str | None = None,
    role: str | None = None,
) -> dict:
    """把岗位、岗位版简历、已确认事实、相关经历、面经聚合成一份受控上下文。"""
    mission: models.JobMission | None = None
    if mission_id is not None:
        candidate = db.get(models.JobMission, mission_id)
        if candidate is not None and candidate.profile_id == profile_id:
            mission = candidate

    resolved_company = (company or (mission.company if mission is not None else None) or "") .strip() or None
    resolved_role = (role or (mission.role if mission is not None else None) or "").strip() or None

    missing_context: list[str] = []
    if raw_jd:
        missing_context.append("raw_jd_from_message")
    elif mission is None or not (mission.parsed_jd or {}):
        missing_context.append("raw_jd")
    if mission is None:
        missing_context.append("mission")

    target_resume = get_target_resume_context(db, mission_id=mission_id, target_resume_id=target_resume_id)
    if target_resume is None:
        missing_context.append("target_resume")

    claims = get_confirmed_claims_context(db, profile_id)
    intel = get_interview_intel_context(db, mission_id=mission_id, company=resolved_company)
    if not intel["has_intel"]:
        missing_context.append("interview_intel")

    source_refs: list[dict] = []
    source_refs.extend(claims["source_refs"])
    if target_resume:
        source_refs.extend(target_resume["source_refs"])
    source_refs.extend(intel["source_refs"])

    relevant_experiences, all_experiences = _relevant_experiences(db, mission)

    mission_raw_jd = None
    if mission is not None:
        mission_raw_jd = (mission.resume_source or {}).get("raw_text")
    return {
        "company": resolved_company,
        "role": resolved_role,
        "mission_id": str(mission.id) if mission is not None else (str(mission_id) if mission_id else None),
        "raw_jd": raw_jd or mission_raw_jd,
        "parsed_requirements": _parsed_requirements(mission),
        "what_matters": dict(mission.what_matters or {}) if mission is not None else {},
        "target_resume": target_resume,
        "target_resume_available": target_resume is not None,
        "confirmed_claims": claims,
        "relevant_experiences": relevant_experiences,
        "all_experiences": all_experiences,
        "interview_intel": intel,
        "source_refs": source_refs,
        "missing_context": list(dict.fromkeys(missing_context)),
    }


def context_summary(ctx: dict) -> dict:
    """给前端顶部展示的轻量摘要。"""
    target = ctx.get("target_resume")
    claims = ctx.get("confirmed_claims") or {}
    intel = ctx.get("interview_intel") or {}
    return {
        "company": ctx.get("company"),
        "role": ctx.get("role"),
        "mission_id": ctx.get("mission_id"),
        "resume_version": target.get("version") if target else None,
        "resume_status": target.get("status") if target else None,
        "experience_count": len(ctx.get("relevant_experiences") or []),
        "confirmed_claims_count": claims.get("confirmed_count", 0),
        "has_interview_intel": bool(intel.get("has_intel")),
        "missing_context": list(ctx.get("missing_context") or []),
    }


def canonical_company_key(value: str | None) -> str:
    return canonical_company(value)


__all__ = [
    "build_mission_interview_context",
    "get_confirmed_claims_context",
    "get_target_resume_context",
    "get_interview_intel_context",
    "context_summary",
]
