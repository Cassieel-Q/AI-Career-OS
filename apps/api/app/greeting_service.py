"""打招呼话术（M3）。

原则：
- **只引用真实存在的内容**：姓名来自档案、经历要点来自用户已确认的定向简历、
  岗位/公司来自投递记录、JD 要点来自岗位分析（有则引用，没有就不写）。
- **不编造**：不虚构数字、不虚构经历、不虚构「对贵司文化的热爱」这类无依据话术。
- **不自动发送**：系统只生成草稿，用户复制后自己去招聘平台粘贴。

两档长度：
- 简洁版（打招呼弹窗直接粘贴，约 3 句）
- 详细版（站内信 / 邮件正文，约 6-8 句）
"""
from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from . import models


def _shorten(text: str, limit: int = 60) -> str:
    text = (text or "").strip()
    if len(text) <= limit:
        return text
    cut = text[:limit]
    # 在最后一个句读处截断，避免半句话
    for sep in ("；", "，", "、", " ", "："):
        pos = cut.rfind(sep)
        if pos >= limit // 2:
            return cut[:pos] + "…"
    return cut + "…"


def _resume_facts(db: Session, application: models.JobApplication) -> dict:
    """从已确认的定向简历取真实事实；没有就用主档案兜底（如实标注）。"""
    name = ""
    highlights: list[str] = []
    source = "none"
    resume = None
    if application.resume_version_id:
        resume = db.get(models.TargetResume, application.resume_version_id)
    if resume is None and application.mission_id:
        resume = db.scalar(
            select_resume(application.mission_id)
        )
    if resume is not None:
        source = "target_resume"
        for bullet in sorted(resume.bullets, key=lambda b: b.sort_order):
            if bullet.status in {"ACCEPTED", "EDITED"} and (bullet.final_text or bullet.suggested_text):
                highlights.append((bullet.final_text or bullet.suggested_text).strip())
        profile = db.get(models.UserProfile, application.profile_id)
        if profile is not None:
            name = profile.full_name or ""
    if not highlights:
        # 兜底：主档案确认过的经历标题（只是「做过什么」，不展开细节）
        source = "profile_experiences" if not highlights else source
        profile = db.get(models.UserProfile, application.profile_id)
        if profile is not None:
            name = name or profile.full_name or ""
            for experience in db.scalars(
                _experience_query(application.profile_id)
            ):
                summary = " ".join(piece for piece in [experience.title, experience.organization] if piece)
                if summary:
                    highlights.append(summary)
    return {"name": name, "highlights": highlights[:3], "source": source}


def select_resume(mission_id) -> models.TargetResume | None:
    return select(models.TargetResume).where(
        models.TargetResume.mission_id == mission_id,
        models.TargetResume.status == "CONFIRMED",
    ).order_by(models.TargetResume.version.desc())


def _experience_query(profile_id):
    return select(models.Experience).where(
        models.Experience.profile_id == profile_id,
        models.Experience.evidence_text.isnot(None),
    ).limit(3)


def _jd_requirements(db: Session, application: models.JobApplication) -> list[str]:
    """JD 要求：取岗位解析里结构化的要求字段（有则用，无则空）。"""
    if not application.mission_id:
        return []
    mission = db.get(models.JobMission, application.mission_id)
    if mission is None or not mission.parsed_jd:
        return []
    analysis = mission.parsed_jd if isinstance(mission.parsed_jd, dict) else {}
    requirements = analysis.get("requirements") or analysis.get("must_have") or analysis.get("required") or []
    result = []
    for item in requirements[:3]:
        text = item if isinstance(item, str) else str(item.get("text") or item.get("title") or "")
        if text.strip():
            result.append(_shorten(text, 50))
    return result


def build_greetings(db: Session, application: models.JobApplication) -> dict:
    """生成简洁版 + 详细版话术草稿（确定性模板，不调用模型、不编造）。"""
    facts = _resume_facts(db, application)
    name = facts["name"] or "我"
    highlights = facts["highlights"]
    jd_points = _jd_requirements(db, application)

    evidence_sentence = "、".join(_shorten(text, 46) for text in highlights[:2]) if highlights else ""
    match_sentence = (
        f"这与岗位要求的「{'」「'.join(jd_points[:2])}」可以直接对应" if jd_points and highlights
        else (f"这些经历覆盖了「{'」「'.join(jd_points[:2])}」的方向" if jd_points else "")
    )

    if highlights:
        short = (
            f"您好，我是{name}，正在应聘{application.role}岗位。"
            f"我的相关经历：{evidence_sentence}。"
            + (f"{match_sentence}，期待有机会进一步沟通。" if match_sentence else "期待有机会进一步沟通。")
        )
    else:
        short = (
            f"您好，我是{name}，正在应聘{application.role}岗位。"
            "我的简历已附上，期待有机会进一步沟通。"
        )

    long_parts: list[str] = []
    long_parts.append(f"您好：我是{name}，对贵司「{application.company}」的{application.role}岗位很感兴趣。")
    if highlights:
        long_parts.append(f"简要介绍我的相关经历：{ '；'.join(_shorten(text, 70) for text in highlights) }。")
    if jd_points:
        long_parts.append(f"从岗位描述看，这个岗位需要：{'；'.join(jd_points)}。")
        if highlights:
            long_parts.append("以上经历与这些要求能直接对应，具体细节可以当面或电话沟通。")
    else:
        long_parts.append("详细经历请见附件简历。")
    if application.location:
        long_parts.append(f"工作地点（{application.location}）与我符合。")
    long_parts.append("期待能获得进一步沟通的机会，谢谢！")
    greeting_long = "".join(piece for piece in long_parts if piece)

    return {
        "short": short.strip(),
        "long": greeting_long.strip(),
        "grounded_on": {
            "name_source": "profile" if facts["name"] else "fallback",
            "facts_source": facts["source"],
            "highlight_count": len(highlights),
            "jd_points_count": len(jd_points),
        },
    }
