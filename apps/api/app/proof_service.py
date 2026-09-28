from __future__ import annotations

import hashlib
import json
import re
from datetime import datetime, timezone
from typing import Iterable
from uuid import UUID

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session, selectinload

from . import models, proof_action_provider as proof_action_provider_module
from .claim_provider import (
    ClaimProviderConnectionError,
    ClaimProviderInvalidResponseError,
    ClaimProviderNotConfiguredError,
    ClaimProviderTimeoutError,
    get_claim_analysis_provider,
    sanitize_evidence_refs,
)
from .interview_provider import (
    InterviewProviderConnectionError,
    InterviewProviderInvalidResponseError,
    InterviewProviderNotConfiguredError,
    InterviewProviderTimeoutError,
    get_interview_provider,
)
from .interview_skills import skill_records
from .mission_intelligence import bounded_intel_records
from .proof_action_provider import (
    ProofActionProviderConnectionError,
    ProofActionProviderInvalidResponseError,
    ProofActionProviderNotConfiguredError,
    ProofActionProviderTimeoutError,
    get_proof_action_provider,
)
from .job_description_service import content_hash
from .proof_schemas import (
    ClaimAnalysisRead,
    InterviewGapType,
    InterviewSessionRead,
    InterviewSessionStatus,
    InterviewResponsePayload,
    InterviewTurnCreate,
    ProofGuidanceRead,
    InterviewTurnRead,
    ProofActionStatus,
    ReevaluateRead,
    ProofActionCreate,
    ProofActionRead,
    ProofArtifactCreate,
    ProofArtifactRead,
    ReadinessStatus,
    ResumeClaimRead,
    TargetJobCreate,
    TargetJobRead,
)


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _fallback_interview_response(claim_text: str, *, answered_rounds: int, answer: str | None) -> InterviewResponsePayload:
    """Keep the interview lane usable when the LLM provider is transiently unavailable.

    DeepSeek is still attempted first. This grounded fallback asks only about
    ownership and evidence already present in the claim, then completes the
    normal three-round debrief contract without inventing results or metrics.
    """
    if answer is None:
        return InterviewResponsePayload.model_validate({
            "question": f"请先说明你在「{claim_text}」中亲自负责的部分，以及最终交付了什么可核对产出。",
            "skill_id": "PROJECT_DEEP_DIVE",
            "followup_dimensions": ["个人负责", "交付产出"],
            "evaluation": {"strong_points": [], "weak_points": []},
        })
    if answered_rounds < 2:
        question = "请补充一个具体决策：当时比较了哪些方案或约束，你依据什么选择最终方案？"
        return InterviewResponsePayload.model_validate({
            "question": question,
            "skill_id": "DECISION_MAKING",
            "followup_dimensions": ["方案取舍", "判定标准"],
            "evaluation": {
                "score": 5,
                "strong_points": ["能够描述项目中的个人动作"],
                "weak_points": ["还需要补充可核对的决策依据和结果"],
                "reference_answer": "我先明确目标和约束，再比较候选方案，最后用测试或交付结果验证选择。",
            },
        })
    return InterviewResponsePayload.model_validate({
        "question": None,
        "skill_id": None,
        "followup_dimensions": [],
        "evaluation": {
            "score": 5,
            "strong_points": ["能说明项目动作"],
            "weak_points": ["需要保留更具体的过程和结果证据"],
            "gap_type": "EVIDENCE_GAP",
            "why": "回答已经覆盖项目动作，但仍缺少可以复核的过程细节和结果证据。",
            "evidence_refs": [],
            "recommended_next_action": "补全项目背景、个人动作、决策依据和可核对结果。",
            "reference_answer": "我会按背景、个人动作、方案取舍和结果证据说明这段项目经历。",
        },
    })


def _question_key(value: str | None) -> str:
    return re.sub(r"[^\w\u4e00-\u9fff]+", "", (value or "").casefold())


def _avoid_repeated_question(response: InterviewResponsePayload, session: models.InterviewSession) -> InterviewResponsePayload:
    """Prevent a provider from sending the same prompt twice in one session."""
    question = response.question
    if not question:
        return response
    key = _question_key(question)
    if not key or all(_question_key(turn.question) != key for turn in session.turns):
        return response
    dimensions = [item for item in response.followup_dimensions if item]
    prompts = [
        ("请具体说明你个人负责的交付物、完成步骤和最终结果。", "个人负责", "交付产出"),
        ("请具体说明一次遇到的困难、你采取的措施，以及如何验证结果。", "问题处理", "结果验证"),
        ("如果重新做一次，你会先补哪项信息或测试？为什么？", "复盘改进", "验证计划"),
    ]
    prompt, *fallback_dimensions = prompts[min(session.round_count, len(prompts) - 1)]
    return response.model_copy(update={
        "question": prompt,
        "skill_id": response.skill_id or "EVIDENCE_GAP",
        "followup_dimensions": dimensions or fallback_dimensions,
    })

def _safe_uuid(value: object) -> UUID | None:
    try:
        text = str(value).strip()
        if not text or text in {'None', 'null'}:
            return None
        return UUID(text)
    except (TypeError, ValueError, AttributeError):
        return None




def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    profile = db.scalar(select(models.UserProfile).where(models.UserProfile.id == profile_id))
    if profile is None:
        raise _http(404, "Profile not found")
    if profile.status != "CONFIRMED":
        raise _http(409, "证明补强需要先确认个人档案。请在本岗位确认 Profile 后，再继续证明流程。")
    return profile


def _target_job(db: Session, target_job_id: UUID, *, for_update: bool = False) -> models.TargetJob:
    statement = select(models.TargetJob).where(models.TargetJob.id == target_job_id)
    if for_update:
        statement = statement.with_for_update()
    target_job = db.scalar(statement)
    if target_job is None:
        raise _http(404, "Target job not found")
    return target_job


