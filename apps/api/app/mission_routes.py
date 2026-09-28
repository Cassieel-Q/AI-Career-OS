from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Request, UploadFile, status
from sqlalchemy.orm import Session

from .database import get_db
from .mission_schemas import AdvanceWorkflow, ConfirmResumeSource, ExperienceSelectionPayload, MissionCreate, MissionIdentityUpdate, MissionOutcomeCreate, MissionReanalyze, RecoverEvidenceCreate, TargetResumeBulletUpdate, TargetResumeGenerateRequest
from .mission_service import (
    add_mission_outcome,
    advance_mission_workflow,
    archive_mission,
    delete_mission,
    bind_mission_resume_from_extraction,
    confirm_resume_source,
    list_missions_sharing_master,
    confirm_strategy,
    confirm_target_resume,
    create_mission,
    create_mission_proof_actions,
    generate_claims_for_mission,
    generate_experience_selection,
    generate_interview_pack,
    generate_red_team,
    generate_resume_strategy,
    generate_target_resume,
    get_experience_selection,
    get_interview_pack,
    get_mission,
    get_readiness,
    get_red_team,
    get_what_matters,
    mark_role_continue,
    reanalyze_mission,
    list_missions,
    list_target_resumes,
    mission_re_evaluate,
    proof_state,
    proof_snapshot,
    recover_existing_evidence,
    retry_company_intel,
    restart_resume_optimization,
    save_experience_selection,
    update_resume_bullet,
    update_mission_identity,
)


router = APIRouter(prefix="/api/v1")


@router.post("/profiles/{profile_id}/job-missions", status_code=status.HTTP_201_CREATED)
def create_job_mission(profile_id: UUID, payload: MissionCreate, db: Session = Depends(get_db)):
    return create_mission(db, profile_id, payload)


@router.get("/profiles/{profile_id}/job-missions")
def read_job_missions(profile_id: UUID, db: Session = Depends(get_db)):
    return list_missions(db, profile_id)


@router.get("/job-missions/{mission_id}")
def read_job_mission(mission_id: UUID, db: Session = Depends(get_db)):
    return get_mission(db, mission_id)


@router.post("/job-missions/{mission_id}/archive")
def archive_job_mission(mission_id: UUID, db: Session = Depends(get_db)):
    return archive_mission(db, mission_id)


@router.delete("/job-missions/{mission_id}", status_code=status.HTTP_200_OK)
def delete_job_mission(mission_id: UUID, db: Session = Depends(get_db)):
    return delete_mission(db, mission_id)


@router.patch("/job-missions/{mission_id}/identity")
def patch_job_mission_identity(mission_id: UUID, payload: MissionIdentityUpdate, db: Session = Depends(get_db)):
    return update_mission_identity(db, mission_id, payload)


@router.get("/job-missions/{mission_id}/what-matters")
def read_what_matters(mission_id: UUID, db: Session = Depends(get_db)):
    return get_what_matters(db, mission_id)


@router.post("/job-missions/{mission_id}/reanalyze")
def reanalyze_job_mission(mission_id: UUID, payload: MissionReanalyze, db: Session = Depends(get_db)):
    return reanalyze_mission(db, mission_id, payload)


@router.post("/job-missions/{mission_id}/claim-analysis")
def create_mission_claim_analysis(mission_id: UUID, db: Session = Depends(get_db)):
    return generate_claims_for_mission(db, mission_id)


@router.post("/job-missions/{mission_id}/experience-selection/generate")
def create_experience_selection(mission_id: UUID, db: Session = Depends(get_db)):
    return generate_experience_selection(db, mission_id)


@router.post("/job-missions/{mission_id}/resume-optimization/regenerate")
def regenerate_resume_optimization(mission_id: UUID, db: Session = Depends(get_db)):
    return restart_resume_optimization(db, mission_id)


@router.get("/job-missions/{mission_id}/experience-selection")
def read_experience_selection(mission_id: UUID, db: Session = Depends(get_db)):
    return get_experience_selection(db, mission_id)


@router.put("/job-missions/{mission_id}/experience-selection")
def save_mission_experience_selection(
    mission_id: UUID,
    payload: ExperienceSelectionPayload,
    confirm: bool = Query(default=False),
    db: Session = Depends(get_db),
):
    return save_experience_selection(db, mission_id, payload, user_confirmed=confirm)


