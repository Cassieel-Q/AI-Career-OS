"""HTTP contract shared by the Resume Studio browser and external agents."""
from uuid import UUID

from fastapi import APIRouter, Depends, Header, HTTPException
from sqlalchemy.orm import Session

from .database import get_db
from .resume_studio_schemas import StudioOperation
from .resume_studio_service import apply_operation, get_or_create_document, read_document

router = APIRouter(prefix="/api/v1")


@router.get("/job-missions/{mission_id}/resume-studio")
def read_studio(mission_id: UUID, db: Session = Depends(get_db)) -> dict:
    return read_document(get_or_create_document(db, mission_id))


@router.patch("/job-missions/{mission_id}/resume-studio")
def edit_studio(
    mission_id: UUID,
    operation: StudioOperation,
    if_match: str | None = Header(default=None, alias="If-Match"),
    db: Session = Depends(get_db),
) -> dict:
    if if_match is None:
        raise HTTPException(428, "请先读取最新简历修订号。")
    try:
        revision = int(if_match.strip('"'))
    except ValueError as exc:
        raise HTTPException(400, "If-Match 必须是整数修订号。") from exc
    return apply_operation(db, mission_id, revision, operation)
