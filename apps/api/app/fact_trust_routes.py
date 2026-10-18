"""HTTP routes for candidate fact attestation."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy.orm import Session

from .database import get_db
from .fact_impact_service import analyze_impact, parse_fact_key, sync_mission
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


class _SyncRequest(BaseModel):
    mission_id: UUID
    expected_revision: int | None = None


@router.get("/profiles/{profile_id}/facts/{source_kind}/{source_id}/impact")
def read_fact_impact(profile_id: UUID, source_kind: str, source_id: UUID, db: Session = Depends(get_db)) -> dict:
    """指令 5.2：这项事实关联了几份岗位简历、其中几份可能需要更新。只读，不改动任何内容。"""
    return analyze_impact(db, profile_id, source_kind, source_id)


@router.get("/profiles/{profile_id}/facts/impact")
def read_fact_impact_by_key(profile_id: UUID, fact_key: str, db: Session = Depends(get_db)) -> dict:
    """按事实键查询影响面（``experience:<uuid>:description:0``）。"""
    kind, source_id = parse_fact_key(fact_key)
    return analyze_impact(db, profile_id, kind, UUID(source_id))


@router.post("/profiles/{profile_id}/facts/{source_kind}/{source_id}/sync")
def sync_fact_to_mission(
    profile_id: UUID, source_kind: str, source_id: UUID, payload: _SyncRequest, db: Session = Depends(get_db)
) -> dict:
    """指令 5.2：只把事实同步到用户**明确选择**的那一个岗位，绝不批量覆盖。"""
    return sync_mission(db, profile_id, source_kind, source_id, payload.mission_id, payload.expected_revision)
