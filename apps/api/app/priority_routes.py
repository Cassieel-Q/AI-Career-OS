from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .priority_schemas import PriorityListRead, PriorityUpdate
from .priority_service import get_priorities, update_priorities


router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/priorities", response_model=PriorityListRead)
def read_priorities(profile_id: UUID, db: Session = Depends(get_db)) -> PriorityListRead:
    return get_priorities(db, profile_id)


@router.put("/profiles/{profile_id}/priorities", response_model=PriorityListRead)
def save_priorities(profile_id: UUID, payload: PriorityUpdate, db: Session = Depends(get_db)) -> PriorityListRead:
    return update_priorities(db, profile_id, payload)
