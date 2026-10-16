"""岗位统一入口路由：粘贴 / 公开链接 / 文件 / 真实来源采集 + 筛选 + 去重。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import select
from sqlalchemy.orm import Session

from . import candidate_job_service as candidate_svc
from . import job_ingest_service as ingest
from . import models
from .database import get_db

router = APIRouter(prefix="/api/v1")


class FetchUrlRequest(BaseModel):
    url: str = Field(min_length=4)


class RemoteOkRequest(BaseModel):
    tag: str | None = None
    limit: int = 20


class SaveCollectedRequest(BaseModel):
    model_config = ConfigDict(extra="ignore")

    jobs: list[dict] = Field(default_factory=list)


@router.get("/job-ingest/sources")
def list_sources() -> dict:
    return {
        "sources": [
            {
                "id": "paste",
                "label": "粘贴完整 JD",
                "mode": "manual",
                "auto_collect": False,
                "note": "任何平台都可用的兜底方式，正文由用户提供。",
            },
            {
                "id": "generic_url",
                "label": "公开招聘链接",
                "mode": "fetch",
                "auto_collect": True,
                "note": "抓取公开可访问页面正文；需登录/验证码的页面会明确标记为不支持自动采集。",
            },
            {
                "id": "file",
                "label": "岗位截图 / PDF / 文档",
                "mode": "upload",
                "auto_collect": True,
                "note": "PDF/文本/Word 可直接解析；图片暂不支持自动 OCR，需手动粘贴。",
            },
            {
                "id": "remoteok",
                "label": "RemoteOK 公开接口",
                "mode": "adapter",
                "auto_collect": True,
                "note": "RemoteOK 官方公开 JSON 接口，无需登录，可直接采集真实在招岗位。",
            },
        ]
    }


@router.post("/job-ingest/fetch-url")
def fetch_url(payload: FetchUrlRequest) -> dict:
    return ingest.fetch_url_text(payload.url)


@router.post("/job-ingest/extract-file")
async def extract_file(file: UploadFile = File(...)) -> dict:
    blob = await file.read()
    if not blob:
        raise HTTPException(422, "文件为空。")
    text, status = ingest.extract_file_text(file.filename or "", blob)
    note = {
        "PARSED": "已解析文件正文。",
        "PARSE_EMPTY": "文件里没有可提取的文本。",
        "UNSUPPORTED_IMAGE": "图片暂不支持自动 OCR，请把岗位描述复制成文本后粘贴。",
        "UNSUPPORTED_TYPE": "暂不支持该文件类型，请粘贴文本或改用 PDF/txt/docx。",
    }.get(status, "")
    return {"filename": file.filename, "status": status, "text": text, "note": note, "size_bytes": len(blob)}


@router.post("/job-ingest/collect-remoteok")
def collect_remoteok(payload: RemoteOkRequest) -> dict:
    return ingest.collect_remoteok(tag=payload.tag, limit=payload.limit)


@router.post("/profiles/{profile_id}/job-ingest/save-collected")
def save_collected(profile_id: UUID, payload: SaveCollectedRequest, db: Session = Depends(get_db)) -> dict:
    """把采集到的真实岗位保存进候选岗位库（复用既有 parse/confirm/import 链路）。"""
    saved: list[dict] = []
    skipped: list[dict] = []
    for job in payload.jobs:
        text = (job.get("text") or "").strip()
        if not text:
            skipped.append({"job": job, "reason": "缺少文本"})
            continue
        duplicates = ingest.find_duplicates(db, profile_id, job.get("company"), job.get("role"), job.get("location"))
        if duplicates:
            skipped.append({"company": job.get("company"), "role": job.get("role"), "reason": "DUPLICATE", "matches": duplicates})
            continue
        rows = candidate_svc.parse_candidates(db, profile_id, text, source_kind="LINK")
        # 一条采集结果 = 一条候选岗位：保留信息最全的那条，避免同一岗位被拆成多条草稿。
        if len(rows) > 1:
            keep = max(rows, key=lambda row: len(row.source_excerpt or ""))
            for row in rows:
                if row is not keep:
                    db.delete(row)
            rows = [keep]
        source_key = ingest.dedupe_key(job.get("company"), job.get("role"), job.get("location"))
        for row in rows:
            row.source_url = (job.get("source_url") or "")[:1024] or None
            row.collected_at = _now()
            row.parse_status = "PARSED"
            row.dedupe_key = source_key
            # 采集结果里的公司/岗位/地点比启发式切分更可信，缺项时补齐。
            if not (row.company or "").strip():
                row.company = (job.get("company") or None)
            if not (row.role or "").strip():
                row.role = (job.get("role") or None)
            if not (row.location or "").strip():
                row.location = (job.get("location") or None)
        db.commit()
        saved.append(
            {
                "source": job.get("source"),
                "source_url": job.get("source_url"),
                "company": job.get("company"),
                "role": job.get("role"),
                "candidate_ids": [str(row.id) for row in rows],
            }
        )
    return {"saved": saved, "skipped": skipped, "saved_count": len(saved), "skipped_count": len(skipped)}


@router.get("/profiles/{profile_id}/job-ingest/library")
def job_library(
    profile_id: UUID,
    q: str | None = Query(default=None, description="关键词：公司/岗位/原文"),
    company: str | None = None,
    location: str | None = None,
    kind: str | None = Query(default=None, description="candidate | mission"),
    db: Session = Depends(get_db),
) -> dict:
    """统一岗位库视图：候选草稿 + 已保存岗位，支持关键词/公司/地点筛选。"""
    needle = (q or "").strip().lower()

    def matches(company_value: str | None, role_value: str | None, location_value: str | None, text: str) -> bool:
        if company and (company_value or "").strip().lower() != company.strip().lower():
            return False
        if location and location.strip().lower() not in (location_value or "").strip().lower():
            return False
        if needle:
            haystack = " ".join([company_value or "", role_value or "", location_value or "", text or ""]).lower()
            if needle not in haystack:
                return False
        return True

    items: list[dict] = []

    if kind in (None, "candidate"):
        candidates = db.scalars(
            select(models.CandidateJob).where(models.CandidateJob.profile_id == profile_id)
        ).all()
        for row in candidates:
            if not matches(row.company, row.role, row.location, row.source_excerpt or row.source_text):
                continue
            items.append(
                {
                    "kind": "CANDIDATE",
                    "id": str(row.id),
                    "company": row.company,
                    "role": row.role,
                    "location": row.location,
                    "status": row.status,
                    "source_kind": row.source_kind,
                    "source_url": getattr(row, "source_url", None),
                    "collected_at": _iso(getattr(row, "collected_at", None)),
                    "parse_status": getattr(row, "parse_status", None) or "PARSED",
                    "imported_mission_id": str(row.imported_mission_id) if row.imported_mission_id else None,
                    "excerpt": (row.source_excerpt or "")[:400],
                }
            )

    if kind in (None, "mission"):
        missions = db.scalars(select(models.JobMission).where(models.JobMission.profile_id == profile_id)).all()
        for row in missions:
            if not matches(row.company, row.role, row.location, row.parsed_jd.get("raw_text", "") if isinstance(row.parsed_jd, dict) else ""):
                continue
            items.append(
                {
                    "kind": "MISSION",
                    "id": str(row.id),
                    "company": row.company,
                    "role": row.role,
                    "location": row.location,
                    "status": row.status,
                    "workflow_state": row.workflow_state,
                    "source_url": (row.resume_source or {}).get("source_url") if isinstance(row.resume_source, dict) else None,
                    "collected_at": None,
                    "parse_status": "PARSED",
                    "excerpt": "",
                }
            )

    companies = sorted({item["company"] for item in items if item.get("company")})
    locations = sorted({item["location"] for item in items if item.get("location")})
    return {
        "items": items,
        "count": len(items),
        "facets": {"companies": companies, "locations": locations},
    }


def _now():
    from datetime import datetime, timezone

    return datetime.now(timezone.utc)


def _iso(value):
    return value.isoformat() if value is not None else None
