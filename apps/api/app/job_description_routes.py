from uuid import UUID

from fastapi import APIRouter, Depends, Response, status
from sqlalchemy.orm import Session

from .database import get_db
from .job_description_schemas import JobDescriptionCreate, JobDescriptionPatch, JobDescriptionRead
from .job_description_service import (
    create_job_description,
    delete_job_description,
    list_job_descriptions,
    update_job_description,
)


router = APIRouter(prefix="/api/v1")


@router.get(
    "/target-roles/{target_role_id}/job-descriptions",
    response_model=list[JobDescriptionRead],
)
def read_job_descriptions(
    target_role_id: UUID,
    db: Session = Depends(get_db),
) -> list[JobDescriptionRead]:
    return list_job_descriptions(db, target_role_id)


@router.post(
    "/target-roles/{target_role_id}/job-descriptions",
    response_model=JobDescriptionRead,
    status_code=status.HTTP_201_CREATED,
)
def save_job_description(
    target_role_id: UUID,
    payload: JobDescriptionCreate,
    db: Session = Depends(get_db),
) -> JobDescriptionRead:
    return create_job_description(db, target_role_id, payload)


@router.patch(
    "/job-descriptions/{jd_id}",
    response_model=JobDescriptionRead,
)
def edit_job_description(
    jd_id: UUID,
    payload: JobDescriptionPatch,
    db: Session = Depends(get_db),
) -> JobDescriptionRead:
    return update_job_description(db, jd_id, payload)


@router.delete(
    "/job-descriptions/{jd_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def remove_job_description(jd_id: UUID, db: Session = Depends(get_db)) -> Response:
    delete_job_description(db, jd_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
