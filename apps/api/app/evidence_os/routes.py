from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from app.database import get_db

from . import gates, models, schemas, service

router = APIRouter(prefix="/evidence-os", tags=["evidence-os"])


def _gate_http(exc: gates.GateViolation) -> HTTPException:
    return HTTPException(status_code=400, detail=exc.as_dict())


def _get_profile_or_404(db: Session, profile_id: UUID):
    from app.models import UserProfile

    row = db.query(UserProfile).filter(UserProfile.id == profile_id).first()
    if not row:
        raise HTTPException(404, "profile not found")
    return row


@router.post("/profiles/{profile_id}/sources", response_model=schemas.SourceOut)
def create_source(profile_id: UUID, body: schemas.SourceCreate, db: Session = Depends(get_db)):
    _get_profile_or_404(db, profile_id)
    return service.create_source(db, profile_id, body)


@router.post("/profiles/{profile_id}/evidence", response_model=schemas.EvidenceOut)
def create_evidence(profile_id: UUID, body: schemas.EvidenceCreate, db: Session = Depends(get_db)):
    _get_profile_or_404(db, profile_id)
    try:
        return service.create_evidence(db, profile_id, body)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.post("/profiles/{profile_id}/claims", response_model=schemas.ClaimOut)
def create_claim(profile_id: UUID, body: schemas.ClaimCreate, db: Session = Depends(get_db)):
    _get_profile_or_404(db, profile_id)
    try:
        return service.create_claim(db, profile_id, body)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.patch("/claims/{claim_id}", response_model=schemas.ClaimOut)
def patch_claim(claim_id: UUID, body: schemas.ClaimUpdate, db: Session = Depends(get_db)):
    claim = db.query(models.EosClaim).filter(models.EosClaim.id == claim_id).first()
    if not claim:
        raise HTTPException(404, "claim not found")
    try:
        return service.update_claim(db, claim, body)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.get("/profiles/{profile_id}/claims", response_model=list[schemas.ClaimOut])
def get_claims(profile_id: UUID, db: Session = Depends(get_db)):
    return service.list_claims(db, profile_id)


@router.post("/profiles/{profile_id}/jds", response_model=schemas.JdOut)
def create_jd(profile_id: UUID, body: schemas.JdCreate, db: Session = Depends(get_db)):
    _get_profile_or_404(db, profile_id)
    jd = service.ingest_jd(db, profile_id, body)
    _, reqs = service.get_jd_with_requirements(db, jd.id)
    out = schemas.JdOut.model_validate(jd)
    out.requirements = [schemas.RequirementOut.model_validate(r) for r in reqs]
    return out


@router.get("/jds/{jd_id}", response_model=schemas.JdOut)
def get_jd(jd_id: UUID, db: Session = Depends(get_db)):
    jd, reqs = service.get_jd_with_requirements(db, jd_id)
    if not jd:
        raise HTTPException(404, "jd not found")
    out = schemas.JdOut.model_validate(jd)
    out.requirements = [schemas.RequirementOut.model_validate(r) for r in reqs]
    return out


@router.post("/profiles/{profile_id}/jds/{jd_id}/match", response_model=schemas.MatchRunResult)
def match_jd(profile_id: UUID, jd_id: UUID, db: Session = Depends(get_db)):
    try:
        return service.run_match(db, profile_id, jd_id)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.post("/profiles/{profile_id}/position", response_model=schemas.VersionOut)
def position(profile_id: UUID, body: schemas.PositionRequest, db: Session = Depends(get_db)):
    try:
        return service.position_and_draft(db, profile_id, body)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.post("/versions/{version_id}/audit", response_model=schemas.AuditResult)
def audit(version_id: UUID, db: Session = Depends(get_db)):
    ver = db.query(models.EosResumeVersion).filter(models.EosResumeVersion.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    return service.audit_version(db, ver)


@router.post("/versions/{version_id}/approve", response_model=schemas.ApprovalOut)
def approve(version_id: UUID, body: schemas.ApproveRequest, db: Session = Depends(get_db)):
    ver = db.query(models.EosResumeVersion).filter(models.EosResumeVersion.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    try:
        return service.approve_version(db, ver, body)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.post("/versions/{version_id}/render", response_model=schemas.RenderResult)
def render(version_id: UUID, db: Session = Depends(get_db)):
    ver = db.query(models.EosResumeVersion).filter(models.EosResumeVersion.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    try:
        return service.render_version(db, ver)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.post("/versions/{version_id}/evals", response_model=list[schemas.EvalReportOut])
def evals(version_id: UUID, db: Session = Depends(get_db)):
    ver = db.query(models.EosResumeVersion).filter(models.EosResumeVersion.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    try:
        return service.run_heuristic_evals(db, ver)
    except gates.GateViolation as e:
        raise _gate_http(e)


@router.get("/versions/{version_id}", response_model=schemas.VersionOut)
def get_version(version_id: UUID, db: Session = Depends(get_db)):
    ver = db.query(models.EosResumeVersion).filter(models.EosResumeVersion.id == version_id).first()
    if not ver:
        raise HTTPException(404, "version not found")
    return ver