def _target_job_read(row: models.TargetJob) -> TargetJobRead:
    return TargetJobRead(
        id=row.id,
        profile_id=row.profile_id,
        raw_text=row.raw_text,
        source_url=row.source_url,
        content_hash=row.content_hash,
        status=row.status,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _claim_read(row: models.ResumeClaim) -> ResumeClaimRead:
    return ResumeClaimRead(
        id=row.id,
        target_job_id=row.target_job_id,
        profile_id=row.profile_id,
        claim=row.claim,
        current_text=row.current_text,
        suggested_text=row.suggested_text,
        reason=row.reason,
        jd_relevance=row.jd_relevance,
        matched_capabilities=row.matched_capabilities or [],
        evidence_refs=[
            parsed
            for value in (row.evidence_refs or [])
            if str(value).strip() not in {'', 'None', 'null'}
            for parsed in [_safe_uuid(value)]
            if parsed is not None
        ],
        readiness_status=ReadinessStatus(row.readiness_status),
        confidence=row.confidence,
        risk_reason=row.risk_reason,
        attack_surface=row.attack_surface or [],
        fingerprint=row.fingerprint,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _profile_facts(profile: models.UserProfile) -> list[dict[str, object]]:
    facts: list[dict[str, object]] = []
    for collection, kind, fields in (
        (profile.education, "education", ("institution", "degree", "field_of_study", "dates")),
        (profile.experiences, "experience", ("title", "organization", "dates", "description")),
        (profile.certifications, "certification", ("name", "issuer", "date", "score")),
        (profile.skills, "skill", ("name", "proficiency")),
    ):
        for row in collection:
            values = [str(getattr(row, field)) for field in fields if getattr(row, field, None)]
            if values:
                facts.append({"id": str(row.id), "kind": kind, "value": " | ".join(values), "evidence_text": row.evidence_text})
    return facts


def claim_fingerprint(profile: models.UserProfile, target_job: models.TargetJob, artifacts: Iterable[models.ProofArtifact] = ()) -> str:
    payload = {
        "profile_id": str(profile.id),
        "profile_status": profile.status,
        "facts": sorted(
            [
                {
                    "id": str(row.id),
                    "value": str(getattr(row, "canonical_value", None) or getattr(row, "raw_value", None) or getattr(row, "name", None) or getattr(row, "title", None) or getattr(row, "institution", None)),
                    "evidence": row.evidence_text,
                }
                for collection in (profile.education, profile.skills, profile.experiences, profile.certifications)
                for row in collection
            ],
            key=lambda item: item["id"],
        ),
        "target_job": {"id": str(target_job.id), "content_hash": target_job.content_hash},
        "artifacts": sorted(
            [{"id": str(artifact.id), "url": artifact.artifact_url, "text": artifact.artifact_text, "verified_fields": artifact.verified_fields} for artifact in artifacts],
            key=lambda item: item["id"],
        ),
    }
    return hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")).hexdigest()


def create_target_job(db: Session, profile_id: UUID, payload: TargetJobCreate) -> TargetJobRead:
    _profile(db, profile_id)
    digest = content_hash(payload.raw_text)
    existing = db.scalar(select(models.TargetJob).where(models.TargetJob.profile_id == profile_id, models.TargetJob.content_hash == digest))
    if existing is not None:
        raise _http(409, "This target job has already been saved")
    row = models.TargetJob(profile_id=profile_id, raw_text=payload.raw_text, source_url=payload.source_url, content_hash=digest, status="CURRENT")
    db.add(row)
    try:
        db.commit()
        db.refresh(row)
    except IntegrityError as exc:
        db.rollback()
        raise _http(409, "This target job has already been saved") from exc
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target job persistence failed") from exc
    return _target_job_read(row)


def list_target_jobs(db: Session, profile_id: UUID) -> list[TargetJobRead]:
    _profile(db, profile_id)
    return [_target_job_read(row) for row in db.scalars(select(models.TargetJob).where(models.TargetJob.profile_id == profile_id).order_by(models.TargetJob.created_at, models.TargetJob.id)).all()]


def get_target_job(db: Session, target_job_id: UUID) -> TargetJobRead:
    return _target_job_read(_target_job(db, target_job_id))


def _claim_provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ClaimProviderNotConfiguredError):
        return _http(503, "主张分析服务未配置")
    if isinstance(exc, ClaimProviderTimeoutError):
        return _http(504, "主张分析超时，请重试")
    if isinstance(exc, (ClaimProviderConnectionError, ClaimProviderInvalidResponseError)):
        return _http(502, "主张分析返回不可用结果；若履历事实不足请先完善档案，否则请重试")
    return _http(502, "主张分析失败，请重试")


def _analysis_read(target_job: models.TargetJob, claims: list[models.ResumeClaim]) -> ClaimAnalysisRead:
    fingerprint = claims[0].fingerprint if claims else ""
    analysis_profile_id = claims[0].profile_id if claims else target_job.profile_id
    return ClaimAnalysisRead(target_job_id=target_job.id, profile_id=analysis_profile_id, fingerprint=fingerprint, claims=[_claim_read(row) for row in claims])


def get_claim_analysis(db: Session, target_job_id: UUID) -> ClaimAnalysisRead:
    target_job = _target_job(db, target_job_id)
    claims = list(db.scalars(select(models.ResumeClaim).where(models.ResumeClaim.target_job_id == target_job_id).order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)).all())
    if not claims:
        raise _http(404, "尚未生成主张分析。请先在「简历建议」点击继续生成，或从左侧进入「主张核对」。")
    # Claims may bind to mission-local CoW profile while TargetJob stays on Master.
    analysis_profile_id = claims[0].profile_id
    if any(row.profile_id != analysis_profile_id for row in claims):
        raise _http(409, "主张分析已过期，请重新生成后再继续")
    profile = _profile(db, analysis_profile_id)
    fingerprint = claim_fingerprint(profile, target_job, db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.profile_id == profile.id)).all())
    if any(row.fingerprint != fingerprint for row in claims):
        # Soft-heal: usable claim text can continue proof/interview after stamp refresh.
        if any(not (row.claim or "").strip() for row in claims):
            raise _http(409, "主张分析已过期，请重新生成后再继续")
        for row in claims:
            if row.fingerprint != fingerprint:
                row.fingerprint = fingerprint
                row.updated_at = datetime.now(timezone.utc)
        try:
            db.commit()
            for row in claims:
                db.refresh(row)
        except SQLAlchemyError as exc:
            db.rollback()
            raise _http(409, "主张分析已过期，请重新生成后再继续") from exc
    return _analysis_read(target_job, claims)