@router.post("/job-missions/{mission_id}/resume-strategy")
def create_resume_strategy(mission_id: UUID, db: Session = Depends(get_db)):
    return generate_resume_strategy(db, mission_id)


@router.post("/job-missions/{mission_id}/target-resumes", status_code=status.HTTP_201_CREATED)
async def create_target_resume(
    mission_id: UUID,
    request: Request,
    db: Session = Depends(get_db),
):
    # FE currently POSTs with an empty body; accept optional JSON without 422.
    from fastapi import HTTPException
    body = TargetResumeGenerateRequest()
    raw = await request.body()
    if raw and raw.strip():
        try:
            body = TargetResumeGenerateRequest.model_validate_json(raw)
        except Exception as exc:
            raise HTTPException(status_code=422, detail="目标简历生成参数无效") from exc
    return generate_target_resume(
        db,
        mission_id,
        source_resume_id=body.source_resume_id,
        strategy_version=body.strategy_version,
    )


@router.get("/job-missions/{mission_id}/target-resumes")
def read_target_resumes(mission_id: UUID, db: Session = Depends(get_db)):
    return list_target_resumes(db, mission_id)


@router.patch("/target-resume-bullets/{bullet_id}")
def edit_target_resume_bullet(bullet_id: UUID, payload: TargetResumeBulletUpdate, db: Session = Depends(get_db)):
    return update_resume_bullet(db, bullet_id, payload)


@router.post("/job-missions/{mission_id}/red-team")
def create_red_team_report(mission_id: UUID, db: Session = Depends(get_db)):
    return generate_red_team(db, mission_id)


@router.get("/job-missions/{mission_id}/red-team")
def read_red_team_report(mission_id: UUID, db: Session = Depends(get_db)):
    return get_red_team(db, mission_id)


@router.post("/job-missions/{mission_id}/interview-pack", status_code=status.HTTP_201_CREATED)
def create_interview_pack(mission_id: UUID, db: Session = Depends(get_db)):
    return generate_interview_pack(db, mission_id)


@router.get("/job-missions/{mission_id}/interview-pack")
def read_interview_pack(mission_id: UUID, db: Session = Depends(get_db)):
    return get_interview_pack(db, mission_id)


@router.get("/job-missions/{mission_id}/proof")
def read_mission_proof(mission_id: UUID, db: Session = Depends(get_db)):
    return proof_state(db, mission_id)


@router.get("/job-missions/{mission_id}/proof-snapshot")
def read_mission_proof_snapshot(mission_id: UUID, db: Session = Depends(get_db)):
    return proof_snapshot(db, mission_id)


@router.post("/job-missions/{mission_id}/proof-actions")
def create_mission_proof_action(mission_id: UUID, claim_id: UUID | None = Query(default=None), db: Session = Depends(get_db)):
    return create_mission_proof_actions(db, mission_id, claim_id)


@router.post("/job-missions/{mission_id}/recover-evidence")
def recover_mission_evidence(mission_id: UUID, payload: RecoverEvidenceCreate, db: Session = Depends(get_db)):
    return recover_existing_evidence(db, mission_id, payload)


@router.post("/job-missions/{mission_id}/re-evaluate")
def re_evaluate_mission_claim(mission_id: UUID, claim_id: UUID = Query(...), db: Session = Depends(get_db)):
    return mission_re_evaluate(db, mission_id, claim_id)


@router.post("/job-missions/{mission_id}/outcomes", status_code=status.HTTP_201_CREATED)
def create_mission_outcome(mission_id: UUID, payload: MissionOutcomeCreate, db: Session = Depends(get_db)):
    return add_mission_outcome(db, mission_id, payload)






@router.get("/profiles/{profile_id}/master-resume-impact")
def get_master_resume_impact(profile_id: UUID, db: Session = Depends(get_db)):
    """List missions under this Master profile for UI warnings before Master overwrite."""
    return {"profile_id": profile_id, "missions": list_missions_sharing_master(db, profile_id)}


