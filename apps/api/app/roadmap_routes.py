from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .roadmap_schemas import ReplanRequest, RoadmapRead, RoadmapTaskRead, RoadmapTaskUpdate
from .roadmap_service import generate_roadmap, get_roadmap, replan_roadmap, update_roadmap_task


router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/roadmap", response_model=RoadmapRead)
def read_roadmap(profile_id: UUID, db: Session = Depends(get_db)) -> RoadmapRead:
    return get_roadmap(db, profile_id)


@router.post("/profiles/{profile_id}/roadmap", response_model=RoadmapRead)
def create_roadmap(profile_id: UUID, db: Session = Depends(get_db)) -> RoadmapRead:
    return generate_roadmap(db, profile_id)


@router.patch("/roadmap-tasks/{task_id}", response_model=RoadmapTaskRead)
def patch_roadmap_task(task_id: UUID, payload: RoadmapTaskUpdate, db: Session = Depends(get_db)) -> RoadmapTaskRead:
    return update_roadmap_task(db, task_id, payload)


@router.post("/profiles/{profile_id}/roadmap/replan", response_model=RoadmapRead)
def replan(profile_id: UUID, payload: ReplanRequest | None = None, db: Session = Depends(get_db)) -> RoadmapRead:
    return replan_roadmap(db, profile_id, payload.remaining_weeks if payload else 4)