def generate_claim_analysis(
    db: Session,
    target_job_id: UUID,
    provider=None,
    *,
    profile_id: UUID | None = None,
) -> ClaimAnalysisRead:
    """Analyze resume claims for a target job.

    Optional profile_id overrides target_job.profile_id so mission-local
    (copy-on-write) bound profiles can be confirmed and used without touching Master.
    """
    target_job = _target_job(db, target_job_id)
    profile = _profile(db, profile_id or target_job.profile_id)
    artifacts = list(db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.profile_id == profile.id)).all())
    fingerprint = claim_fingerprint(profile, target_job, artifacts)
    existing = list(db.scalars(select(models.ResumeClaim).where(models.ResumeClaim.target_job_id == target_job_id).order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)).all())
    if existing and all(row.fingerprint == fingerprint for row in existing):
        # Avoid sticky skill-list tokens (Revit/SuperMap/AutoCAD) when project experiences exist.
        facts_preview = _profile_facts(profile)
        has_experience = any(str(f.get("kind") or "") in {"experience", "project"} for f in facts_preview)
        skill_only = has_experience and all(
            len((row.claim or "").strip()) <= 24
            and not any(ch.isspace() for ch in (row.claim or "").strip())
            and not any(ch in (row.claim or "") for ch in "，。；、,.")
            for row in existing
        )
        if not skill_only:
            return _analysis_read(target_job, existing)
    facts = _profile_facts(profile)
    db.rollback()
    provider = provider or get_claim_analysis_provider()
    try:
        proposals = provider.analyze(target_job={"id": str(target_job.id), "raw_text": target_job.raw_text, "source_url": target_job.source_url}, profile_facts=facts)
    except Exception as exc:
        raise _claim_provider_error(exc) from exc
    known_fact_ids = {UUID(str(fact["id"])) for fact in facts}
    for proposal in proposals.claims:
        if any(ref not in known_fact_ids for ref in proposal.evidence_refs):
            raise _http(422, "Claim analysis returned an unknown Profile evidence reference")
        if proposal.suggested_text and not proposal.evidence_refs:
            raise _http(422, "Claim suggestions must be grounded in Profile evidence")
    try:
        locked_job = _target_job(db, target_job_id, for_update=True)
        analysis_profile_id = profile.id
        current_profile = _profile(db, analysis_profile_id)
        current_fingerprint = claim_fingerprint(current_profile, locked_job, db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.profile_id == current_profile.id)).all())
        if current_fingerprint != fingerprint:
            raise _http(409, "Profile or target job changed while analysis was running; retry")
        for row in list(locked_job.claims):
            db.delete(row)
        db.flush()
        capability_values: list[dict[str, object]] = []
        for index, proposal in enumerate(proposals.claims, start=1):
            capabilities = [value.model_dump(mode="json") for value in proposal.matched_capabilities]
            for capability in capabilities:
                if capability not in capability_values:
                    capability_values.append(capability)
            db.add(
                models.ResumeClaim(
                    target_job_id=locked_job.id,
                    profile_id=analysis_profile_id,
                    claim=proposal.claim,
                    current_text=proposal.current_text,
                    suggested_text=proposal.suggested_text,
                    reason=proposal.reason,
                    jd_relevance=proposal.jd_relevance,
                    matched_capabilities=capabilities,
                    evidence_refs=sanitize_evidence_refs(proposal.evidence_refs),
                    readiness_status=proposal.readiness_status.value,
                    confidence=proposal.confidence,
                    risk_reason=proposal.risk_reason,
                    attack_surface=[item.model_dump(mode="json") for item in proposal.attack_surface],
                    fingerprint=current_fingerprint,
                    sort_order=index,
                )
            )
        locked_job.capabilities = capability_values
        locked_job.updated_at = datetime.now(timezone.utc)
        db.commit()
        claims = list(db.scalars(select(models.ResumeClaim).where(models.ResumeClaim.target_job_id == target_job_id).order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)).all())
        return _analysis_read(locked_job, claims)
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Claim analysis persistence failed") from exc



def _mission_for_target_and_profile(
    db: Session, target_job_id: UUID, profile_id: UUID
) -> models.JobMission | None:
    """Resolve JobMission for a target job, honoring mission-local bound_profile_id.

    TargetJob.profile_id stays on Master; mission-local CoW claims bind to
    resume_source.bound_profile_id. Prefer a mission whose effective profile
    matches the claim/profile id.
    """
    missions = list(
        db.scalars(select(models.JobMission).where(models.JobMission.target_job_id == target_job_id)).all()
    )
    if not missions:
        return None
    for mission in missions:
        src = mission.resume_source if isinstance(mission.resume_source, dict) else {}
        bound_raw = src.get("bound_profile_id")
        if bound_raw:
            try:
                if UUID(str(bound_raw)) == profile_id:
                    return mission
            except (TypeError, ValueError):
                pass
        elif mission.profile_id == profile_id:
            return mission
    for mission in missions:
        if mission.profile_id == profile_id:
            return mission
    return missions[0]


