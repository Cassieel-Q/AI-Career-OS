from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .jd_analysis_schemas import MarketProfileRead, MarketRequirementEvidenceRead
from .market_profile_service import generate_market_profile, get_market_profile, get_requirement_evidence


router = APIRouter(prefix="/api/v1")


@router.get("/target-roles/{target_role_id}/market-profile", response_model=MarketProfileRead)
def read_market_profile(target_role_id: UUID, db: Session = Depends(get_db)) -> MarketProfileRead:
    return get_market_profile(db, target_role_id)


@router.post("/target-roles/{target_role_id}/market-profile", response_model=MarketProfileRead)
def create_market_profile(target_role_id: UUID, db: Session = Depends(get_db)) -> MarketProfileRead:
    return generate_market_profile(db, target_role_id)


@router.get("/market-requirements/{requirement_id}/evidence", response_model=list[MarketRequirementEvidenceRead])
def read_market_requirement_evidence(requirement_id: UUID, db: Session = Depends(get_db)) -> list[MarketRequirementEvidenceRead]:
    return get_requirement_evidence(db, requirement_id)
