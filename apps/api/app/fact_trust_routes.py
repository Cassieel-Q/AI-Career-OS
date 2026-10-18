"""HTTP routes for candidate fact attestation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from .database import get_db
from .fact_trust_schemas import FactAttestCreate, FactAttestRead, FactListRead
from .fact_trust_service import attest_fact, list_facts

router = APIRouter(prefix="/api/v1")


@router.get("/profiles/{profile_id}/facts", response_model=FactListRead)
def read_profile_facts(profile_id: UUID, db: Session = Depends(get_db)) -> FactListRead:
    return list_facts(db, profile_id)


@router.post("/profiles/{profile_id}/facts/attest", response_model=FactAttestRead)
def attest_profile_fact(
    profile_id: UUID, payload: FactAttestCreate, db: Session = Depends(get_db)
) -> FactAttestRead:
    return attest_fact(db, profile_id, payload)


@router.get("/profiles/{profile_id}/facts/attested")
def read_attested_facts(profile_id: UUID, db: Session = Depends(get_db)) -> dict[str, object]:
    from .fact_trust_service import attested_fact_texts

    return {"profile_id": str(profile_id), "facts": attested_fact_texts(db, profile_id)}