def _claim_bound_to_allowed_profile(
    db: Session, claim: models.ResumeClaim, target_job: models.TargetJob
) -> bool:
    """True when claim.profile_id matches TargetJob.profile_id or a mission-local bind."""
    if target_job.profile_id == claim.profile_id:
        return True
    return _mission_for_target_and_profile(db, target_job.id, claim.profile_id) is not None


def _claim(db: Session, claim_id: UUID) -> models.ResumeClaim:
    claim = db.scalar(select(models.ResumeClaim).where(models.ResumeClaim.id == claim_id))
    if claim is None:
        raise _http(404, "Resume claim not found")
    profile = _profile(db, claim.profile_id)
    target_job = _target_job(db, claim.target_job_id)
    if not _claim_bound_to_allowed_profile(db, claim, target_job):
        raise _http(409, "简历主张未绑定到当前任务档案，请重新生成当前岗位的主张分析")
    artifacts = list(db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.profile_id == profile.id)).all())
    current_fp = claim_fingerprint(profile, target_job, artifacts)
    if claim.fingerprint != current_fp:
        # Soft path: usable claim text can start interview after fingerprint self-heal.
        # Do not invent evidence; only refresh staleness stamp when claim content exists.
        if not (claim.claim or "").strip():
            raise _http(409, "简历主张已过期或不可用，请重新生成主张分析后再开始模拟面试")
        claim.fingerprint = current_fp
        claim.updated_at = datetime.now(timezone.utc)
        try:
            db.commit()
            db.refresh(claim)
        except SQLAlchemyError as exc:
            db.rollback()
            raise _http(409, "简历主张已过期，请重新生成主张分析后再开始模拟面试") from exc
    return claim


def _claim_context(db: Session, claim: models.ResumeClaim) -> tuple[models.UserProfile, models.TargetJob, list[dict[str, object]]]:
    profile = _profile(db, claim.profile_id)
    target_job = _target_job(db, claim.target_job_id)
    refs = {UUID(str(value)) for value in (claim.evidence_refs or [])}
    evidence = [fact for fact in _profile_facts(profile) if UUID(str(fact["id"])) in refs]
    for artifact in db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.claim_id == claim.id)).all():
        if artifact.id in refs:
            evidence.append(
                {
                    "id": str(artifact.id),
                    "kind": "artifact",
                    "value": artifact.artifact_url or artifact.artifact_text or "",
                    "evidence_text": artifact.artifact_text or artifact.artifact_url or "",
                }
            )
    return profile, target_job, evidence


def _interview_provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, InterviewProviderNotConfiguredError):
        return _http(503, "Interview service is not configured")
    if isinstance(exc, InterviewProviderTimeoutError):
        return _http(504, "Interview question generation timed out; please retry")
    if isinstance(exc, (InterviewProviderConnectionError, InterviewProviderInvalidResponseError)):
        return _http(502, "Interview question generation failed; please retry")
    return _http(502, "Interview question generation failed; please retry")


def _interview_read(session: models.InterviewSession) -> InterviewSessionRead:
    return InterviewSessionRead(
        id=session.id,
        profile_id=session.profile_id,
        target_job_id=session.target_job_id,
        claim_id=session.claim_id,
        mission_id=session.mission_id,
        status=InterviewSessionStatus(session.status),
        round_count=session.round_count,
        next_question=session.next_question,
        next_skill_id=session.next_skill_id,
        strong_points=list(session.strong_points or []),
        weak_points=list(session.weak_points or []),
        gap_type=InterviewGapType(session.gap_type) if session.gap_type else None,
        gap_why=session.gap_why,
        gap_evidence=[UUID(str(value)) for value in (session.gap_evidence or [])],
        recommended_next_action=session.recommended_next_action,
        turns=[
            InterviewTurnRead(
                id=turn.id,
                round_number=turn.round_number,
                skill_id=turn.skill_id,
                question=turn.question,
                answer=turn.answer,
                followup_dimensions=list(turn.followup_dimensions or []),
                evaluation=dict(turn.evaluation or {}),
                created_at=turn.created_at,
            )
            for turn in session.turns
        ],
        created_at=session.created_at,
        updated_at=session.updated_at,
    )


def _interview_turn_context(session: models.InterviewSession) -> list[dict[str, object]]:
    return [
        {
            "round_number": turn.round_number,
            "skill_id": turn.skill_id,
            "question": turn.question,
            "answer": turn.answer,
            "evaluation": turn.evaluation or {},
        }
        for turn in session.turns
    ]


def _final_resume_context(mission: models.JobMission | None) -> dict[str, object] | None:
    """Return only the latest confirmed target resume for interview prompting."""
    if mission is None:
        return None
    resumes = [row for row in (mission.target_resumes or []) if str(row.status).upper() == "CONFIRMED"]
    if not resumes:
        return None
    resume = sorted(resumes, key=lambda row: (row.version, row.updated_at), reverse=True)[0]
    return {
        "version": resume.version,
        "positioning_statement": resume.positioning_statement,
        "bullets": [
            {
                "source_experience_id": str(bullet.source_experience_id) if bullet.source_experience_id else None,
                "text": bullet.final_text or bullet.suggested_text,
                "original_text": bullet.original_text,
                "status": bullet.status,
            }
            for bullet in resume.bullets
            if bullet.status in {"ACCEPTED", "EDITED"}
        ],
    }


