"""HTTP routes for the interview records library."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .database import get_db
from .interview_record_schemas import (
    InterviewRecordCreate,
    InterviewRecordListRead,
    InterviewRecordPatch,
    InterviewRecordRead,
)
from .interview_record_service import (
    create_interview_record,
    evaluate_interview_record,
    get_interview_record,
    list_interview_records,
    patch_interview_record,
)

router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/interview-records", response_model=InterviewRecordListRead)
def read_interview_records(profile_id: UUID, db: Session = Depends(get_db)) -> InterviewRecordListRead:
    return list_interview_records(db, profile_id)


@router.post(
    "/profiles/{profile_id}/interview-records",
    response_model=InterviewRecordRead,
    status_code=status.HTTP_201_CREATED,
)
def create_profile_interview_record(
    profile_id: UUID, payload: InterviewRecordCreate, db: Session = Depends(get_db)
) -> InterviewRecordRead:
    return create_interview_record(db, profile_id, payload)


@router.get("/interview-records/{record_id}", response_model=InterviewRecordRead)
def read_interview_record(record_id: UUID, db: Session = Depends(get_db)) -> InterviewRecordRead:
    return get_interview_record(db, record_id)


@router.patch("/interview-records/{record_id}", response_model=InterviewRecordRead)
def update_interview_record(
    record_id: UUID, payload: InterviewRecordPatch, db: Session = Depends(get_db)
) -> InterviewRecordRead:
    return patch_interview_record(db, record_id, payload)


@router.post("/interview-records/{record_id}/evaluate", response_model=InterviewRecordRead)
def evaluate_record(record_id: UUID, db: Session = Depends(get_db)) -> InterviewRecordRead:
    return evaluate_interview_record(db, record_id)
