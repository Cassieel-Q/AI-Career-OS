from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .gap_schemas import GapAnalysisRead
from .gap_service import create_gap_analysis, get_gap_analysis


router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/gap-analysis", response_model=GapAnalysisRead)
def read_gap_analysis(profile_id: UUID, db: Session = Depends(get_db)) -> GapAnalysisRead:
    return get_gap_analysis(db, profile_id)


@router.post("/profiles/{profile_id}/gap-analysis", response_model=GapAnalysisRead)
def generate_gap_analysis(profile_id: UUID, db: Session = Depends(get_db)) -> GapAnalysisRead:
    return create_gap_analysis(db, profile_id)