def start_interview_session(db: Session, claim_id: UUID, provider=None) -> InterviewSessionRead:
    claim = _claim(db, claim_id)
    readiness = str(claim.readiness_status or "").strip().upper()
    evidence_refs = list(claim.evidence_refs or [])
    # Invent-ownership / JD-gap claims are strengthen targets, not mock interview ownership drills.
    if readiness == "UNSUPPORTED" and not evidence_refs:
        raise _http(
            422,
            "这条主张还没有履历证据支撑，属于补强缺口，不能直接开始模拟面试。请先回到证明补强补充证据，或选择有证据的主张。",
        )
    profile, target_job, evidence = _claim_context(db, claim)
    mission = _mission_for_target_and_profile(db, target_job.id, profile.id)
    # A fresh start owns the claim's active lane. Close stale sessions before
    # asking the provider so the client cannot resume an older conversation.
    active_sessions = db.scalars(
        select(models.InterviewSession).where(
            models.InterviewSession.claim_id == claim.id,
            models.InterviewSession.status == InterviewSessionStatus.ACTIVE.value,
        )
    ).all()
    for active in active_sessions:
        active.status = InterviewSessionStatus.INVALIDATED.value
        active.next_question = None
        active.next_skill_id = None
        active.updated_at = datetime.now(timezone.utc)
    provider = provider or get_interview_provider()
    pack_topics = []
    if mission is not None and getattr(mission, "interview_packs", None):
        latest_pack = mission.interview_packs[-1]
        pack_topics = list((latest_pack.pack or {}).get("topics") or []) if isinstance(latest_pack.pack, dict) else []
    try:
        interview_intel = bounded_intel_records(mission.interview_intel if mission is not None else [])
        response = provider.ask(
            target_job={"id": str(target_job.id), "raw_text": target_job.raw_text, "interview_pack": pack_topics[:12], "interview_intel": interview_intel, "final_resume": _final_resume_context(mission)},
            claim={"id": str(claim.id), "claim": claim.claim, "matched_capabilities": claim.matched_capabilities or []},
            evidence=evidence,
            skills=skill_records(),
            turns=[],
            answer=None,
        )
    except Exception as exc:
        # A provider timeout or transient gateway error must not strand the
        # user before the first question. DeepSeek remains the primary path;
        # this keeps a grounded, retryable interview lane available.
        response = _fallback_interview_response(claim.claim, answered_rounds=0, answer=None)
    if response.question is None or response.skill_id is None:
        raise _http(422, "Interview provider must return an opening question")
    session = models.InterviewSession(
        profile_id=profile.id,
        target_job_id=target_job.id,
        claim_id=claim.id,
        mission_id=mission.id if mission else None,
        status=InterviewSessionStatus.ACTIVE.value,
        round_count=0,
        next_question=response.question,
        next_skill_id=response.skill_id,
    )
    db.add(session)
    db.flush()
    db.add(
        models.InterviewTurn(
            session_id=session.id,
            round_number=1,
            skill_id=response.skill_id,
            question=response.question,
            answer=None,
            followup_dimensions=response.followup_dimensions,
            evaluation={},
        )
    )
    try:
        db.commit()
        db.refresh(session)
        return _interview_read(session)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Interview session persistence failed") from exc


def get_interview_session(db: Session, session_id: UUID) -> InterviewSessionRead:
    session = db.scalar(select(models.InterviewSession).where(models.InterviewSession.id == session_id))
    if session is None:
        raise _http(404, "Interview session not found")
    _claim(db, session.claim_id)
    return _interview_read(session)


def list_interview_sessions(db: Session, claim_id: UUID) -> list[InterviewSessionRead]:
    _claim(db, claim_id)
    rows = db.scalars(
        select(models.InterviewSession)
        .options(selectinload(models.InterviewSession.turns))
        .where(models.InterviewSession.claim_id == claim_id)
        .order_by(models.InterviewSession.created_at.desc(), models.InterviewSession.id.desc())
    ).all()
    return [_interview_read(row) for row in rows]


def submit_interview_turn(db: Session, session_id: UUID, payload: InterviewTurnCreate, provider=None) -> InterviewSessionRead:
    session = db.scalar(select(models.InterviewSession).where(models.InterviewSession.id == session_id))
    if session is None:
        raise _http(404, "Interview session not found")
    if session.status != InterviewSessionStatus.ACTIVE.value:
        raise _http(409, "This interview session is already complete")
    claim = _claim(db, session.claim_id)
    profile, target_job, evidence = _claim_context(db, claim)
    pending = next((turn for turn in reversed(session.turns) if turn.answer is None), None)
    if pending is None:
        raise _http(409, "This interview session has no pending question")
    if session.round_count >= 5:
        raise _http(409, "Interview sessions are limited to five rounds")
    provider = provider or get_interview_provider()
    mission = _mission_for_target_and_profile(db, target_job.id, profile.id)
    pack_topics = []
    if mission is not None and getattr(mission, "interview_packs", None):
        latest_pack = mission.interview_packs[-1]
        pack_topics = list((latest_pack.pack or {}).get("topics") or []) if isinstance(latest_pack.pack, dict) else []
    try:
        interview_intel = bounded_intel_records(mission.interview_intel if mission is not None else [])
        response = provider.ask(
            target_job={"id": str(target_job.id), "raw_text": target_job.raw_text, "interview_pack": pack_topics[:12], "interview_intel": interview_intel, "final_resume": _final_resume_context(mission)},
            claim={"id": str(claim.id), "claim": claim.claim, "matched_capabilities": claim.matched_capabilities or []},
            evidence=evidence,
            skills=skill_records(),
            turns=_interview_turn_context(session),
            answer=payload.answer,
        )
    except Exception as exc:
        response = _fallback_interview_response(claim.claim, answered_rounds=session.round_count, answer=payload.answer)
    response = _avoid_repeated_question(response, session)
    pending.answer = payload.answer
    pending.evaluation = response.evaluation.model_dump(mode="json")
    session.round_count += 1
    session.updated_at = datetime.now(timezone.utc)
    is_complete = response.question is None or response.skill_id is None or session.round_count >= 5
    if is_complete:
        if session.round_count < 3:
            # Providers may conclude early. Keep the answered turn and append
            # a deterministic Chinese follow-up so debrief never dead-ends.
            followup_question = response.question or "请再补充一轮：这项工作中你亲自完成了什么，结果如何？"
            followup_skill = response.skill_id or pending.skill_id or "EVIDENCE_GAP"
            session.next_question = followup_question
            session.next_skill_id = followup_skill
            db.add(
                models.InterviewTurn(
                    session_id=session.id,
                    round_number=pending.round_number + 1,
                    skill_id=followup_skill,
                    question=followup_question,
                    answer=None,
                    followup_dimensions=["个人负责", "结果证据"],
                    evaluation={},
                )
            )
            is_complete = False
        elif response.evaluation.gap_type is None:
            # The round cap is a hard stop. A provider that omits gap_type
            # must not strand the user on a disabled submit button; preserve
            # the answer and classify the unresolved evidence conservatively.
            response = response.model_copy(update={
                "evaluation": response.evaluation.model_copy(update={
                    "gap_type": InterviewGapType.EVIDENCE_GAP,
                    "why": response.evaluation.why or "面试轮次已完成，但仍缺少可核对的结果证据。",
                    "recommended_next_action": response.evaluation.recommended_next_action or "补全项目背景、个人动作、决策依据和可核对结果。",
                })
            })
        if is_complete:
            session.status = InterviewSessionStatus.COMPLETED.value
            session.next_question = None
            session.next_skill_id = None
            session.strong_points = response.evaluation.strong_points
            session.weak_points = response.evaluation.weak_points
            session.gap_type = response.evaluation.gap_type.value
            session.gap_why = response.evaluation.why
            session.gap_evidence = [str(value) for value in response.evaluation.evidence_refs]
            session.recommended_next_action = response.evaluation.recommended_next_action
    else:
        session.next_question = response.question
        session.next_skill_id = response.skill_id
        db.add(
            models.InterviewTurn(
                session_id=session.id,
                round_number=pending.round_number + 1,
                skill_id=response.skill_id,
                question=response.question,
                answer=None,
                followup_dimensions=response.followup_dimensions,
                evaluation={},
            )
        )
    try:
        db.commit()
        db.refresh(session)
        return _interview_read(session)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Interview session persistence failed") from exc


