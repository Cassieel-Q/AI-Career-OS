from uuid import UUID

from fastapi import APIRouter, Depends, status
from sqlalchemy.orm import Session

from .database import get_db
from .proof_schemas import (
    ClaimAnalysisRead,
    InterviewSessionCreate,
    InterviewSessionRead,
    InterviewTurnCreate,
    ProofActionRead,
    ProofArtifactCreate,
    ProofArtifactRead,
    ProofGuidanceRead,
    ReevaluateRead,
    TargetJobCreate,
    TargetJobRead,
)
from .proof_service import (
    create_target_job,
    generate_proof_actions,
    generate_claim_analysis,
    get_claim_analysis,
    get_interview_session,
    get_target_job,
    list_interview_sessions,
    list_proof_actions,
    list_target_jobs,
    reevaluate_claim,
    generate_proof_guidance,
    start_interview_session,
    submit_proof_artifact,
    submit_interview_turn,
)


router = APIRouter(prefix="/api/v1")


@router.post("/profiles/{profile_id}/target-jobs", response_model=TargetJobRead, status_code=status.HTTP_201_CREATED)
def save_target_job(profile_id: UUID, payload: TargetJobCreate, db: Session = Depends(get_db)) -> TargetJobRead:
    return create_target_job(db, profile_id, payload)


@router.get("/profiles/{profile_id}/target-jobs", response_model=list[TargetJobRead])
def read_target_jobs(profile_id: UUID, db: Session = Depends(get_db)) -> list[TargetJobRead]:
    return list_target_jobs(db, profile_id)


@router.get("/target-jobs/{target_job_id}", response_model=TargetJobRead)
def read_target_job(target_job_id: UUID, db: Session = Depends(get_db)) -> TargetJobRead:
    return get_target_job(db, target_job_id)


@router.get("/target-jobs/{target_job_id}/claim-analysis", response_model=ClaimAnalysisRead)
def read_claim_analysis(target_job_id: UUID, db: Session = Depends(get_db)) -> ClaimAnalysisRead:
    return get_claim_analysis(db, target_job_id)


@router.post("/target-jobs/{target_job_id}/claim-analysis", response_model=ClaimAnalysisRead)
def create_claim_analysis(target_job_id: UUID, db: Session = Depends(get_db)) -> ClaimAnalysisRead:
    return generate_claim_analysis(db, target_job_id)


@router.post("/resume-claims/{claim_id}/interview-sessions", response_model=InterviewSessionRead, status_code=status.HTTP_201_CREATED)
def create_interview_session(claim_id: UUID, _payload: InterviewSessionCreate, db: Session = Depends(get_db)) -> InterviewSessionRead:
    return start_interview_session(db, claim_id)


@router.get("/interview-sessions/{session_id}", response_model=InterviewSessionRead)
def read_interview_session(session_id: UUID, db: Session = Depends(get_db)) -> InterviewSessionRead:
    return get_interview_session(db, session_id)


@router.get("/resume-claims/{claim_id}/interview-sessions", response_model=list[InterviewSessionRead])
def read_interview_sessions(claim_id: UUID, db: Session = Depends(get_db)) -> list[InterviewSessionRead]:
    return list_interview_sessions(db, claim_id)


@router.post("/interview-sessions/{session_id}/turns", response_model=InterviewSessionRead)
def add_interview_turn(session_id: UUID, payload: InterviewTurnCreate, db: Session = Depends(get_db)) -> InterviewSessionRead:
    return submit_interview_turn(db, session_id, payload)


@router.post("/resume-claims/{claim_id}/proof-actions", response_model=list[ProofActionRead])
def create_proof_actions(claim_id: UUID, db: Session = Depends(get_db)) -> list[ProofActionRead]:
    return generate_proof_actions(db, claim_id)


@router.get("/resume-claims/{claim_id}/proof-actions", response_model=list[ProofActionRead])
def read_proof_actions(claim_id: UUID, db: Session = Depends(get_db)) -> list[ProofActionRead]:
    return list_proof_actions(db, claim_id)


@router.post("/proof-actions/{action_id}/artifacts", response_model=ProofArtifactRead, status_code=status.HTTP_201_CREATED)
def create_proof_artifact(action_id: UUID, payload: ProofArtifactCreate, db: Session = Depends(get_db)) -> ProofArtifactRead:
    return submit_proof_artifact(db, action_id, payload)


@router.post("/resume-claims/{claim_id}/re-evaluate", response_model=ReevaluateRead)
def re_evaluate_claim(claim_id: UUID, db: Session = Depends(get_db)) -> ReevaluateRead:
    return reevaluate_claim(db, claim_id)


@router.post("/resume-claims/{claim_id}/proof-guidance", response_model=ProofGuidanceRead)
def create_proof_guidance(claim_id: UUID, action_type: str, db: Session = Depends(get_db)) -> ProofGuidanceRead:
    return generate_proof_guidance(db, claim_id, action_type)
