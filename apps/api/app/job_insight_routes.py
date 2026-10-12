"""岗位洞察路由：岗位关键词分析 + 简历×岗位匹配度 + 简历原文读写。

用户诉求对应：
- 「增加一个对岗位的分析，用 api 分析形成 2~3 个关键词，并在岗位表格里显示」→ job-analysis；
- 「准备度应该按现有简历与岗位的匹配度来调用 api 分析，说明为什么匹配 / 哪里不匹配 / 是否值得投递」
  → match-analysis；
- 「简历工作台里放原始文字供用户自己修改」→ resume-text。
"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from . import models
from .database import get_db
from .job_insight_service import get_job_analysis, get_match_analysis, profile_resume_text
from .job_insight_service import assemble_profile_text

router = APIRouter(prefix="/api/v1")

MAX_RESUME_TEXT_CHARS = 60_000


class ResumeTextPayload(BaseModel):
    raw_text: str = Field(default="", max_length=MAX_RESUME_TEXT_CHARS)


class ResumeTextRead(BaseModel):
    profile_id: str
    raw_text: str
    source: str  # EDITED_TEXT / PROFILE_FACTS / MISSING


# ---------------------------------------------------------------------------
# 岗位关键词
# ---------------------------------------------------------------------------


@router.get("/job-missions/{mission_id}/job-analysis")
def read_job_analysis(mission_id: UUID, refresh: bool = False, db: Session = Depends(get_db)):
    return get_job_analysis(db, mission_id, refresh=refresh)


@router.post("/job-missions/{mission_id}/job-analysis")
def refresh_job_analysis(mission_id: UUID, db: Session = Depends(get_db)):
    return get_job_analysis(db, mission_id, refresh=True)


# ---------------------------------------------------------------------------
# 简历 × 岗位匹配度
# ---------------------------------------------------------------------------


@router.get("/job-missions/{mission_id}/match-analysis")
def read_match_analysis(mission_id: UUID, refresh: bool = False, db: Session = Depends(get_db)):
    return get_match_analysis(db, mission_id, refresh=refresh)


@router.post("/job-missions/{mission_id}/match-analysis")
def refresh_match_analysis(mission_id: UUID, db: Session = Depends(get_db)):
    return get_match_analysis(db, mission_id, refresh=True)


# ---------------------------------------------------------------------------
# 简历原文（简历工作台）
# ---------------------------------------------------------------------------


def _profile_or_404(db: Session, profile_id: UUID) -> models.UserProfile:
    row = db.get(models.UserProfile, profile_id)
    if row is None:
        raise HTTPException(status_code=404, detail="档案不存在")
    return row


@router.get("/profiles/{profile_id}/resume-text", response_model=ResumeTextRead)
def read_resume_text(profile_id: UUID, db: Session = Depends(get_db)):
    profile = _profile_or_404(db, profile_id)
    raw = (getattr(profile, "resume_text", None) or "").strip()
    if raw:
        return ResumeTextRead(profile_id=str(profile.id), raw_text=raw, source="EDITED_TEXT")
    assembled = assemble_profile_text(db, profile).strip()
    return ResumeTextRead(
        profile_id=str(profile.id),
        raw_text=assembled,
        source="PROFILE_FACTS" if assembled else "MISSING",
    )


@router.put("/profiles/{profile_id}/resume-text", response_model=ResumeTextRead)
def save_resume_text(profile_id: UUID, payload: ResumeTextPayload, db: Session = Depends(get_db)):
    profile = _profile_or_404(db, profile_id)
    text = (payload.raw_text or "").strip()
    profile.resume_text = text or None
    db.commit()
    if text:
        return ResumeTextRead(profile_id=str(profile.id), raw_text=text, source="EDITED_TEXT")
    assembled = assemble_profile_text(db, profile).strip()
    return ResumeTextRead(
        profile_id=str(profile.id),
        raw_text=assembled,
        source="PROFILE_FACTS" if assembled else "MISSING",
    )


@router.delete("/job-missions/{mission_id}/job-analysis", status_code=204)
def clear_job_analysis(mission_id: UUID, db: Session = Depends(get_db)):
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    mission.analysis = None
    db.commit()
    return None


@router.delete("/job-missions/{mission_id}/match-analysis", status_code=204)
def clear_match_analysis(mission_id: UUID, db: Session = Depends(get_db)):
    mission = db.get(models.JobMission, mission_id)
    if mission is None:
        raise HTTPException(status_code=404, detail="岗位不存在")
    mission.match_analysis = None
    db.commit()
    return None


__all__ = ["router", "profile_resume_text"]