def _proof_action_provider_error(exc: Exception) -> HTTPException:
    if isinstance(exc, ProofActionProviderNotConfiguredError):
        return _http(503, "Proof action service is not configured")
    if isinstance(exc, ProofActionProviderTimeoutError):
        return _http(504, "Proof action generation timed out; please retry")
    if isinstance(exc, (ProofActionProviderConnectionError, ProofActionProviderInvalidResponseError)):
        return _http(502, "Proof action generation failed; please retry")
    return _http(502, "Proof action generation failed; please retry")


def _action_read(action: models.ProofAction) -> ProofActionRead:
    return ProofActionRead(
        id=action.id,
        claim_id=action.claim_id,
        profile_id=action.profile_id,
        title=action.title,
        why_now=action.why_now,
        target_claim=action.target_claim,
        target_gap=InterviewGapType(action.target_gap),
        estimated_hours=action.estimated_hours,
        artifact_type=action.artifact_type,
        definition_of_done=action.definition_of_done,
        expected_evidence=action.expected_evidence,
        status=ProofActionStatus(action.status),
        completed_at=action.completed_at,
        updated_at=action.updated_at,
    )


def _artifact_read(artifact: models.ProofArtifact) -> ProofArtifactRead:
    return ProofArtifactRead(
        id=artifact.id,
        action_id=artifact.action_id,
        claim_id=artifact.claim_id,
        profile_id=artifact.profile_id,
        artifact_type=artifact.artifact_type,
        artifact_url=artifact.artifact_url,
        artifact_text=artifact.artifact_text,
        manually_confirmed=artifact.manually_confirmed,
        verified_fields=list(artifact.verified_fields or []),
        created_at=artifact.created_at,
    )



def _deterministic_strengthen_specs(claim: models.ResumeClaim) -> list[dict[str, object]]:
    """Concrete executable strengthen steps — no interview debrief required."""
    claim_text = (claim.claim or "").strip() or "当前主张"
    return [
        {
            "title": "回答 3–5 个事实追问",
            "why_now": f"「{claim_text}」仍偏弱，先用可核对事实把主张钉住。",
            "target_gap": InterviewGapType.EVIDENCE_GAP.value,
            "estimated_hours": 0.5,
            "artifact_type": "FACT_QA_NOTES",
            "definition_of_done": "写下 3–5 个具体事实回答（时间、角色、动作、结果、可核对来源）。",
            "expected_evidence": "事实问答笔记（含可核对细节，而非空泛形容词）。",
        },
        {
            "title": "补全项目背景 / 个人动作 / 结果",
            "why_now": f"面试官会追问你在「{claim_text}」里到底做了什么。",
            "target_gap": InterviewGapType.PROJECT_GAP.value,
            "estimated_hours": 1.0,
            "artifact_type": "PROJECT_WRITEUP",
            "definition_of_done": "补全项目背景、你的个人动作、以及可量化或可复核的结果。",
            "expected_evidence": "一段结构化项目说明（背景 / 动作 / 结果）。",
        },
    ]


def seed_deterministic_proof_actions(db: Session, claim_id: UUID) -> list[ProofActionRead]:
    """Ensure weak claims have executable ProofActions bound to the claim profile."""
    claim = _claim(db, claim_id)
    existing = list_proof_actions(db, claim_id)
    if existing:
        allowed_types = {"FACT_QA_NOTES", "PROJECT_WRITEUP"}
        legacy = [row for row in db.scalars(select(models.ProofAction).where(models.ProofAction.claim_id == claim_id)).all() if row.artifact_type not in allowed_types]
        if legacy:
            for row in legacy:
                db.delete(row)
            db.commit()
            existing = list_proof_actions(db, claim_id)
        return existing
    profile, target_job, _evidence = _claim_context(db, claim)
    mission = _mission_for_target_and_profile(db, target_job.id, profile.id)
    caps = claim.matched_capabilities or []
    cap_name = caps[0].get("name") if caps and isinstance(caps[0], dict) else None
    try:
        for spec in _deterministic_strengthen_specs(claim):
            db.add(
                models.ProofAction(
                    profile_id=profile.id,
                    claim_id=claim.id,
                    session_id=None,
                    mission_id=mission.id if mission else None,
                    title=str(spec["title"]),
                    why_now=str(spec["why_now"]),
                    target_claim=claim.claim,
                    target_gap=str(spec["target_gap"]),
                    estimated_hours=float(spec["estimated_hours"]),
                    artifact_type=str(spec["artifact_type"]),
                    definition_of_done=str(spec["definition_of_done"]),
                    expected_evidence=str(spec["expected_evidence"]),
                    target_capability=cap_name,
                    status=ProofActionStatus.PROPOSED.value,
                )
            )
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "补强动作保存失败，请稍后重试") from exc
    return list_proof_actions(db, claim_id)


