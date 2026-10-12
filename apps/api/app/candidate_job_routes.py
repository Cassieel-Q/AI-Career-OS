"""候选岗位暂存区路由（目标一）。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from . import candidate_job_service as svc
from .database import get_db


router = APIRouter(prefix="/api/v1")


class CandidateParseRequest(BaseModel):
    source_text: str = Field(min_length=1)
    source_kind: str = "PASTE"


class CandidateJobRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id: str
    profile_id: str
    source_kind: str
    recognition_source: str
    source_excerpt: str
    company: str | None = None
    role: str | None = None
    location: str | None = None
    status: str
    imported_mission_id: str | None = None
    warnings: list[str] = Field(default_factory=list)
    title: str = ""
    created_at: str | None = None
    updated_at: str | None = None


class CandidateUpdateRequest(BaseModel):
    company: str | None = None
    role: str | None = None
    location: str | None = None


class CandidateImportResult(BaseModel):
    model_config = ConfigDict(extra="ignore")

    candidate_id: str
    mission_id: str
    company: str = ""
    role: str = ""
    status: str
    reused: bool = False


@router.post(
    "/profiles/{profile_id}/candidate-jobs/parse",
    response_model=list[CandidateJobRead],
    status_code=201,
)
def parse_candidate_jobs(profile_id: UUID, payload: CandidateParseRequest, db: Session = Depends(get_db)):
    rows = svc.parse_candidates(db, profile_id, payload.source_text, source_kind=payload.source_kind)
    return [svc.candidate_read(row) for row in rows]


@router.get("/profiles/{profile_id}/candidate-jobs", response_model=list[CandidateJobRead])
def read_candidate_jobs(
    profile_id: UUID,
    status: list[str] | None = Query(default=None),
    db: Session = Depends(get_db),
):
    statuses = status if status else ["DRAFT", "CONFIRMED", "IMPORTED"]
    rows = svc.list_candidates(db, profile_id, statuses=statuses)
    return [svc.candidate_read(row) for row in rows]


@router.get("/candidate-jobs/{candidate_id}", response_model=CandidateJobRead)
def read_candidate_job(candidate_id: UUID, db: Session = Depends(get_db)):
    return svc.candidate_read(svc.get_candidate(db, candidate_id))


@router.patch("/candidate-jobs/{candidate_id}", response_model=CandidateJobRead)
def patch_candidate_job(candidate_id: UUID, payload: CandidateUpdateRequest, db: Session = Depends(get_db)):
    row = svc.update_candidate(
        db,
        candidate_id,
        company=payload.company,
        role=payload.role,
        location=payload.location,
    )
    return svc.candidate_read(row)


@router.post("/candidate-jobs/{candidate_id}/confirm", response_model=CandidateJobRead)
def confirm_candidate_job(candidate_id: UUID, db: Session = Depends(get_db)):
    return svc.candidate_read(svc.confirm_candidate(db, candidate_id))


@router.post("/candidate-jobs/{candidate_id}/reject", response_model=CandidateJobRead)
def reject_candidate_job(candidate_id: UUID, db: Session = Depends(get_db)):
    return svc.candidate_read(svc.reject_candidate(db, candidate_id))


@router.post("/candidate-jobs/{candidate_id}/import", response_model=CandidateImportResult)
def import_candidate_job(candidate_id: UUID, db: Session = Depends(get_db)):
    result = svc.import_candidate(db, candidate_id)
    if not isinstance(result, dict):  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="导入结果异常")
    return result
