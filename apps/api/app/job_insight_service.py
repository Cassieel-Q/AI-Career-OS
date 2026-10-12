"""岗位洞察编排：把 mission / profile 的数据整理成模型输入，并把结果缓存到库上。

对外只暴露四个函数：
- ``get_job_analysis`` / ``refresh_job_analysis``：岗位关键词（2~3 个）；
- ``get_match_analysis`` / ``refresh_match_analysis``：简历 × 岗位匹配度。

设计取舍：
- **缓存落库**（``job_missions.analysis`` / ``job_missions.match_analysis``）：岗位列表是高频页面，
  不能每次进页面都调模型；只有用户点「重新分析」才刷新。
- **简历原文优先**：优先用 ``user_profiles.resume_text``（用户在简历工作台里编辑过的原文），
  老档案没有这一列内容时，用已确认的事实（经历 / 技能 / 教育 / 证书）拼一段出来，
  保证不会因为历史数据缺字段而返回空。
"""
from __future__ import annotations

from datetime import datetime, timezone
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models
from .job_insight_provider import analyze_job_keywords, analyze_job_match

VERDICT_LABEL = {
    "strong": "值得投递",
    "maybe": "先补齐再投",
    "weak": "暂不建议投递",
}

SOURCE_LABEL = {
    "LLM": "模型分析",
    "LOCAL_RULE": "本地规则估算",
    "NONE": "尚未分析",
}


# ---------------------------------------------------------------------------
# 取数
# ---------------------------------------------------------------------------


def _mission_or_404(db: Session, mission_id: UUID) -> models.JobMission:
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    return mission


def _as_dict(raw: object) -> dict:
    return dict(raw) if isinstance(raw, dict) else {}


def mission_jd_text(db: Session, mission: models.JobMission, *, limit: int = 6000) -> str:
    target_job = db.get(models.TargetJob, mission.target_job_id)
    raw = (getattr(target_job, "raw_text", None) or "") if target_job is not None else ""
    return raw[:limit]


def mission_requirement_names(db: Session, mission: models.JobMission) -> list[str]:
    """岗位要求名：优先取结构化解析结果，其次取 what_matters 的核心能力。"""
    names: list[str] = []

    def push(value: object) -> None:
        text = str(value or "").strip()
        if text and text not in names:
            names.append(text)

    parsed = _as_dict(mission.parsed_jd)
    for bucket in ("requirements", "preferred_requirements"):
        for item in parsed.get(bucket) or []:
            if isinstance(item, dict):
                push(item.get("text") or item.get("name"))
    for item in parsed.get("capabilities") or []:
        push(item)

    what_matters = _as_dict(mission.what_matters)
    for item in what_matters.get("core_capabilities") or []:
        if isinstance(item, dict):
            push(item.get("name"))
    for item in what_matters.get("high_importance_requirements") or []:
        if isinstance(item, dict):
            push(item.get("text") or item.get("name"))

    return names[:40]


def _bound_profile_id(mission: models.JobMission) -> UUID | None:
    raw = _as_dict(mission.resume_source).get("bound_profile_id")
    if not raw:
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def effective_profile(db: Session, mission: models.JobMission) -> models.UserProfile | None:
    bound = _bound_profile_id(mission)
    profile = db.get(models.UserProfile, bound) if bound else None
    if profile is None:
        profile = db.get(models.UserProfile, mission.profile_id)
    return profile


def assemble_profile_text(db: Session, profile: models.UserProfile) -> str:
    """没有简历原文时，用已确认事实拼一段可读文本。"""
    lines: list[str] = []
    head = " ".join(part for part in [profile.full_name, profile.email, profile.city] if part)
    if head:
        lines.append(head)
    skills = [s.name for s in db.scalars(select(models.ProfileSkill).where(models.ProfileSkill.profile_id == profile.id)).all() if s.name]
    if skills:
        lines.append("技能：" + "、".join(skills))
    for row in db.scalars(
        select(models.Experience).where(models.Experience.profile_id == profile.id)
    ).all():
        segment = " · ".join(part for part in [row.title, row.organization, row.dates] if part)
        if row.description:
            segment = f"{segment}：{row.description}" if segment else row.description
        if segment:
            lines.append("经历：" + segment)
    for row in db.scalars(select(models.Education).where(models.Education.profile_id == profile.id)).all():
        segment = " · ".join(
            part
            for part in [row.institution, row.degree, row.field_of_study, row.dates]
            if part
        )
        if segment:
            lines.append("教育：" + segment)
    for row in db.scalars(select(models.Certification).where(models.Certification.profile_id == profile.id)).all():
        if row.name:
            lines.append("证书：" + row.name)
    return "\n".join(lines)