def _completed_debrief(db: Session, claim_id: UUID) -> models.InterviewSession:
    session = db.scalar(
        select(models.InterviewSession)
        .where(models.InterviewSession.claim_id == claim_id, models.InterviewSession.status == InterviewSessionStatus.COMPLETED.value)
        .order_by(models.InterviewSession.updated_at.desc(), models.InterviewSession.id.desc())
    )
    if session is None:
        raise _http(409, "请先完成压力测试，再创建补强证据")
    return session


def list_proof_actions(db: Session, claim_id: UUID) -> list[ProofActionRead]:
    _claim(db, claim_id)
    rows = db.scalars(select(models.ProofAction).where(models.ProofAction.claim_id == claim_id).order_by(models.ProofAction.created_at, models.ProofAction.id)).all()
    return [_action_read(row) for row in rows]


def generate_proof_actions(db: Session, claim_id: UUID, provider=None) -> list[ProofActionRead]:
    claim = _claim(db, claim_id)
    # The user-facing flow has exactly two next steps. Keep provider-backed
    # action planning available for explicit callers/tests, but the product
    # endpoint always exposes the focused deterministic pair and cleans up
    # legacy cards from earlier versions.
    if provider is None and proof_action_provider_module._provider is None:
        return seed_deterministic_proof_actions(db, claim_id)
    existing = list_proof_actions(db, claim_id)
    if existing:
        return existing
    # Strengthen path must not hard-require mock-interview debrief; seed executable actions first.
    try:
        debrief = _completed_debrief(db, claim_id)
    except HTTPException as exc:
        if exc.status_code == 409:
            return seed_deterministic_proof_actions(db, claim_id)
        raise
    profile, target_job, evidence = _claim_context(db, claim)
    mission = _mission_for_target_and_profile(db, target_job.id, profile.id)
    provider = provider or get_proof_action_provider()
    try:
        proposals = provider.plan(
            claim={"id": str(claim.id), "claim": claim.claim, "readiness_status": claim.readiness_status, "matched_capabilities": claim.matched_capabilities or []},
            debrief={"gap_type": debrief.gap_type, "why": debrief.gap_why, "recommended_next_action": debrief.recommended_next_action},
            evidence=evidence,
        )
    except Exception as exc:
        # Provider failure after debrief: still give the user something executable.
        return seed_deterministic_proof_actions(db, claim_id)
    for proposal in proposals.actions:
        if proposal.target_claim.strip() != claim.claim.strip():
            raise _http(422, "补强证据必须针对当前主张")
    try:
        for proposal in proposals.actions:
            db.add(
                models.ProofAction(
                    profile_id=profile.id,
                    claim_id=claim.id,
                    session_id=debrief.id,
                    mission_id=mission.id if mission else None,
                    title=proposal.title,
                    why_now=proposal.why_now,
                    target_claim=proposal.target_claim,
                    target_gap=proposal.target_gap.value,
                    estimated_hours=proposal.estimated_hours,
                    artifact_type=proposal.artifact_type,
                    definition_of_done=proposal.definition_of_done,
                    expected_evidence=proposal.expected_evidence,
                    target_capability=(claim.matched_capabilities or [{}])[0].get("name") if claim.matched_capabilities else None,
                    status=ProofActionStatus.PROPOSED.value,
                )
            )
        db.commit()
        rows = list(db.scalars(select(models.ProofAction).where(models.ProofAction.claim_id == claim_id).order_by(models.ProofAction.created_at, models.ProofAction.id)).all())
        return [_action_read(row) for row in rows]
    except HTTPException:
        db.rollback()
        raise
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Proof action persistence failed") from exc


def submit_proof_artifact(db: Session, action_id: UUID, payload: ProofArtifactCreate) -> ProofArtifactRead:
    action = db.scalar(select(models.ProofAction).where(models.ProofAction.id == action_id))
    if action is None:
        raise _http(404, "Proof action not found")
    if payload.action_id != action_id:
        raise _http(422, "Artifact action_id does not match the path")
    claim = _claim(db, action.claim_id)
    existing = db.scalar(
        select(models.ProofArtifact).where(
            models.ProofArtifact.action_id == action_id,
            models.ProofArtifact.artifact_url == payload.artifact_url,
            models.ProofArtifact.artifact_text == payload.artifact_text,
        )
    )
    if existing is not None:
        return _artifact_read(existing)
    artifact = models.ProofArtifact(
        profile_id=action.profile_id,
        claim_id=claim.id,
        action_id=action.id,
        artifact_type=payload.artifact_type,
        artifact_url=payload.artifact_url,
        artifact_text=payload.artifact_text,
        manually_confirmed=payload.manually_confirmed,
        verified_fields=payload.verified_fields,
    )
    db.add(artifact)
    action.status = ProofActionStatus.COMPLETED.value
    action.completed_at = datetime.now(timezone.utc)
    action.updated_at = action.completed_at
    # Special mark actions: stop claiming rather than inventing evidence.
    mark_type = (payload.artifact_type or action.artifact_type or "").upper()
    if mark_type in {"NO_EXPERIENCE_MARK", "NON_CLAIMABLE_MARK"}:
        claim.readiness_status = ReadinessStatus.UNSUPPORTED.value
        if mark_type == "NO_EXPERIENCE_MARK":
            claim.risk_reason = "用户确认没有这段经历，已停止主张。"
        else:
            claim.risk_reason = "用户确认该能力暂不可主张，已移出可主张清单。"
    try:
        db.commit()
        db.refresh(artifact)
        return _artifact_read(artifact)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Proof artifact persistence failed") from exc


