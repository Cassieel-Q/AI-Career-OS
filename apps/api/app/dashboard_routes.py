from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .dashboard_schemas import DashboardRead
from .dashboard_service import get_dashboard
from .database import get_db


router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/dashboard", response_model=DashboardRead)
def read_dashboard(profile_id: UUID, db: Session = Depends(get_db)) -> DashboardRead:
    return get_dashboard(db, profile_id)