def profile_resume_text(db: Session, mission: models.JobMission) -> tuple[str, bool]:
    """返回 (简历文本, 是否来自用户维护的原文)。"""
    profile = effective_profile(db, mission)
    if profile is None:
        return "", False
    raw = (getattr(profile, "resume_text", None) or "").strip()
    if raw:
        return raw, True
    return assemble_profile_text(db, profile).strip(), False


# ---------------------------------------------------------------------------
# 岗位关键词
# ---------------------------------------------------------------------------


def get_job_analysis(db: Session, mission_id: UUID, *, refresh: bool = False) -> dict:
    mission = _mission_or_404(db, mission_id)
    cached = _as_dict(mission.analysis)
    if cached.get("keywords") and not refresh:
        return cached
    result = analyze_job_keywords(
        role=mission.role,
        company=mission.company,
        jd_text=mission_jd_text(db, mission),
        requirement_names=mission_requirement_names(db, mission),
    )
    payload = {
        **result,
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    mission.analysis = payload
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


# ---------------------------------------------------------------------------
# 简历 × 岗位匹配度
# ---------------------------------------------------------------------------


def _has_meaningful_resume(db: Session, mission: models.JobMission) -> bool:
    resume_text, from_raw = profile_resume_text(db, mission)
    if from_raw:
        return True
    # 拼出来的事实文本至少要有一段经历/技能，才认为「有简历」。
    return bool(resume_text.strip())


def get_match_analysis(db: Session, mission_id: UUID, *, refresh: bool = False) -> dict:
    mission = _mission_or_404(db, mission_id)
    cached = _as_dict(mission.match_analysis)
    if cached.get("score") is not None and not refresh:
        return cached
    resume_text, from_raw = profile_resume_text(db, mission)
    result = analyze_job_match(
        role=mission.role,
        company=mission.company,
        resume_text=resume_text,
        jd_text=mission_jd_text(db, mission),
        requirement_names=mission_requirement_names(db, mission),
        has_resume=bool(resume_text.strip()),
    )
    payload = {
        **result,
        "verdict_label": VERDICT_LABEL.get(str(result.get("verdict")), "待评估"),
        "resume_source": "EDITED_TEXT" if from_raw else ("PROFILE_FACTS" if resume_text.strip() else "MISSING"),
        "resume_chars": len(resume_text),
        "generated_at": datetime.now(timezone.utc).isoformat(),
    }
    mission.match_analysis = payload
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    return payload


def cached_insight(mission: models.JobMission) -> dict:
    """给岗位列表用的轻量投影（不触发任何模型调用）。"""
    analysis = _as_dict(mission.analysis)
    match = _as_dict(mission.match_analysis)
    keywords = [str(k) for k in (analysis.get("keywords") or []) if str(k).strip()][:3]
    score = match.get("score")
    try:
        score_value = int(score) if score is not None else None
    except (TypeError, ValueError):
        score_value = None
    return {
        "keywords": keywords,
        "summary": str(analysis.get("summary") or ""),
        "analysis_source": str(analysis.get("source") or "NONE"),
        "match_score": score_value,
        "match_verdict": str(match.get("verdict") or "") or None,
        "match_verdict_label": str(match.get("verdict_label") or "") or None,
        "match_source": str(match.get("source") or "NONE"),
    }


__all__ = [
    "VERDICT_LABEL",
    "SOURCE_LABEL",
    "assemble_profile_text",
    "cached_insight",
    "effective_profile",
    "get_job_analysis",
    "get_match_analysis",
    "mission_jd_text",
    "mission_requirement_names",
    "profile_resume_text",
]