def reevaluate_claim(db: Session, claim_id: UUID) -> ReevaluateRead:
    claim = db.scalar(select(models.ResumeClaim).where(models.ResumeClaim.id == claim_id))
    if claim is None:
        raise _http(404, "Resume claim not found")
    profile = _profile(db, claim.profile_id)
    target_job = _target_job(db, claim.target_job_id)
    artifacts = list(db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.claim_id == claim_id).order_by(models.ProofArtifact.created_at, models.ProofArtifact.id)).all())
    if not artifacts:
        raise _http(409, "Add a proof artifact before re-evaluating this claim")
    before_status = ReadinessStatus(claim.readiness_status)
    before_confidence = claim.confidence
    if before_status == ReadinessStatus.UNSUPPORTED:
        after_status = ReadinessStatus.UNSUPPORTED
        reason = "The submitted artifact does not establish an experience that was previously absent."
    elif before_status == ReadinessStatus.WEAK_EVIDENCE:
        after_status = ReadinessStatus.DEFENDABLE
        reason = "A user-submitted artifact now gives the claim a concrete proof surface for interview follow-up."
    else:
        after_status = before_status
        reason = "The claim already had sufficient readiness; the artifact strengthens its evidence trail."
    new_refs = [artifact.id for artifact in artifacts]
    claim.readiness_status = after_status.value
    claim.confidence = min(1.0, max(before_confidence, before_confidence + 0.2))
    claim.evidence_refs = sanitize_evidence_refs([*(claim.evidence_refs or []), *(str(value) for value in new_refs)])
    claim.risk_reason = reason
    claim.fingerprint = claim_fingerprint(profile, target_job, artifacts)
    claim.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Claim re-evaluation persistence failed") from exc
    return ReevaluateRead(
        claim_id=claim.id,
        before_readiness=before_status,
        after_readiness=after_status,
        before_confidence=before_confidence,
        after_confidence=claim.confidence,
        new_evidence_refs=new_refs,
        reason=reason,
        artifacts=[_artifact_read(artifact) for artifact in artifacts],
    )


def generate_proof_guidance(db: Session, claim_id: UUID, action_type: str) -> ProofGuidanceRead:
    """Return direct AI coaching for the selected strengthening path.

    This endpoint deliberately does not create a ProofArtifact. The user is
    asking for coaching or additional questions, so requiring a link/text
    submission here made the old re-evaluation page a dead end.
    """
    claim = _claim(db, claim_id)
    normalized = str(action_type or "").strip().upper()
    if normalized not in {"FACT_QA_NOTES", "PROJECT_WRITEUP"}:
        raise _http(422, "请选择事实追问或项目补全。")
    profile, target_job, evidence = _claim_context(db, claim)
    mission = _mission_for_target_and_profile(db, target_job.id, profile.id)
    sessions = list_interview_sessions(db, claim.id)
    completed = next((item for item in sessions if item.status == InterviewSessionStatus.COMPLETED), None)
    debrief = {
        "gap_type": completed.gap_type.value if completed and completed.gap_type else claim.readiness_status,
        "why": completed.gap_why if completed else claim.risk_reason,
        "strong_points": completed.strong_points if completed else [],
        "weak_points": completed.weak_points if completed else [],
        "recommended_next_action": completed.recommended_next_action if completed else None,
        "turns": [
            {"round_number": turn.round_number, "question": turn.question, "answer": turn.answer, "evaluation": turn.evaluation or {}}
            for turn in (completed.turns if completed else [])
        ],
        "interview_intel": bounded_intel_records(mission.interview_intel if mission is not None else []),
    }
    claim_payload = {"id": str(claim.id), "claim": claim.claim, "readiness_status": claim.readiness_status, "matched_capabilities": claim.matched_capabilities or []}
    evidence_payload = evidence
    try:
        provider = proof_action_provider_module._provider or get_proof_action_provider()
        return provider.guidance(claim=claim_payload, debrief=debrief, evidence=evidence_payload, action_type=normalized)
    except Exception:
        if normalized == "FACT_QA_NOTES":
            return ProofGuidanceRead(
                claim_id=claim.id,
                action_type=normalized,
                title="事实追问",
                summary="请按顺序回答下面 3–5 个问题，只写你亲自做过且可以核对的事实。",
                questions=[
                    "项目发生在什么时间、背景和目标是什么？",
                    "你亲自负责了哪一部分，具体做了哪些动作？",
                    "你比较或选择过哪些方案，依据什么做决定？",
                    "结果如何验证，有哪些数据、文档、模型或答辩材料可以核对？",
                ],
                generated_by="fallback",
            )
        return ProofGuidanceRead(
            claim_id=claim.id,
            action_type=normalized,
            title="项目补齐指南",
            summary="围绕面试暴露的缺口，把项目补成一份能被复核的项目说明，不预设没有发生过的结果。",
            steps=[
                "补写项目背景、目标和约束，说明为什么要做这项工作。",
                "列出你的个人动作、方案取舍和实际交付物。",
                "设计一次可重复的测试或对比，记录指标、基准和结论。",
                "整理成项目说明、方案对比表、测试记录或可展示 Demo。",
            ],
            learning=["指标定义与实验设计", "系统方案取舍和约束分析", "结果复盘与结构化表达"],
            expected_outputs=["项目背景与个人分工说明", "方案对比或决策记录", "测试记录与结果复盘"],
            generated_by="fallback",
        )
