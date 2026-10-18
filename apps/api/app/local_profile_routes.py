"""本机档案恢复与「无模型建档」接口（可信求职 v1.2 · 指令 3.2 / 3.4）。

两条用户反馈对应两个接口：

- **P01**：跳过模型配置后，首次用户根本建不出可编辑的简历（上传必 503，也没有粘贴入口）
  → ``POST /profiles/{id}/resumes/local`` 用本地规则建档，完全不调模型。
- **P07**：清了浏览器存储后，已有档案像「丢了」，而界面只认 localStorage 里的当前 ID
  → ``GET /local/profiles`` 从服务端读回本机已有档案，**只返回 id / 名称 / 时间与条目数**，
  不返回简历正文，避免把本机接口变成可读全部简历内容的枚举接口。

两个接口都过 :func:`app.local_access.assert_trusted_request`，并且额外要求本机客户端头。
"""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from .database import get_db
from .local_access import CLIENT_HEADER, CLIENT_HEADER_VALUE, assert_trusted_request
from .local_resume_parse import local_resume_extraction

router = APIRouter(prefix="/api/v1")

MAX_LOCAL_TEXT = 60_000
#: 档案列表最多返回最近 20 条，避免一次把本机全部档案都列出来。
MAX_PROFILE_LIST = 20


class LocalResumePayload(BaseModel):
    raw_text: str = Field(default="", max_length=MAX_LOCAL_TEXT)


def _assert_local_client(request: Request) -> None:
    """本机来源 + 客户端头；缺一个就 403。"""
    assert_trusted_request(request)
    if (request.headers.get(CLIENT_HEADER) or "").strip() != CLIENT_HEADER_VALUE:
        raise HTTPException(403, "缺少本机客户端标识头，已拒绝该请求。")


@router.get("/local/profiles")
def list_local_profiles(request: Request, db: Session = Depends(get_db)) -> dict[str, object]:
    """本机已有档案的轻量列表（不含简历正文），用于清了浏览器存储后恢复。"""
    _assert_local_client(request)
    from . import models

    rows = db.execute(
        select(
            models.UserProfile.id,
            models.UserProfile.full_name,
            models.UserProfile.status,
            models.UserProfile.created_at,
            models.UserProfile.updated_at,
        )
        .order_by(models.UserProfile.updated_at.desc().nullslast(), models.UserProfile.created_at.desc())
        .limit(MAX_PROFILE_LIST)
    ).all()
    profiles = []
    for profile_id, full_name, status, created_at, updated_at in rows:
        experience_count = db.scalar(
            select(func.count()).select_from(models.Experience).where(models.Experience.profile_id == profile_id)
        )
        profiles.append(
            {
                "profile_id": str(profile_id),
                "label": (full_name or "").strip() or "未命名档案",
                "status": status,
                "experience_count": int(experience_count or 0),
                "created_at": created_at.isoformat() if created_at else None,
                "updated_at": updated_at.isoformat() if updated_at else None,
            }
        )
    return {"profiles": profiles, "total": len(profiles), "truncated": len(profiles) == MAX_PROFILE_LIST}


@router.post("/profiles/{profile_id}/resumes/local")
def ingest_resume_locally(
    profile_id: UUID, payload: LocalResumePayload, request: Request, db: Session = Depends(get_db)
) -> dict[str, object]:
    """不调用模型的建档：只按规则切分原文，每条都带原文证据。

    用户随后可在简历工作台补正；配置好模型后再点「重新提取事实」即可换成模型解析。
    """
    _assert_local_client(request)
    from .profile_service import replace_profile_from_extraction
    from .resume_schemas import ResumeExtractionResult

    raw = (payload.raw_text or "").strip()
    if len(raw) < 10:
        raise HTTPException(422, "简历原文太短，至少 10 个字。")
    extraction = ResumeExtractionResult.model_validate(local_resume_extraction(raw))
    profile = replace_profile_from_extraction(db, profile_id, extraction, raw_text=raw)
    return {
        **profile.model_dump(mode="json"),
        "parse_source": "LOCAL_RULE",
        "parsed_counts": {
            "education": len(extraction.education),
            "skills": len(extraction.skills),
            "experiences": len(extraction.experiences),
            "certifications": len(extraction.certifications),
        },
    }