@router.post("/job-missions/{mission_id}/resumes")
async def post_mission_resume_pdf(
    mission_id: UUID,
    file: UploadFile = File(...),
    update_master: bool = Form(False),
    db: Session = Depends(get_db),
):
    """Upload PDF bound to this mission only (CoW). Set update_master=true to overwrite Master."""
    from .main import (
        MAX_RESUME_BYTES,
        ResumeExtractionFailure,
        _log_provider_failure,
        _provider_failure_http_exception,
        extract_pdf_text,
        extract_section_first_resume,
        get_resume_provider,
    )
    import hashlib
    import time
    from .mission_service import source_resume_section_order

    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
    data = await file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume PDF exceeds the 10 MB limit（文件超过 10MB，请压缩后重试或改用粘贴文本）")
    text_body = extract_pdf_text(data)
    started = time.perf_counter()
    try:
        provider = get_resume_provider()
        processed = extract_section_first_resume(provider, text_body, timing_ms={})
        digest = hashlib.sha256(data).hexdigest()
        return bind_mission_resume_from_extraction(
            db,
            mission_id,
            processed.result,
            mode="upload",
            update_master=bool(update_master),
            filename=file.filename,
            content_hash_value=digest,
            source_section_order=source_resume_section_order(text_body),
        )
    except HTTPException:
        raise
    except ResumeExtractionFailure as failure:
        _log_provider_failure(failure)
        raise _provider_failure_http_exception(failure) from None
    except Exception as error:
        failure = ResumeExtractionFailure(
            error,
            stage="mission_resume_pdf_ingest",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            total_llm_calls=0,
            provider_call=False,
        )
        _log_provider_failure(failure)
        raise _provider_failure_http_exception(failure) from None


@router.post("/job-missions/{mission_id}/resumes/text")
def post_mission_resume_text(
    mission_id: UUID,
    payload: dict,
    db: Session = Depends(get_db),
):
    """Paste resume text bound to this mission only (CoW). Body: {raw_text, update_master?}."""
    from .main import (
        ResumeExtractionFailure,
        _log_provider_failure,
        _provider_failure_http_exception,
        extract_section_first_resume,
        get_resume_provider,
    )
    import hashlib
    import time
    from .mission_service import source_resume_section_order

    raw = str((payload or {}).get("raw_text") or "").strip()
    if len(raw) < 40:
        raise HTTPException(status_code=422, detail="Resume text is too short")
    update_master = bool((payload or {}).get("update_master") or False)
    started = time.perf_counter()
    try:
        provider = get_resume_provider()
        processed = extract_section_first_resume(provider, raw, timing_ms={})
        digest = hashlib.sha256(raw.encode("utf-8")).hexdigest()
        return bind_mission_resume_from_extraction(
            db,
            mission_id,
            processed.result,
            mode="paste",
            update_master=update_master,
            filename=None,
            content_hash_value=digest,
            source_section_order=source_resume_section_order(raw),
        )
    except HTTPException:
        raise
    except ResumeExtractionFailure as failure:
        _log_provider_failure(failure)
        raise _provider_failure_http_exception(failure) from None
    except Exception as error:
        failure = ResumeExtractionFailure(
            error,
            stage="mission_resume_text_ingest",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            total_llm_calls=0,
            provider_call=False,
        )
        _log_provider_failure(failure)
        raise _provider_failure_http_exception(failure) from None


@router.post("/job-missions/{mission_id}/confirm-resume-source")
def post_confirm_resume_source(mission_id: UUID, payload: ConfirmResumeSource, db: Session = Depends(get_db)):
    return confirm_resume_source(db, mission_id, payload)


@router.post("/job-missions/{mission_id}/confirm-strategy")
def post_confirm_strategy(mission_id: UUID, db: Session = Depends(get_db)):
    return confirm_strategy(db, mission_id)


@router.post("/job-missions/{mission_id}/confirm-target-resume")
def post_confirm_target_resume(mission_id: UUID, db: Session = Depends(get_db)):
    return confirm_target_resume(db, mission_id)


@router.post("/job-missions/{mission_id}/advance")
def post_advance_workflow(mission_id: UUID, payload: AdvanceWorkflow, db: Session = Depends(get_db)):
    return advance_mission_workflow(db, mission_id, payload)


@router.post("/job-missions/{mission_id}/retry-company-intel")
def post_retry_company_intel(mission_id: UUID, db: Session = Depends(get_db)):
    return retry_company_intel(db, mission_id)


@router.post("/job-missions/{mission_id}/continue-to-resume")
def post_continue_to_resume(mission_id: UUID, db: Session = Depends(get_db)):
    return mark_role_continue(db, mission_id)


@router.get("/job-missions/{mission_id}/readiness")
def read_mission_readiness(mission_id: UUID, db: Session = Depends(get_db)):
    return get_readiness(db, mission_id)
