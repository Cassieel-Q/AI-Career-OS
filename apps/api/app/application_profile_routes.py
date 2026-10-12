"""ResumeProfile / ApplicationProfile 边界路由（目标四）。"""
from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from . import application_profile_service as svc
from .database import get_db


router = APIRouter(prefix="/api/v1")


class ApplicationProfilePayload(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_number: str | None = None
    family_info: str | None = None
    health_status: str | None = None
    archive_location: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    availability: str | None = None


class ApplicationProfileRead(BaseModel):
    model_config = ConfigDict(extra="ignore")

    id_number: str | None = None
    family_info: str | None = None
    health_status: str | None = None
    archive_location: str | None = None
    emergency_contact: str | None = None
    emergency_phone: str | None = None
    availability: str | None = None


@router.get("/profiles/{profile_id}/application-profile", response_model=ApplicationProfileRead)
def read_application_profile(profile_id: UUID, db: Session = Depends(get_db)):
    return svc.application_profile_read(svc.get_application_profile(db, profile_id))


@router.put("/profiles/{profile_id}/application-profile", response_model=ApplicationProfileRead)
def put_application_profile(profile_id: UUID, payload: ApplicationProfilePayload, db: Session = Depends(get_db)):
    row = svc.upsert_application_profile(db, profile_id, payload.model_dump(exclude_none=True))
    return svc.application_profile_read(row)


@router.get("/profiles/{profile_id}/resume-facts")
def read_resume_facts(profile_id: UUID, db: Session = Depends(get_db)):
    """简历生成可读的事实（不含网申敏感字段）。"""
    return svc.resume_visible_facts(db, profile_id)


@router.get("/profiles/{profile_id}/application-fill-facts")
def read_application_fill_facts(profile_id: UUID, db: Session = Depends(get_db)):
    """网申填表可读：ResumeProfile + ApplicationProfile。"""
    return svc.application_fill_facts(db, profile_id)
