from __future__ import annotations

import hashlib
import logging
import re
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

logger = logging.getLogger(__name__)

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from . import models
from .interview_intelligence import InterviewIntelRetriever, InterviewIntelResult
from .mission_intelligence import MissionIntelligenceService, intel_records
from .mission_provider import (
    MissionProviderConnectionError,
    MissionProviderInvalidResponseError,
    MissionProviderNotConfiguredError,
    MissionProviderTimeoutError,
    MissionProviderUpstreamError,
    OpenAIMissionProvider,
    get_mission_provider,
)
from .mission_schemas import (
    AdvanceWorkflow,
    ConfirmResumeSource,
    ResumeSourceMode,
    ExperienceSelectionPayload,
    InterviewPackPayload,
    JobExtractionPayload,
    MissionCreate,
    MissionIdentityUpdate,
    MissionOutcomeCreate,
    MissionReanalyze,
    MissionStatus,
    RecoverEvidenceCreate,
    RedTeamPayload,
    ResumeStrategyPayload,
    TargetResumeBulletUpdate,
    TargetResumePayload,
    WhatMattersPayload,
    WorkflowState,
)
from .claim_provider import sanitize_evidence_refs
from .proof_service import (
    _claim_read,
    _target_job_read,
    generate_claim_analysis,
    generate_proof_actions,
    get_claim_analysis,
    _analysis_read,
    list_interview_sessions,
    list_proof_actions,
    reevaluate_claim,
    seed_deterministic_proof_actions,
    submit_proof_artifact,
)
from .proof_schemas import ProofArtifactCreate
from .resume_intelligence import DefaultCareerEvidenceIntelligence
from .job_description_service import content_hash
from .profile_service import create_draft_profile, replace_profile_from_extraction
from .resume_schemas import ResumeExtractionResult


def _http(status: int, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def provider_http_error(exc: Exception) -> HTTPException:
    """Map provider failures to HTTP errors with a non-empty Chinese detail body.

    Never return an empty body; FE depends on detail for humanizeMissionError.
    Do not leak schema / pydantic / provider stack traces to clients.
    """
    if isinstance(exc, MissionProviderNotConfiguredError):
        return _http(503, "模型服务尚未配置（缺少可用的 API Key 或模型设置），请检查环境后重试。")
    if isinstance(exc, MissionProviderTimeoutError):
        return _http(504, "模型这一步超时了，请重试。已保存的内容还在。")
    if isinstance(exc, MissionProviderUpstreamError):
        code = getattr(exc, "status_code", None)
        if code in {401, 403}:
            return _http(502, "模型服务鉴权失败，请检查 API Key 后重试。")
        if code == 429:
            return _http(502, "模型服务繁忙或配额不足，请稍后重试。")
        return _http(502, "模型上游暂时不可用，请稍后重试。已保存的内容还在。")
    if isinstance(exc, MissionProviderInvalidResponseError):
        reason = str(getattr(exc, "reason", "") or "")
        if reason in {"empty_response", "response_shape", "json_decode"}:
            return _http(502, "模型返回内容无法解析，请重试。已保存的内容还在。")
        if reason == "schema_validation":
            return _http(502, "模型返回的岗位结构化结果不完整，请重试。已保存的内容还在。")
        return _http(502, "模型这一步暂时没跑通，请重试。已保存的内容还在。")
    if isinstance(exc, MissionProviderConnectionError):
        return _http(502, "无法连接模型服务，请检查网络或 OPENAI_BASE_URL 后重试。")
    return _http(502, "模型这一步暂时没跑通，请重试。已保存的内容还在。")


def _soft_jd_extraction() -> JobExtractionPayload:
    """Minimal non-invented extraction when the model cannot run.

    Identity fields are explicitly UNKNOWN; requirements stay empty (no fabricated JD facts).
    """
    return JobExtractionPayload.model_validate(
        {
            "company": "UNKNOWN",
            "role": "UNKNOWN",
            "role_family": "UNKNOWN",
            "seniority": "UNKNOWN",
            "location": None,
            "responsibilities": [],
            "requirements": [],
            "preferred_requirements": [],
            "capabilities": [],
            "keywords": [],
        }
    )


def _soft_what_matters() -> WhatMattersPayload:
    return WhatMattersPayload.model_validate(
        {
            "core_capabilities": [],
            "high_importance_requirements": [],
            "evidence_expected": [],
            "likely_success_signals": [],
            "bonus_capabilities": [],
            "potential_interview_focus": [],
            "confidence": 0.0,
            "jd_evidence_refs": [],
        }
    )


def _workflow_of(mission: models.JobMission) -> str:
    raw = getattr(mission, "workflow_state", None) or WorkflowState.ROLE_UNDERSTOOD.value
    return str(raw)


def _set_workflow(mission: models.JobMission, state: WorkflowState | str) -> None:
    mission.workflow_state = state.value if isinstance(state, WorkflowState) else str(state)


def _require_workflow(mission: models.JobMission, allowed: set[str], detail: str) -> None:
    current = _workflow_of(mission)
    if current not in allowed:
        raise _http(409, detail)


def _require_resume_source(mission: models.JobMission) -> None:
    source = getattr(mission, "resume_source", None)
    if not source:
        raise _http(409, "请先选择这份岗位要用的简历，再继续。")


def _resume_source_dict(mission: models.JobMission) -> dict[str, object]:
    raw = getattr(mission, "resume_source", None)
    return dict(raw) if isinstance(raw, dict) else {}


def _bound_profile_id(mission: models.JobMission) -> UUID | None:
    raw = _resume_source_dict(mission).get("bound_profile_id")
    if raw is None or raw == "":
        return None
    try:
        return UUID(str(raw))
    except (TypeError, ValueError):
        return None


def _effective_profile_for_mission(db: Session, mission: models.JobMission) -> models.UserProfile:
    """Resume prep reads mission-local CoW profile when isolation=mission_local."""
    bound = _bound_profile_id(mission)
    if bound is not None:
        return _profile(db, bound)
    return _profile(db, mission.profile_id)


def list_missions_sharing_master(db: Session, profile_id: UUID) -> list[dict[str, object]]:
    """Missions listed under this Master profile_id (for Master-update warnings)."""
    rows = list(
        db.scalars(
            select(models.JobMission)
            .where(models.JobMission.profile_id == profile_id)
            .order_by(models.JobMission.updated_at.desc(), models.JobMission.id)
        ).all()
    )
    out: list[dict[str, object]] = []
    for row in rows:
        src = _resume_source_dict(row)
        isolation = str(src.get("isolation") or "")
        mode = str(src.get("mode") or "")
        # Mission-local binds keep mission.profile_id as Master for listing; they are
        # not affected by Master content overwrite unless they use mode=master / shared.
        affected = isolation != "mission_local"
        out.append(
            {
                "id": row.id,
                "display_name": row.display_name,
                "company": row.company,
                "role": row.role,
                "resume_mode": mode or None,
                "isolation": isolation or None,
                "affected_by_master_update": affected,
            }
        )
    return out




def advance_workflow(mission: models.JobMission, event: str, *, user_confirmed: bool = True) -> None:
    """Explicit user-confirmed transitions. LLM success alone must not call this with user_confirmed=False to skip ahead."""
    if not user_confirmed:
        raise _http(409, "需要你确认后才能进入下一步。")
    current = _workflow_of(mission)
    transitions: dict[str, dict[str, str]] = {
        "ROLE_UNDERSTOOD": {"select_resume": WorkflowState.RESUME_REQUIRED.value},
        "RESUME_REQUIRED": {"resume_bound": WorkflowState.RESUME_SELECTED.value},
        "RESUME_SELECTED": {"need_selection": WorkflowState.EXPERIENCE_SELECTION_REQUIRED.value},
        "EXPERIENCE_SELECTION_REQUIRED": {"confirm_experiences": WorkflowState.EXPERIENCES_CONFIRMED.value},
        "EXPERIENCES_CONFIRMED": {"need_strategy": WorkflowState.RESUME_STRATEGY_REQUIRED.value},
        "RESUME_STRATEGY_REQUIRED": {"confirm_strategy": WorkflowState.RESUME_STRATEGY_CONFIRMED.value},
        "RESUME_STRATEGY_CONFIRMED": {"target_drafted": WorkflowState.TARGET_RESUME_DRAFT.value},
        "TARGET_RESUME_DRAFT": {"confirm_target": WorkflowState.TARGET_RESUME_CONFIRMED.value},
        "TARGET_RESUME_CONFIRMED": {"start_stress": WorkflowState.STRESS_TEST_REQUIRED.value},
        "STRESS_TEST_REQUIRED": {
            "strengthen": WorkflowState.STRENGTHENING_REQUIRED.value,
            "interview_ready": WorkflowState.INTERVIEW_PREP_READY.value,
        },
        "STRENGTHENING_REQUIRED": {
            "proof_progress": WorkflowState.PROOF_IN_PROGRESS.value,
            "interview_ready": WorkflowState.INTERVIEW_PREP_READY.value,
            "reevaluate": WorkflowState.CLAIM_REEVALUATION_REQUIRED.value,
        },
        "PROOF_IN_PROGRESS": {
            "reevaluate": WorkflowState.CLAIM_REEVALUATION_REQUIRED.value,
            "interview_ready": WorkflowState.INTERVIEW_PREP_READY.value,
        },
        "CLAIM_REEVALUATION_REQUIRED": {
            "upgrade_resume": WorkflowState.RESUME_UPGRADE_AVAILABLE.value,
            "interview_ready": WorkflowState.INTERVIEW_PREP_READY.value,
            "strengthen": WorkflowState.STRENGTHENING_REQUIRED.value,
        },
        "RESUME_UPGRADE_AVAILABLE": {"target_drafted": WorkflowState.TARGET_RESUME_DRAFT.value},
        "INTERVIEW_PREP_READY": {"start_interview": WorkflowState.INTERVIEW_IN_PROGRESS.value},
        "INTERVIEW_IN_PROGRESS": {"debrief": WorkflowState.INTERVIEW_DEBRIEF_READY.value},
        "INTERVIEW_DEBRIEF_READY": {"outcome": WorkflowState.OUTCOME.value},
    }
    # Allow idempotent re-entry for confirm events from adjacent states
    aliases = {
        ("EXPERIENCES_CONFIRMED", "confirm_experiences"): WorkflowState.EXPERIENCES_CONFIRMED.value,
        ("RESUME_STRATEGY_CONFIRMED", "confirm_strategy"): WorkflowState.RESUME_STRATEGY_CONFIRMED.value,
        ("TARGET_RESUME_CONFIRMED", "confirm_target"): WorkflowState.TARGET_RESUME_CONFIRMED.value,
        ("EXPERIENCE_SELECTION_REQUIRED", "need_selection"): WorkflowState.EXPERIENCE_SELECTION_REQUIRED.value,
        ("RESUME_STRATEGY_REQUIRED", "need_strategy"): WorkflowState.RESUME_STRATEGY_REQUIRED.value,
        ("STRESS_TEST_REQUIRED", "start_stress"): WorkflowState.STRESS_TEST_REQUIRED.value,
    }
    if (current, event) in aliases:
        _set_workflow(mission, aliases[(current, event)])
        # chain automatic follow-ups for confirm_experiences
        if event == "confirm_experiences":
            _set_workflow(mission, WorkflowState.RESUME_STRATEGY_REQUIRED)
        return
    nxt = transitions.get(current, {}).get(event)
    if not nxt:
        raise _http(409, f"当前步骤不能执行该操作（{current} / {event}）。")
    _set_workflow(mission, nxt)
    if event == "confirm_experiences":
        _set_workflow(mission, WorkflowState.RESUME_STRATEGY_REQUIRED)
    if event == "resume_bound":
        _set_workflow(mission, WorkflowState.EXPERIENCE_SELECTION_REQUIRED)


def _profile(db: Session, profile_id: UUID) -> models.UserProfile:
    profile = db.scalar(select(models.UserProfile).where(models.UserProfile.id == profile_id))
    if profile is None:
        raise _http(404, "Profile not found")
    return profile


def _mission(db: Session, mission_id: UUID) -> models.JobMission:
    mission = db.scalar(select(models.JobMission).where(models.JobMission.id == mission_id))
    if mission is None:
        raise _http(404, "Job Mission not found")
    return mission


def _mission_for_profile(db: Session, mission_id: UUID, profile_id: UUID) -> models.JobMission:
    mission = _mission(db, mission_id)
    if mission.profile_id != profile_id:
        raise _http(404, "Job Mission not found")
    return mission



def _experience_ids_for_profile(profile: models.UserProfile) -> set[UUID]:
    """Current resume-source experience ids only (not education/skills/certs)."""
    return {row.id for row in (profile.experiences or [])}


def _prune_resume_strategy(
    strategy: ResumeStrategyPayload,
    experience_ids: set[UUID],
) -> tuple[ResumeStrategyPayload, list[str]]:
    """Drop experience refs that are not in the effective current source profile.

    Returns (pruned_strategy, pruned_id_strings). Never invents replacement ids.
    """
    pruned: list[str] = []
    order = []
    for value in strategy.recommended_experience_order or []:
        if value in experience_ids:
            order.append(value)
        else:
            pruned.append(str(value))
    guidance = []
    for item in strategy.experience_guidance or []:
        exp_id = item.experience_id
        if exp_id in experience_ids:
            guidance.append(item)
        else:
            pruned.append(str(exp_id))
    # De-dupe pruned list while preserving order
    seen: set[str] = set()
    pruned_unique: list[str] = []
    for raw in pruned:
        if raw in seen:
            continue
        seen.add(raw)
        pruned_unique.append(raw)
    if not pruned_unique and order == list(strategy.recommended_experience_order or []) and len(guidance) == len(strategy.experience_guidance or []):
        return strategy, []
    return (
        strategy.model_copy(
            update={
                "recommended_experience_order": order[:20],
                "experience_guidance": guidance[:20],
            }
        ),
        pruned_unique,
    )


def _strategy_from_keep_selections(
    selections: ExperienceSelectionPayload,
    experience_ids: set[UUID],
    *,
    extraction: JobExtractionPayload,
    what_matters: WhatMattersPayload,
    positioning: str | None = None,
    profile_facts: list[dict[str, object]] | None = None,
) -> ResumeStrategyPayload | None:
    """Deterministic repair path from confirmed KEEP selections — no invented experience ids."""
    keep = [
        row
        for row in selections.selections
        if row.experience_id in experience_ids
        and str(getattr(row.decision, "value", row.decision)) in {"KEEP_AND_HIGHLIGHT", "KEEP"}
    ]
    if not keep:
        keep = [
            row for row in selections.selections
            if row.experience_id in experience_ids
            and str(getattr(row.decision, "value", row.decision)) == "DEEMPHASIZE"
        ]
    if not keep:
        return None
    facts_by_id = {str(fact.get("id")): fact for fact in (profile_facts or []) if isinstance(fact, dict)}
    caps = [c.name for c in (what_matters.core_capabilities or [])[:3]]
    guidance = []
    for row in keep:
        fact = facts_by_id.get(str(row.experience_id), {})
        detail = str(fact.get("description") or fact.get("evidence_text") or "").strip()
        highlights = [part.strip() for part in re.split(r"[。；;\n]+", detail) if part.strip()][:3]
        if not highlights:
            highlights = list(row.related_capabilities or caps)[:5]
        why = (row.why or "这段经历可用于说明与目标岗位相关的个人贡献").strip()
        guidance.append(
            {
                "experience_id": str(row.experience_id),
                "role_in_story": why[:600],
                "what_to_highlight": highlights,
                "what_to_avoid": ["不要补写原简历没有的数字、工具或结果", "不要把团队成果写成个人独立完成"],
                "target_capabilities": list(row.related_capabilities or caps)[:5],
                "evidence_refs": [str(v) for v in (row.supporting_evidence_refs or [])][:20],
                "interview_risk_notes": ["准备说明个人负责部分、采用的方法和结果证据"],
            }
        )
    company = extraction.company if extraction.company and extraction.company != "UNKNOWN" else "目标公司"
    role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"
    pos = (positioning or "").strip()
    if not pos:
        pos = (
            f"面向{company}·{role}，优先展示可核对的个人动作、方法和结果。"
        )
    return ResumeStrategyPayload.model_validate(
        {
            "positioning_statement": pos[:600],
            "recommended_experience_order": [str(row.experience_id) for row in keep][:20],
            "experience_guidance": guidance[:20],
        }
    )


def _ensure_strategy_grounded(
    strategy: ResumeStrategyPayload,
    *,
    profile: models.UserProfile,
    selections: ExperienceSelectionPayload,
    extraction: JobExtractionPayload,
    what_matters: WhatMattersPayload,
) -> ResumeStrategyPayload:
    """Intersect strategy experience refs with current source; repair or Chinese 422."""
    experience_ids = _experience_ids_for_profile(profile)
    pruned, dropped = _prune_resume_strategy(strategy, experience_ids)
    eligible_ids = {
        row.experience_id for row in selections.selections
        if str(getattr(row.decision, "value", row.decision)) != "OMIT"
    }
    pruned = pruned.model_copy(update={
        "recommended_experience_order": [eid for eid in pruned.recommended_experience_order if eid in eligible_ids],
        "experience_guidance": [item for item in pruned.experience_guidance if item.experience_id in eligible_ids],
    })
    critical_empty = not pruned.recommended_experience_order and not pruned.experience_guidance
    if critical_empty:
        repaired = _strategy_from_keep_selections(
            selections,
            experience_ids,
            extraction=extraction,
            what_matters=what_matters,
            positioning=pruned.positioning_statement,
            profile_facts=_profile_facts(profile),
        )
        if repaired is None:
            raise _http(
                422,
                "简历策略引用了当前简历来源中不存在的经历，且没有可用的已确认经历可修复。"
                "请返回经历筛选核对后，再点「重新生成策略」。",
            )
        return repaired
    if dropped and not pruned.recommended_experience_order and pruned.experience_guidance:
        # Keep guidance order when order was all ghosts
        pruned = pruned.model_copy(
            update={
                "recommended_experience_order": [item.experience_id for item in pruned.experience_guidance][:20]
            }
        )
    return pruned



def _profile_facts(profile: models.UserProfile) -> list[dict[str, object]]:
    return DefaultCareerEvidenceIntelligence.profile_facts(profile)


def source_resume_section_order(source_text: str) -> list[str]:
    """Read top-level headings in source order, retaining separate project/internship sections."""
    from .resume_sections import detect_sections

    order: list[str] = []
    for section in detect_sections(source_text):
        heading = section.heading.casefold()
        if section.key == "EDUCATION":
            key = "education"
        elif section.key == "EXPERIENCE":
            key = "project" if any(word in heading for word in ("项目", "科研", "竞赛", "project", "research")) else "experience"
        elif section.key in {"SKILLS", "LANGUAGE"}:
            key = "skills"
        elif section.key in {"CREDENTIALS", "HONORS"}:
            key = "certifications"
        elif section.key == "CAMPUS":
            key = "campus"
        else:
            continue
        if key not in order:
            order.append(key)
    return order


def _profile_evidence_ids(db: Session, profile: models.UserProfile) -> set[UUID]:
    ids = {row.id for collection in (profile.education, profile.skills, profile.experiences, profile.certifications) for row in collection}
    ids.update(row.id for row in db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.profile_id == profile.id)).all())
    return ids


def _requirement_refs(extraction: JobExtractionPayload) -> set[str]:
    return {item.id for item in [*extraction.requirements, *extraction.preferred_requirements]}


def _validate_grounding(raw_text: str, extraction: JobExtractionPayload, what_matters: WhatMattersPayload) -> WhatMattersPayload:
    """Validate requirement evidence; sanitize What Matters refs instead of hard-failing.

    Returning the (possibly sanitized) payload lets callers persist usable What Matters
    when the model cites non-requirement refs like raw_text snippets.
    """
    normalized_raw = raw_text.casefold()
    for requirement in [*extraction.requirements, *extraction.preferred_requirements]:
        if requirement.evidence_text.casefold() not in normalized_raw:
            raise _http(422, "Mission intelligence returned a JD requirement without source evidence")
    allowed = _requirement_refs(extraction)
    bad = set(what_matters.jd_evidence_refs) - allowed
    if not bad:
        return what_matters
    # Prefer keeping analysis over opaque soft-UNKNOWN shells.
    from .mission_provider import OpenAIMissionProvider

    return OpenAIMissionProvider._sanitize_what_matters_refs(what_matters, extraction)



def _is_unknown_identity(value: object) -> bool:
    if value is None:
        return True
    text = str(value).strip()
    return (not text) or text.upper() in {"UNKNOWN", "N/A", "NONE", "NULL", "-"}


def _display_name_for(company: str, role: str) -> str:
    company_u = _is_unknown_identity(company)
    role_u = _is_unknown_identity(role)
    company_s = (company or "").strip()
    role_s = (role or "").strip()
    if company_u and not role_u:
        return role_s
    if role_u and not company_u:
        return company_s
    if company_u and role_u:
        return "未识别岗位"
    return f"{company_s} · {role_s}"


def _parsed_identity(parsed: object) -> tuple[str | None, str | None]:
    data = parsed if isinstance(parsed, dict) else {}
    company = data.get("company")
    role = data.get("role")
    company_s = str(company).strip() if company is not None else None
    role_s = str(role).strip() if role is not None else None
    if company_s is not None and _is_unknown_identity(company_s):
        company_s = None
    if role_s is not None and _is_unknown_identity(role_s):
        role_s = None
    return company_s, role_s


def _hydrate_mission_identity(db: Session, mission: models.JobMission, *, persist: bool = True) -> models.JobMission:
    """Prefer real company/role/seniority/location; backfill UNKNOWN from parsed_jd / JD heuristics."""
    company = (mission.company or "").strip() or "UNKNOWN"
    role = (mission.role or "").strip() or "UNKNOWN"
    seniority = (mission.seniority or "").strip() or "UNKNOWN"
    location = (mission.location or None)
    if isinstance(location, str):
        location = location.strip() or None
    parsed = dict(mission.parsed_jd or {}) if isinstance(mission.parsed_jd, dict) else {}
    parsed_company, parsed_role = _parsed_identity(parsed)

    changed = False
    if _is_unknown_identity(company) and parsed_company:
        company = parsed_company
        changed = True
    if _is_unknown_identity(role) and parsed_role:
        role = parsed_role
        changed = True

    parsed_seniority = parsed.get("seniority")
    if _is_unknown_identity(seniority) and parsed_seniority and not _is_unknown_identity(str(parsed_seniority)):
        seniority = str(parsed_seniority).strip()
        changed = True
    parsed_location = parsed.get("location")
    if location is None and parsed_location and not _is_unknown_identity(str(parsed_location)):
        location = str(parsed_location).strip() or None
        if location:
            changed = True

    need_raw = (
        _is_unknown_identity(company)
        or _is_unknown_identity(role)
        or _is_unknown_identity(seniority)
        or location is None
    )
    raw_text = ""
    if need_raw:
        target_job = db.get(models.TargetJob, mission.target_job_id)
        raw_text = (getattr(target_job, "raw_text", None) or "") if target_job is not None else ""

    if raw_text and need_raw:
        from .mission_provider import OpenAIMissionProvider
        from .jd_identity_normalize import (
            infer_location_from_jd,
            infer_seniority_from_jd,
            normalize_location,
            normalize_seniority,
        )

        if _is_unknown_identity(company):
            inferred_company = OpenAIMissionProvider._infer_company_from_jd(raw_text)
            if inferred_company:
                company = inferred_company
                changed = True
        if _is_unknown_identity(role):
            inferred_role = OpenAIMissionProvider._infer_role_from_jd(raw_text)
            if inferred_role:
                role = inferred_role
                changed = True
        if _is_unknown_identity(seniority):
            inferred_seniority = infer_seniority_from_jd(raw_text)
            if inferred_seniority and inferred_seniority != "UNKNOWN":
                seniority = normalize_seniority(inferred_seniority)
                changed = True
        if location is None:
            inferred_location = infer_location_from_jd(raw_text)
            if inferred_location:
                location = normalize_location(inferred_location)
                if location:
                    changed = True

    display_name = _display_name_for(company, role)
    if mission.display_name != display_name:
        # Rewrite opaque UNKNOWN · UNKNOWN even when identity stays unresolved.
        if "UNKNOWN" in str(mission.display_name or "").upper() or not (mission.display_name or "").strip():
            changed = True

    if not changed and mission.display_name == display_name:
        return mission

    if _is_unknown_identity(mission.company) and not _is_unknown_identity(company):
        mission.company = company
        parsed["company"] = company
        changed = True
    if _is_unknown_identity(mission.role) and not _is_unknown_identity(role):
        mission.role = role
        parsed["role"] = role
        changed = True
    if _is_unknown_identity(mission.seniority) and not _is_unknown_identity(seniority):
        mission.seniority = seniority
        parsed["seniority"] = seniority
        changed = True
    if mission.location is None and location:
        mission.location = location
        parsed["location"] = location
        changed = True
    if mission.display_name != display_name:
        mission.display_name = display_name
        changed = True
    if changed:
        mission.parsed_jd = parsed
        mission.updated_at = datetime.now(timezone.utc)
        if persist:
            try:
                db.add(mission)
                db.commit()
                db.refresh(mission)
            except Exception:
                db.rollback()
                logger.exception("hydrate_mission_identity persist failed mission_id=%s", getattr(mission, "id", None))
    return mission


def _mission_read(row: models.JobMission) -> dict[str, object]:
    warnings: list[str] = []
    intel = row.interview_intel or []
    if not intel:
        warnings.append("company_intel_unavailable")
    company = (row.company or "").strip() or "UNKNOWN"
    role = (row.role or "").strip() or "UNKNOWN"
    parsed = row.parsed_jd or {}
    parsed_company, parsed_role = _parsed_identity(parsed)
    if _is_unknown_identity(company) and parsed_company:
        company = parsed_company
    if _is_unknown_identity(role) and parsed_role:
        role = parsed_role
    display_name = row.display_name
    if _is_unknown_identity(display_name) or "UNKNOWN" in str(display_name or "").upper():
        display_name = _display_name_for(company, role)
    elif not (display_name or "").strip():
        display_name = _display_name_for(company, role)
    if _is_unknown_identity(company) and _is_unknown_identity(role):
        warnings.append("jd_identity_unresolved")
    return {
        "id": row.id,
        "profile_id": row.profile_id,
        "target_job_id": row.target_job_id,
        "display_name": display_name,
        "company": company,
        "role": role,
        "role_family": row.role_family,
        "seniority": row.seniority,
        "location": row.location,
        "status": row.status,
        "workflow_state": getattr(row, "workflow_state", None) or WorkflowState.ROLE_UNDERSTOOD.value,
        "resume_source": getattr(row, "resume_source", None),
        "warnings": list(dict.fromkeys(warnings)),
        "parsed_jd": row.parsed_jd or {},
        "what_matters": row.what_matters or {},
        "resume_strategy": row.resume_strategy or {},
        "interview_intel": intel,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def _discard_archived_mission_for_recreate(db: Session, mission: models.JobMission, target_job: models.TargetJob) -> None:
    """Remove archived progress before recreating the same JD."""
    for claim in list(target_job.claims or []):
        db.delete(claim)
    db.delete(mission)
    db.flush()


def create_mission(db: Session, profile_id: UUID, payload: MissionCreate, provider=None) -> dict[str, object]:
    profile = _profile(db, profile_id)
    digest = content_hash(payload.raw_text)
    target_job = db.scalar(select(models.TargetJob).where(models.TargetJob.profile_id == profile_id, models.TargetJob.content_hash == digest))
    if target_job is not None:
        existing = db.scalar(select(models.JobMission).where(models.JobMission.profile_id == profile_id, models.JobMission.target_job_id == target_job.id))
        if existing is not None:
            if existing.status == MissionStatus.ARCHIVED.value:
                _discard_archived_mission_for_recreate(db, existing, target_job)
            else:
                db.rollback()
                raise _http(409, "This Job Mission already exists")
    try:
        active_provider = provider or get_mission_provider()
        service = MissionIntelligenceService(provider=active_provider, retriever=InterviewIntelRetriever())
        intel_warning = False
        jd_warning = False
        analysis_error: dict[str, object] | None = None
        try:
            extraction, what_matters, intel = service.analyze_jd(payload.raw_text)
            what_matters = _validate_grounding(payload.raw_text, extraction, what_matters)
        except Exception as analyze_exc:
            # Prefer progressive soft-fail over empty/opaque 502:
            # 1) JD-only path if available
            # 2) parse_jd alone (keep real extraction; empty what_matters)
            # 3) create mission with UNKNOWN identity (no invented requirements)
            logger.exception(
                "analyze_jd failed type=%s reason=%s",
                type(analyze_exc).__name__,
                getattr(analyze_exc, "reason", None),
            )
            analysis_error = {
                "type": type(analyze_exc).__name__,
                "reason": getattr(analyze_exc, "reason", None) or getattr(analyze_exc, "detail", None) or str(analyze_exc)[:300],
                "status_code": getattr(analyze_exc, "status_code", None),
            }
            intel = []
            intel_warning = True
            recovered = False
            if hasattr(service, "analyze_jd_without_intel"):
                try:
                    extraction, what_matters = service.analyze_jd_without_intel(payload.raw_text)
                    what_matters = _validate_grounding(payload.raw_text, extraction, what_matters)
                    recovered = True
                except Exception:
                    logger.exception("analyze_jd_without_intel also failed")
            if not recovered:
                try:
                    extraction = active_provider.parse_jd(payload.raw_text)
                    what_matters = _soft_what_matters()
                    # Grounding may fail if model invented evidence_text; drop reqs rather than 502.
                    try:
                        what_matters = _validate_grounding(payload.raw_text, extraction, what_matters)
                    except HTTPException:
                        extraction = extraction.model_copy(
                            update={"requirements": [], "preferred_requirements": []}
                        )
                    jd_warning = True
                    recovered = True
                except Exception:
                    logger.exception("parse_jd soft path failed; creating UNKNOWN shell mission")
                    extraction = _soft_jd_extraction()
                    what_matters = _soft_what_matters()
                    jd_warning = True
                    recovered = True
            if not recovered:
                raise provider_http_error(analyze_exc) from analyze_exc
        else:
            if not intel:
                intel_warning = True
        # Keep the provider call outside the write transaction. The TargetJob
        # row is inserted only after the slow request has returned.
        if target_job is None:
            target_job = models.TargetJob(profile_id=profile.id, raw_text=payload.raw_text, source_url=payload.source_url, content_hash=digest, status="CURRENT")
            db.add(target_job)
            db.flush()
        existing = db.scalar(
            select(models.JobMission).where(
                models.JobMission.profile_id == profile_id,
                models.JobMission.target_job_id == target_job.id,
                models.JobMission.status != MissionStatus.ARCHIVED.value,
            )
        )
        if existing is not None:
            db.rollback()
            raise _http(409, "This Job Mission already exists")
        target_job.requirements = [item.model_dump(mode="json") for item in extraction.requirements]
        target_job.capabilities = [{"name": value, "summary": value, "atomic_requirement_ids": []} for value in extraction.capabilities]
        company = extraction.company.strip() or "UNKNOWN"
        role = extraction.role.strip() or "UNKNOWN"
        display_name = _display_name_for(company, role)
        mission_kwargs = dict(
            profile_id=profile.id,
            target_job_id=target_job.id,
            display_name=display_name,
            company=company,
            role=role,
            role_family=extraction.role_family,
            seniority=extraction.seniority,
            location=extraction.location,
            status=MissionStatus.DRAFT.value,
            parsed_jd=extraction.model_dump(mode="json"),
            what_matters=what_matters.model_dump(mode="json"),
            interview_intel=intel or [],
        )
        # workflow_state may be absent on older ORM models before APPLY patches models.py
        try:
            mission = models.JobMission(**mission_kwargs, workflow_state=WorkflowState.ROLE_UNDERSTOOD.value, resume_source=None)
        except TypeError:
            mission = models.JobMission(**mission_kwargs)
            if hasattr(mission, "workflow_state"):
                mission.workflow_state = WorkflowState.ROLE_UNDERSTOOD.value
        db.add(mission)
        db.commit()
        db.refresh(mission)
        payload_out = _mission_read(mission)
        warnings: list[str] = list(payload_out.get("warnings") or [])
        if intel_warning or not (intel or []):
            warnings.append("company_intel_unavailable")
        if jd_warning:
            warnings.append("jd_analysis_unavailable")
        if company.upper() == "UNKNOWN" and role.upper() == "UNKNOWN":
            warnings.append("jd_identity_unresolved")
        if warnings:
            payload_out["warnings"] = list(dict.fromkeys(warnings))
        if analysis_error:
            payload_out["analysis_error"] = analysis_error
        elif jd_warning:
            payload_out["analysis_error"] = {
                "type": "partial_jd_analysis",
                "reason": "what_matters_or_intel_degraded",
                "status_code": None,
            }
        return payload_out
    except HTTPException:
        db.rollback()
        raise
    except Exception as exc:
        db.rollback()
        if isinstance(exc, (MissionProviderNotConfiguredError, MissionProviderTimeoutError, MissionProviderConnectionError, MissionProviderUpstreamError, MissionProviderInvalidResponseError)):
            raise provider_http_error(exc) from exc
        raise _http(503, "Job Mission persistence failed") from exc


def list_missions(db: Session, profile_id: UUID) -> list[dict[str, object]]:
    _profile(db, profile_id)
    rows = list(
        db.scalars(
            select(models.JobMission)
            .where(
                models.JobMission.profile_id == profile_id,
                models.JobMission.status != MissionStatus.ARCHIVED.value,
            )
            .order_by(models.JobMission.created_at, models.JobMission.id)
        ).all()
    )
    return [_mission_read(_hydrate_mission_identity(db, row)) for row in rows]


def get_mission(db: Session, mission_id: UUID) -> dict[str, object]:
    mission = _hydrate_mission_identity(db, _mission(db, mission_id))
    return _mission_read(mission)


def archive_mission(db: Session, mission_id: UUID) -> dict[str, object]:
    row = _mission(db, mission_id)
    row.status = MissionStatus.ARCHIVED.value
    row.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _mission_read(row)


def delete_mission(db: Session, mission_id: UUID) -> dict[str, object]:
    """Hard-delete a job mission (and cascaded children). Prefer archive for soft remove."""
    row = _mission(db, mission_id)
    payload = _mission_read(row)
    db.delete(row)
    db.commit()
    return {"deleted": True, "id": str(payload.get("id") or mission_id)}


def reanalyze_mission(db: Session, mission_id: UUID, payload: MissionReanalyze, provider=None) -> dict[str, object]:
    """Re-run JD LLM analysis for an existing mission (what matters + identity + intel)."""
    mission = _mission(db, mission_id)
    try:
        service = MissionIntelligenceService(provider=provider or get_mission_provider(), retriever=InterviewIntelRetriever())
        extraction, what_matters, intel = service.analyze_jd(payload.raw_text)
        what_matters = _validate_grounding(payload.raw_text, extraction, what_matters)
    except Exception as exc:
        raise provider_http_error(exc) from exc
    target_job = db.get(models.TargetJob, mission.target_job_id)
    if target_job is not None:
        target_job.raw_text = payload.raw_text
        target_job.source_url = payload.source_url
        target_job.content_hash = content_hash(payload.raw_text)
    mission.company = extraction.company.strip() or "UNKNOWN"
    mission.role = extraction.role.strip() or "UNKNOWN"
    mission.role_family = extraction.role_family
    mission.seniority = extraction.seniority
    mission.location = extraction.location
    mission.display_name = _display_name_for(mission.company, mission.role)
    mission.parsed_jd = extraction.model_dump(mode="json")
    mission.what_matters = what_matters.model_dump(mode="json")
    mission.interview_intel = intel
    if hasattr(mission, "workflow_state"):
        # Re-analyze returns user to role understanding; do not wipe later progress unless still early.
        current = _workflow_of(mission)
        if current in {WorkflowState.JD_REQUIRED.value, WorkflowState.JOB_ANALYZING.value, WorkflowState.ROLE_UNDERSTOOD.value, WorkflowState.RESUME_REQUIRED.value}:
            _set_workflow(mission, WorkflowState.ROLE_UNDERSTOOD)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def get_what_matters(db: Session, mission_id: UUID) -> dict[str, object]:
    row = _mission(db, mission_id)
    return {"mission_id": row.id, "what_matters": row.what_matters or {}, "interview_intel": row.interview_intel or []}


def update_mission_identity(db: Session, mission_id: UUID, payload: MissionIdentityUpdate) -> dict[str, object]:
    mission = _mission(db, mission_id)
    mission.company = payload.company.strip() or "UNKNOWN"
    mission.role = payload.role.strip() or "UNKNOWN"
    mission.role_family = payload.role_family.strip() or "UNKNOWN"
    mission.seniority = payload.seniority.strip() or "UNKNOWN"
    mission.location = payload.location.strip() if payload.location else None
    mission.display_name = _display_name_for(mission.company, mission.role)
    parsed = dict(mission.parsed_jd or {})
    parsed.update({"company": mission.company, "role": mission.role, "role_family": mission.role_family, "seniority": mission.seniority, "location": mission.location})
    mission.parsed_jd = parsed
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)



def _purge_mission_claims_for_profile(db: Session, mission: models.JobMission, profile_id: UUID | None) -> int:
    """Delete claims/evidence/proof tied to an old profile for this mission target job.

    Used on resume rebind/confirm so stale Master or previous mission-local claims
    cannot drive proof buttons against the newly bound profile.
    """
    if profile_id is None:
        return 0
    claims = list(
        db.scalars(
            select(models.ResumeClaim).where(
                models.ResumeClaim.target_job_id == mission.target_job_id,
                models.ResumeClaim.profile_id == profile_id,
            )
        ).all()
    )
    if not claims:
        return 0
    claim_ids = [row.id for row in claims]
    actions = list(db.scalars(select(models.ProofAction).where(models.ProofAction.claim_id.in_(claim_ids))).all())
    action_ids = [row.id for row in actions]
    if action_ids:
        for artifact in db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.action_id.in_(action_ids))).all():
            db.delete(artifact)
    for action in actions:
        db.delete(action)
    for artifact in db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.claim_id.in_(claim_ids))).all():
        db.delete(artifact)
    for session in db.scalars(select(models.InterviewSession).where(models.InterviewSession.claim_id.in_(claim_ids))).all():
        db.delete(session)
    for claim in claims:
        db.delete(claim)
    db.flush()
    return len(claims)


def _reset_resume_optimization_state(db: Session, mission: models.JobMission) -> None:
    """Invalidate derived resume decisions when the source profile changes.

    The source resume is the input to selection, strategy, target-resume bullets,
    and interview claims. Keeping any of those rows after a rebind makes the UI
    show a stale generic ranking for the newly uploaded resume.
    """
    for row in list(mission.selections or []):
        db.delete(row)
    for row in list(mission.target_resumes or []):
        db.delete(row)
    for row in list(mission.red_team_reports or []):
        db.delete(row)
    for row in list(mission.interview_packs or []):
        db.delete(row)
    mission.resume_strategy = {}
    mission.resume_source = dict(mission.resume_source or {})
    mission.resume_source["optimization_reset_at"] = datetime.now(timezone.utc).isoformat()
    db.flush()


def restart_resume_optimization(db: Session, mission_id: UUID) -> dict[str, object]:
    """Explicitly recalculate an existing mission from its bound source resume."""
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    _reset_resume_optimization_state(db, mission)
    _set_workflow(mission, WorkflowState.RESUME_SELECTED)
    mission.status = MissionStatus.RESUME_PREP.value
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    return generate_experience_selection(db, mission_id)


def _weak_proof_soft_state(*, message: str, next_action: str = "请重新生成当前岗位的主张分析") -> dict[str, object]:
    """Structured Chinese empty proof state — never an English binding exception."""
    return {
        "readiness_status": "WEAK_EVIDENCE",
        "proof_actions": [],
        "next_action": next_action,
        "message": message,
    }


def generate_claims_for_mission(db: Session, mission_id: UUID):
    """Run claim analysis against the mission-effective profile (bound local or Master).

    Mission-local uploads create a DRAFT bound profile; proof requires that profile
    to be CONFIRMED. Master remains untouched when isolation=mission_local.

    Binding mode=master trusts the shared Master archive: DRAFT Master with facts is
    promoted to CONFIRMED (same as confirm_resume_source), so proof is not a dead end.
    """
    mission = _mission(db, mission_id)
    profile = _effective_profile_for_mission(db, mission)
    src = _resume_source_dict(mission)
    mode = str(src.get("mode") or "")
    isolation = str(src.get("isolation") or "")
    master_trusted = mode == "master" or (
        isolation == "shared_master" and _bound_profile_id(mission) is None
    )
    if profile.status != "CONFIRMED":
        if master_trusted and _promote_master_confirmed_if_ready(db, profile):
            db.commit()
            db.refresh(profile)
        else:
            raise _http(
                409,
                "证明补强需要先确认个人档案。请在本页上方确认这份简历中的事实，再点「找出最危险的一项」。",
            )
    analysis = generate_claim_analysis(db, mission.target_job_id, profile_id=profile.id)
    for claim in analysis.claims:
        status = getattr(claim, "readiness_status", None)
        status_v = getattr(status, "value", status)
        if status_v in {"WEAK_EVIDENCE", "UNSUPPORTED"}:
            try:
                seed_deterministic_proof_actions(db, claim.id)
            except HTTPException:
                continue
    return analysis


def _effective_profile_id(mission: models.JobMission) -> UUID:
    return _bound_profile_id(mission) or mission.profile_id


def _looks_like_placeholder_profile(profile: models.UserProfile) -> bool:
    """True when Master/local profile looks like XX/文职 demo template, not a real resume."""
    blobs: list[str] = []
    for row in profile.experiences or []:
        for value in (
            getattr(row, "title", None),
            getattr(row, "organization", None),
            getattr(row, "description", None),
            getattr(row, "evidence_text", None),
        ):
            if isinstance(value, str) and value.strip():
                blobs.append(value.strip())
    for row in profile.education or []:
        for value in (getattr(row, "institution", None), getattr(row, "field_of_study", None)):
            if isinstance(value, str) and value.strip():
                blobs.append(value.strip())
    if not blobs:
        return True
    joined = "\n".join(blobs)
    markers = (
        "XX信息咨询",
        "XX交通",
        "XX大学",
        "某某公司",
        "可能由 AI 生成",
        "（注：部分内容可能由 AI 生成）",
        "(注：部分内容可能由 AI 生成)",
    )
    if any(m in joined for m in markers):
        return True
    has_wenzhi = any("文职助理" in b for b in blobs)
    has_xx = any(("XX信息" in b) or (b.startswith("XX") and len(b) >= 3) for b in blobs)
    return bool(has_wenzhi and has_xx)


def _promote_master_confirmed_if_ready(db: Session, profile: models.UserProfile) -> bool:
    """Master resume selection trusts the shared archive; promote DRAFT → CONFIRMED when it has facts.

    Returns True if status is (or becomes) CONFIRMED. Empty DRAFT profiles stay DRAFT so the
    in-mission confirm card can still collect facts — never invent content.
    """
    if profile.status == "CONFIRMED":
        return True
    if not any((profile.education, profile.skills, profile.experiences, profile.certifications)):
        return False
    profile.status = "CONFIRMED"
    profile.updated_at = datetime.now(timezone.utc)
    return True




def _coerce_extraction(raw: object) -> JobExtractionPayload:
    data = dict(raw or {}) if isinstance(raw, dict) else {}
    for key in ("requirements", "preferred_requirements"):
        items = data.get(key) or []
        fixed = []
        for item in items:
            if not isinstance(item, dict):
                continue
            row = dict(item)
            if not row.get("evidence_text"):
                row["evidence_text"] = row.get("text") or row.get("id") or "UNKNOWN"
            if not row.get("category"):
                row["category"] = "GENERAL"
            if not row.get("id"):
                row["id"] = str(row.get("text") or "req")[:64]
            if not row.get("text"):
                row["text"] = row["evidence_text"] or row["id"]
            fixed.append(row)
        data[key] = fixed
    for key, default in (
        ("company", "UNKNOWN"),
        ("role", "UNKNOWN"),
        ("role_family", "UNKNOWN"),
        ("seniority", "UNKNOWN"),
    ):
        if not data.get(key):
            data[key] = default
    data.setdefault("responsibilities", [])
    data.setdefault("capabilities", [])
    data.setdefault("keywords", [])
    return JobExtractionPayload.model_validate(data)



def _coerce_what_matters(raw: object) -> WhatMattersPayload:
    data = dict(raw or {}) if isinstance(raw, dict) else {}
    caps = []
    for item in data.get('core_capabilities') or []:
        if isinstance(item, str):
            caps.append({'name': item, 'why': item, 'evidence_refs': []})
        elif isinstance(item, dict):
            row = dict(item)
            row.setdefault('name', str(row.get('text') or row.get('id') or 'capability'))
            row.setdefault('why', str(row.get('why') or row['name']))
            row.setdefault('evidence_refs', [])
            caps.append({'name': row['name'], 'why': row['why'], 'evidence_refs': list(row.get('evidence_refs') or [])})
    data['core_capabilities'] = caps
    reqs = []
    for item in data.get('high_importance_requirements') or []:
        if isinstance(item, str):
            reqs.append({'text': item, 'importance': 'HIGH', 'evidence_refs': []})
        elif isinstance(item, dict):
            row = dict(item)
            text_value = str(row.get('text') or row.get('name') or row.get('id') or 'requirement')
            reqs.append({
                'text': text_value,
                'importance': row.get('importance') or 'HIGH',
                'evidence_refs': list(row.get('evidence_refs') or []),
            })
    data['high_importance_requirements'] = reqs
    data.setdefault('evidence_expected', [])
    data.setdefault('likely_success_signals', [])
    data.setdefault('bonus_capabilities', [])
    data.setdefault('potential_interview_focus', [])
    data.setdefault('jd_evidence_refs', [])
    try:
        conf = float(data.get('confidence', 0.5))
    except Exception:
        conf = 0.5
    data['confidence'] = max(0.0, min(1.0, conf))
    # Relax grounding: ensure evidence_refs subset by clearing invalid refs
    refs = set(data.get('jd_evidence_refs') or [])
    for bucket in ('core_capabilities', 'high_importance_requirements'):
        for item in data[bucket]:
            item['evidence_refs'] = [r for r in item.get('evidence_refs') or [] if r in refs]
    return WhatMattersPayload.model_validate(data)


def generate_experience_selection(db: Session, mission_id: UUID, provider=None) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    profile = _effective_profile_for_mission(db, mission)
    extraction = _coerce_extraction(mission.parsed_jd)
    what_matters = _coerce_what_matters(mission.what_matters)
    try:
        selection = (provider or get_mission_provider()).select_experiences(profile_facts=_profile_facts(profile), extraction=extraction, what_matters=what_matters)
    except Exception as exc:
        # A provider outage must not put the user back into the old manual
        # ranking flow. Return a deterministic, evidence-only AI draft so the
        # user still sees a reasoned decision for every source experience.
        logger.warning("experience selection provider unavailable; using grounded heuristic", exc_info=True)
        rows = []
        for fact in _profile_facts(profile):
            if str(fact.get("kind") or "").lower() not in {"experience", "work", "project", ""}:
                continue
            exp_id = fact.get("id") or fact.get("experience_id")
            if not exp_id:
                continue
            decision, why, highlights, confidence = OpenAIMissionProvider._heuristic_experience_decision(
                fact, extraction=extraction, what_matters=what_matters
            )
            rows.append({
                "experience_id": str(exp_id),
                "decision": decision,
                "why": _scrub_user_text(why),
                "related_capabilities": highlights[:5],
                "supporting_evidence_refs": [],
                "confidence": confidence,
            })
        selection = ExperienceSelectionPayload.model_validate({"selections": rows})
    if not selection.selections and profile.experiences:
        # Last-resort fill so FE is never stuck on empty 经历筛选 after a "successful" empty LLM pack.
        seen_label: set[tuple[str, str]] = set()
        rows = []
        for exp in profile.experiences:
            label_key = ((exp.organization or "").strip().lower(), (exp.title or "").strip().lower())
            if label_key != ("", "") and label_key in seen_label:
                continue
            if label_key != ("", ""):
                seen_label.add(label_key)
            fact = {
                "id": str(exp.id),
                "kind": "experience",
                "title": exp.title,
                "organization": exp.organization,
                "description": exp.description,
                "experience_type": exp.experience_type,
            }
            decision, why, highlights, confidence = OpenAIMissionProvider._heuristic_experience_decision(
                fact, extraction=extraction, what_matters=what_matters
            )
            rows.append({
                "experience_id": str(exp.id),
                "decision": decision,
                "why": _scrub_user_text(why),
                "related_capabilities": highlights,
                "supporting_evidence_refs": [],
                "confidence": confidence,
            })
        selection = ExperienceSelectionPayload.model_validate({"selections": rows})
    # Persist draft selections WITHOUT treating this as user confirmation.
    return _persist_experience_selection(db, mission_id, selection, user_confirmed=False)


def _scrub_user_text(value: str) -> str:
    """Strip UUIDs / evidence ids from user-visible Chinese analysis text."""
    import re as _re
    cleaned = str(value or "")
    cleaned = _re.sub(
        r"[（(]\s*(?:dogfood-req-[\w-]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*[）)]",
        "",
        cleaned,
    )
    cleaned = _re.sub(
        r"\b(?:dogfood-req-[\w-]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b",
        "",
        cleaned,
    )
    cleaned = _re.sub(r"[ \t]{2,}", " ", cleaned)
    return cleaned.strip(" ,;，；、") or "与目标岗位能力匹配，建议保留并突出"


def _persist_experience_selection(db: Session, mission_id: UUID, payload: ExperienceSelectionPayload, *, user_confirmed: bool) -> dict[str, object]:
    mission = _mission(db, mission_id)
    profile = _effective_profile_for_mission(db, mission)
    known_ids = {row.id for row in profile.experiences}
    evidence_ids = _profile_evidence_ids(db, profile)
    # Soft-filter unknown ids/refs (LLM often invents evidence UUIDs) instead of hard-failing the whole step.
    filtered = []
    seen_exp: set[UUID] = set()
    dedupe_label: set[tuple[str, str]] = set()
    exp_by_id = {row.id: row for row in profile.experiences}
    for item in payload.selections:
        if item.experience_id not in known_ids:
            continue
        if item.experience_id in seen_exp:
            continue
        seen_exp.add(item.experience_id)
        row_exp = exp_by_id.get(item.experience_id)
        label_key = (
            (getattr(row_exp, "organization", None) or "").strip().lower(),
            (getattr(row_exp, "title", None) or "").strip().lower(),
        )
        if label_key != ("", "") and label_key in dedupe_label:
            # Duplicate company/title under different experience_ids — keep first
            continue
        if label_key != ("", ""):
            dedupe_label.add(label_key)
        refs = [ref for ref in (item.supporting_evidence_refs or []) if ref in evidence_ids]
        why = _scrub_user_text(item.why)
        filtered.append(item.model_copy(update={"supporting_evidence_refs": refs, "why": why}))
    for item in filtered:
        row = db.scalar(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id, models.MissionExperienceSelection.experience_id == item.experience_id))
        if row is None:
            row = models.MissionExperienceSelection(mission_id=mission.id, profile_id=profile.id, experience_id=item.experience_id)
            db.add(row)
        row.decision = item.decision.value
        row.why = item.why
        row.related_capabilities = list(item.related_capabilities)
        row.supporting_evidence_refs = [str(value) for value in item.supporting_evidence_refs]
        row.confidence = item.confidence
        row.updated_at = datetime.now(timezone.utc)
    mission.status = MissionStatus.RESUME_PREP.value
    if user_confirmed:
        advance_workflow(mission, "confirm_experiences", user_confirmed=True)
    else:
        # LLM draft only — stay on / move to EXPERIENCE_SELECTION_REQUIRED
        if _workflow_of(mission) in {
            WorkflowState.RESUME_SELECTED.value,
            WorkflowState.RESUME_REQUIRED.value,
            WorkflowState.ROLE_UNDERSTOOD.value,
        }:
            _set_workflow(mission, WorkflowState.EXPERIENCE_SELECTION_REQUIRED)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    rows = list(db.scalars(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id).order_by(models.MissionExperienceSelection.created_at, models.MissionExperienceSelection.id)).all())
    return {"mission_id": mission.id, "selections": [_selection_read(row) for row in rows], "workflow_state": _workflow_of(mission)}


def save_experience_selection(db: Session, mission_id: UUID, payload: ExperienceSelectionPayload, *, user_confirmed: bool = False) -> dict[str, object]:
    """PUT from FE.

    Chip edits save as draft (user_confirmed=False) and stay on EXPERIENCE_SELECTION_REQUIRED.
    Primary CTA passes user_confirmed=True → EXPERIENCES_CONFIRMED → RESUME_STRATEGY_REQUIRED.
    """
    return _persist_experience_selection(db, mission_id, payload, user_confirmed=user_confirmed)


def _selection_read(row: models.MissionExperienceSelection) -> dict[str, object]:
    return {"id": row.id, "mission_id": row.mission_id, "profile_id": row.profile_id, "experience_id": row.experience_id, "decision": row.decision, "why": row.why, "related_capabilities": row.related_capabilities or [], "supporting_evidence_refs": row.supporting_evidence_refs or [], "confidence": row.confidence, "updated_at": row.updated_at}


def get_experience_selection(db: Session, mission_id: UUID) -> dict[str, object]:
    _mission(db, mission_id)
    rows = db.scalars(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission_id).order_by(models.MissionExperienceSelection.created_at, models.MissionExperienceSelection.id)).all()
    return {"mission_id": mission_id, "selections": [_selection_read(row) for row in rows]}


def generate_resume_strategy(db: Session, mission_id: UUID, provider=None) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    current = _workflow_of(mission)
    if current not in {
        WorkflowState.EXPERIENCES_CONFIRMED.value,
        WorkflowState.RESUME_STRATEGY_REQUIRED.value,
        WorkflowState.RESUME_STRATEGY_CONFIRMED.value,
        WorkflowState.TARGET_RESUME_DRAFT.value,
    }:
        # Allow if selections exist (legacy missions) but prefer explicit confirm
        selections_exist = db.scalar(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id)) is not None
        if not selections_exist:
            raise _http(409, "请先确认经历筛选，再制定简历策略。")
    profile = _effective_profile_for_mission(db, mission)
    extraction = _coerce_extraction(mission.parsed_jd)
    what_matters = _coerce_what_matters(mission.what_matters)
    selections = ExperienceSelectionPayload(selections=[
        {"experience_id": row.experience_id, "decision": row.decision, "why": row.why, "related_capabilities": row.related_capabilities or [], "supporting_evidence_refs": row.supporting_evidence_refs or [], "confidence": row.confidence}
        for row in db.scalars(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id)).all()
    ])
    if not selections.selections:
        raise _http(409, "请先确认经历筛选，再制定简历策略。")
    try:
        strategy = (provider or get_mission_provider()).build_resume_strategy(profile_facts=_profile_facts(profile), extraction=extraction, what_matters=what_matters, selections=selections)
    except Exception as exc:
        raise provider_http_error(exc) from exc
    strategy = _ensure_strategy_grounded(
        strategy,
        profile=profile,
        selections=selections,
        extraction=extraction,
        what_matters=what_matters,
    )
    mission.status = MissionStatus.RESUME_PREP.value
    mission.resume_strategy = strategy.model_dump(mode="json")
    # LLM draft only — stay on RESUME_STRATEGY_REQUIRED until user confirms
    if current in {WorkflowState.EXPERIENCES_CONFIRMED.value, WorkflowState.RESUME_STRATEGY_REQUIRED.value} or not mission.resume_strategy:
        _set_workflow(mission, WorkflowState.RESUME_STRATEGY_REQUIRED)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    return {"mission_id": mission.id, "strategy": strategy.model_dump(mode="json"), "workflow_state": _workflow_of(mission)}


def generate_target_resume(db: Session, mission_id: UUID, provider=None, *, source_resume_id: str | None = None, strategy_version: int | None = None) -> dict[str, object]:
    """Load mission context server-side and call real LLM Target Resume generation.

    FE must not re-send JD/Evidence; optional source_resume_id / strategy_version are hints only.
    """
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    current = _workflow_of(mission)
    if current not in {
        WorkflowState.RESUME_STRATEGY_CONFIRMED.value,
        WorkflowState.TARGET_RESUME_DRAFT.value,
        WorkflowState.RESUME_UPGRADE_AVAILABLE.value,
    }:
        raise _http(409, "请先确认简历策略，再生成目标简历。")
    profile = _effective_profile_for_mission(db, mission)
    existing_resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission.id).order_by(models.TargetResume.version.desc()))
    strategy_raw = mission.resume_strategy or {}
    if isinstance(strategy_raw, dict):
        strategy_raw = {k: v for k, v in strategy_raw.items() if not str(k).startswith("_")}
    strategy_payload = ResumeStrategyPayload.model_validate(strategy_raw) if strategy_raw else None
    if strategy_payload is None:
        raise _http(409, "还需要先完成本岗位的简历策略，再生成目标简历。")
    extraction = _coerce_extraction(mission.parsed_jd)
    what_matters = _coerce_what_matters(mission.what_matters)
    # Only pass experience_ids that belong to the CURRENT resume-source profile
    # (Master vs upload/paste each have their own profile ids). Stale selections
    # from a prior bind must not leak into generation.
    experience_ids = _experience_ids_for_profile(profile)
    selections = ExperienceSelectionPayload(selections=[
        {
            "experience_id": row.experience_id,
            "decision": row.decision,
            "why": row.why,
            "related_capabilities": row.related_capabilities or [],
            "supporting_evidence_refs": row.supporting_evidence_refs or [],
            "confidence": row.confidence,
        }
        for row in db.scalars(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id)).all()
        if row.experience_id in experience_ids
    ])
  
    strategy_payload = _ensure_strategy_grounded(
        strategy_payload,
        profile=profile,
        selections=selections,
        extraction=extraction,
        what_matters=what_matters,
    )
    # Persist pruned strategy so retries / FE do not keep feeding ghost ids.
    mission.resume_strategy = strategy_payload.model_dump(mode="json")
    # Raw JD from Target Job SoT (never trust FE-resent JD)
    raw_jd = ""
    try:
        target_job = db.scalar(select(models.TargetJob).where(models.TargetJob.id == mission.target_job_id))
        if target_job is not None:
            raw_jd = str(target_job.raw_text or "")
    except Exception:
        raw_jd = ""
    interview_intel = list(mission.interview_intel or [])
    version = (existing_resume.version + 1) if existing_resume else 1
    if strategy_version is not None and strategy_version > 0:
        # Hint only — strategy lives on mission; do not invent parallel versions.
        pass
    _ = source_resume_id  # selected resume comes from mission.resume_source / profile
    try:
        payload = (provider or get_mission_provider()).build_target_resume(
            profile_facts=_profile_facts(profile),
            extraction=extraction,
            strategy=strategy_payload,
            version=version,
            what_matters=what_matters,
            selections=selections,
            interview_intel=interview_intel,
            raw_jd=raw_jd,
            mission_id=str(mission.id),
        )
    except Exception as exc:
        raise provider_http_error(exc) from exc
    # experience_ids already computed above from the effective (current-source) profile
    evidence_ids = _profile_evidence_ids(db, profile)
    requirement_refs = _requirement_refs(extraction)
    # Drop bullets that cite ghost experience ids (do not invent replacements).
    grounded_bullets = [
        item
        for item in payload.bullets
        if item.source_experience_id is None or item.source_experience_id in experience_ids
    ]
    if not grounded_bullets:
        # Never leave TARGET_RESUME_DRAFT with target_resume=null (blank FE page).
        if current == WorkflowState.TARGET_RESUME_DRAFT.value and existing_resume is None:
            _set_workflow(mission, WorkflowState.RESUME_STRATEGY_CONFIRMED)
            mission.updated_at = datetime.now(timezone.utc)
            db.commit()
        raise _http(
            422,
            "目标简历引用了当前简历来源中不存在的经历。请返回经历筛选核对后，再点「重试生成」。",
        )
    # Soft-filter recommended order to known ids only
    payload = payload.model_copy(
        update={
            "bullets": grounded_bullets,
            "recommended_experience_order": [
                value for value in (payload.recommended_experience_order or []) if value in experience_ids
            ],
        }
    )

    # Soft-filter unknown evidence/jd refs rather than hard-failing a grounded draft
    cleaned_bullets = []
    for item in payload.bullets:
        ev = [ref for ref in item.evidence_refs if ref in evidence_ids]
        jd = [ref for ref in item.jd_refs if ref in requirement_refs]
        grounding = getattr(item, "grounding_status", None)
        grounding_val = grounding.value if hasattr(grounding, "value") else str(grounding or "SUPPORTED")
        synthetic_project = item.source_experience_id is None and any(
            str(flag).upper() == "SYNTHETIC_PROJECT" for flag in (item.risk_flags or [])
        )
        if synthetic_project:
            # Synthetic projects are suggestions for work the candidate may do;
            # they are never treated as completed evidence by default.
            grounding_val = "NEEDS_CONFIRMATION"
        if not ev and grounding_val == "SUPPORTED":
            grounding_val = "NEEDS_CONFIRMATION"
        cleaned_bullets.append(item.model_copy(update={
            "evidence_refs": ev,
            "jd_refs": jd,
            "grounding_status": grounding_val,
        }))
    payload = payload.model_copy(update={"bullets": cleaned_bullets})
    # Persist positioning for internal strategy/red-team only; strip writing-constraint dumps
    # so they never surface as a standalone resume Summary/摘要 section.
    _pos = (payload.positioning_statement or "").strip()
    _pos_l = _pos.lower()
    if any(tok in _pos_l for tok in ("every claim must", "do not invent", "evidence refs", "summary:")) or "摘要" in _pos:
        _pos = ""
    strategy_dump = strategy_payload.model_dump(mode="json")
    # Keep the source PDF/text section order as the source of truth. The model may
    # suggest an order, but it must not silently turn Education/Projects/Skills
    # into a different resume template.
    source_order = list((_resume_source_dict(mission).get("section_order") or []))
    generated_order = list(getattr(payload, "section_order", None) or [])
    section_order = source_order or generated_order or ["education", "experience", "project", "skills", "certifications"]
    strategy_dump["_generation"] = {
        "section_order": section_order,
        "skills": list(getattr(payload, "skills", None) or []),
        "excluded_suggestions": list(getattr(payload, "excluded_suggestions", None) or []),
        "bullet_grounding": [
            (b.grounding_status.value if hasattr(b.grounding_status, "value") else str(b.grounding_status))
            for b in payload.bullets
        ],
        "bullet_target_capabilities": [list(getattr(b, "target_capabilities", None) or []) for b in payload.bullets],
        "provider": "llm",
    }
    resume = models.TargetResume(
        mission_id=mission.id,
        version=version,
        status="DRAFT",
        positioning_statement=_pos,
        recommended_experience_order=[str(value) for value in payload.recommended_experience_order],
        strategy=strategy_dump,
    )
    db.add(resume)
    db.flush()
    default_selected_sources: set[UUID] = set()
    for index, bullet in enumerate(payload.bullets):
        # Keep generated alternatives unselected until the user reviews them.
        # Confirmation below chooses one grounded version per source
        # experience when the user has not explicitly selected one.
        final_text = bullet.final_text or bullet.suggested_text
        risk = list(bullet.risk_flags or [])
        gstat = bullet.grounding_status.value if hasattr(bullet.grounding_status, "value") else str(bullet.grounding_status)
        # Persist grounding without schema migration (encoded alongside risk_flags for export/debug)
        if not any(str(x).startswith("GROUNDING:") for x in risk):
            risk = [f"GROUNDING:{gstat}", *risk][:20]
        default_status = "SUGGESTED"
        # The first grounded rewrite for a real source experience is the
        # default choice. Alternatives start rejected; users can explicitly
        # switch by rejecting the chosen version and accepting another one.
        if bullet.source_experience_id and gstat == "SUPPORTED":
            if bullet.source_experience_id not in default_selected_sources:
                default_status = "ACCEPTED"
                default_selected_sources.add(bullet.source_experience_id)
            else:
                default_status = "REJECTED"
        db.add(models.TargetResumeBullet(
            target_resume_id=resume.id,
            source_experience_id=bullet.source_experience_id,
            original_text=bullet.original_text,
            suggested_text=bullet.suggested_text,
            final_text=final_text,
            reason=bullet.reason,
            jd_refs=list(bullet.jd_refs),
            evidence_refs=[str(value) for value in bullet.evidence_refs],
            resume_skill_refs=list(bullet.resume_skill_refs),
            risk_flags=risk,
            status=default_status,
            sort_order=index,
        ))
    mission.status = MissionStatus.RESUME_PREP.value
    _set_workflow(mission, WorkflowState.TARGET_RESUME_DRAFT)
    mission.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(resume)
        out = _resume_read(resume)
        out["workflow_state"] = _workflow_of(mission)
        return out
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Target Resume persistence failed") from exc


def _resume_read(row: models.TargetResume) -> dict[str, object]:
    strategy = dict(row.strategy or {})
    gen = strategy.get("_generation") if isinstance(strategy.get("_generation"), dict) else {}
    grounding_list = list(gen.get("bullet_grounding") or [])
    caps_list = list(gen.get("bullet_target_capabilities") or [])
    bullets_out = []
    for bullet in row.bullets:
        gstat = None
        for flag in (bullet.risk_flags or []):
            s = str(flag)
            if s.startswith("GROUNDING:"):
                gstat = s.split(":", 1)[1]
                break
        if not gstat and grounding_list:
            idx = bullet.sort_order if isinstance(bullet.sort_order, int) else len(bullets_out)
            if 0 <= idx < len(grounding_list):
                gstat = grounding_list[idx]
        caps = []
        if caps_list:
            idx = bullet.sort_order if isinstance(bullet.sort_order, int) else len(bullets_out)
            if 0 <= idx < len(caps_list) and isinstance(caps_list[idx], list):
                caps = caps_list[idx]
        bullets_out.append({
            "id": bullet.id,
            "source_experience_id": bullet.source_experience_id,
            "original_text": bullet.original_text,
            "suggested_text": bullet.suggested_text,
            "final_text": bullet.final_text,
            "reason": bullet.reason,
            "jd_refs": bullet.jd_refs or [],
            "evidence_refs": bullet.evidence_refs or [],
            "resume_skill_refs": bullet.resume_skill_refs or [],
            "risk_flags": [f for f in (bullet.risk_flags or []) if not str(f).startswith("GROUNDING:")],
            "status": bullet.status,
            "sort_order": bullet.sort_order,
            "grounding_status": gstat or "SUPPORTED",
            "target_capabilities": caps,
        })
    return {
        "id": row.id,
        "mission_id": row.mission_id,
        "version": row.version,
        "status": row.status,
        "positioning_statement": row.positioning_statement,
        "recommended_experience_order": row.recommended_experience_order or [],
        "strategy": strategy,
        "section_order": list(gen.get("section_order") or []),
        "skills": list(gen.get("skills") or []),
        "excluded_suggestions": list(gen.get("excluded_suggestions") or []),
        "bullets": bullets_out,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
    }


def list_target_resumes(db: Session, mission_id: UUID) -> list[dict[str, object]]:
    _mission(db, mission_id)
    return [_resume_read(row) for row in db.scalars(select(models.TargetResume).where(models.TargetResume.mission_id == mission_id).order_by(models.TargetResume.version, models.TargetResume.id)).all()]


def update_resume_bullet(db: Session, bullet_id: UUID, payload: TargetResumeBulletUpdate) -> dict[str, object]:
    bullet = db.scalar(select(models.TargetResumeBullet).where(models.TargetResumeBullet.id == bullet_id))
    if bullet is None:
        raise _http(404, "Target Resume bullet not found")
    if payload.status is not None:
        bullet.status = payload.status.value
        # A source experience may have several alternative rewrites, but the
        # final resume can contain only one accepted wording for that
        # experience.  Make the choice atomic at the API boundary so direct
        # clients and the web UI share the same invariant.
        if payload.status.value in {"ACCEPTED", "EDITED"} and bullet.source_experience_id:
            siblings = db.scalars(
                select(models.TargetResumeBullet).where(
                    models.TargetResumeBullet.target_resume_id == bullet.target_resume_id,
                    models.TargetResumeBullet.source_experience_id == bullet.source_experience_id,
                    models.TargetResumeBullet.id != bullet.id,
                )
            ).all()
            for sibling in siblings:
                if sibling.status != "REJECTED":
                    sibling.status = "REJECTED"
                    sibling.updated_at = datetime.now(timezone.utc)
    if payload.final_text is not None:
        bullet.final_text = payload.final_text
        if payload.status is None:
            bullet.status = "EDITED"
    if payload.fact_confirmed is True:
        flags = [str(value) for value in (bullet.risk_flags or []) if str(value).upper() != "FACT_CONFIRMED"]
        bullet.risk_flags = ["FACT_CONFIRMED", *flags][:20]
        if payload.status is None:
            bullet.status = "ACCEPTED"
    elif payload.fact_confirmed is False:
        bullet.risk_flags = [str(value) for value in (bullet.risk_flags or []) if str(value).upper() != "FACT_CONFIRMED"]
        if bullet.status == "ACCEPTED" and any(str(value).upper() in {"SYNTHETIC_PROJECT", "GROUNDING:NEEDS_CONFIRMATION"} for value in (bullet.risk_flags or [])):
            bullet.status = "SUGGESTED"
    # Editing a rewrite is also a user choice. Enforce the same invariant for
    # PATCH calls that omit an explicit status (for example final_text-only or
    # fact_confirmed-only updates), not only for the Accept button payload.
    if bullet.status in {"ACCEPTED", "EDITED"} and bullet.source_experience_id:
        siblings = db.scalars(
            select(models.TargetResumeBullet).where(
                models.TargetResumeBullet.target_resume_id == bullet.target_resume_id,
                models.TargetResumeBullet.source_experience_id == bullet.source_experience_id,
                models.TargetResumeBullet.id != bullet.id,
            )
        ).all()
        for sibling in siblings:
            if sibling.status != "REJECTED":
                sibling.status = "REJECTED"
                sibling.updated_at = datetime.now(timezone.utc)
    bullet.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(bullet)
    return {
        "id": bullet.id,
        "target_resume_id": bullet.target_resume_id,
        "status": bullet.status,
        "final_text": bullet.final_text,
        "suggested_text": bullet.suggested_text,
        "fact_confirmed": any(str(value).upper() == "FACT_CONFIRMED" for value in (bullet.risk_flags or [])),
        "risk_flags": list(bullet.risk_flags or []),
    }



def _uuid_only_refs(values: object) -> list[str]:
    from uuid import UUID

    out: list[str] = []
    if not isinstance(values, list):
        return out
    for value in values:
        try:
            out.append(str(UUID(str(value))))
        except Exception:
            continue
    return out


def _target_resume_payload_from_row(resume: models.TargetResume) -> TargetResumePayload:
    bullets = []
    for bullet in resume.bullets:
        bullets.append({
            "source_experience_id": bullet.source_experience_id,
            "original_text": bullet.original_text,
            "suggested_text": bullet.final_text or bullet.suggested_text,
            "final_text": bullet.final_text,
            "reason": bullet.reason,
            "jd_refs": list(bullet.jd_refs or []),
            "evidence_refs": _uuid_only_refs(bullet.evidence_refs or []),
            "resume_skill_refs": list(bullet.resume_skill_refs or []),
            "risk_flags": list(bullet.risk_flags or []),
        })
    positioning = (resume.positioning_statement or "").strip()
    if not positioning:
        # Dogfood scrub may clear Summary/positioning; red-team schema still requires min_length=1.
        positioning = "（未填写定位）"
    return TargetResumePayload.model_validate({
        "positioning_statement": positioning,
        "recommended_experience_order": resume.recommended_experience_order or [],
        "bullets": bullets,
    })

def generate_red_team(db: Session, mission_id: UUID, provider=None) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    current = _workflow_of(mission)
    if current not in {
        WorkflowState.TARGET_RESUME_CONFIRMED.value,
        WorkflowState.STRESS_TEST_REQUIRED.value,
        WorkflowState.STRENGTHENING_REQUIRED.value,
    }:
        raise _http(409, "请先确认目标简历，再做压力测试。")
    profile = _effective_profile_for_mission(db, mission)
    resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission.id).order_by(models.TargetResume.version.desc()))
    if resume is None:
        raise _http(409, "请先生成并确认目标简历，再做压力测试。")
    extraction = _coerce_extraction(mission.parsed_jd)
    what = _coerce_what_matters(mission.what_matters)
    target = _target_resume_payload_from_row(resume)
    try:
        report = (provider or get_mission_provider()).red_team(profile_facts=_profile_facts(profile), extraction=extraction, what_matters=what, target_resume=target)
    except Exception as exc:
        raise provider_http_error(exc) from exc
    row = models.RedTeamReport(mission_id=mission.id, target_resume_id=resume.id, findings=[item.model_dump(mode="json") for item in report.findings])
    db.add(row)
    mission.status = MissionStatus.STRENGTHENING.value
    _set_workflow(mission, WorkflowState.STRESS_TEST_REQUIRED)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    out = _red_team_read(row)
    out["workflow_state"] = _workflow_of(mission)
    return out


def _red_team_read(row: models.RedTeamReport) -> dict[str, object]:
    return {"id": row.id, "mission_id": row.mission_id, "target_resume_id": row.target_resume_id, "findings": row.findings or [], "created_at": row.created_at}


def get_red_team(db: Session, mission_id: UUID) -> dict[str, object]:
    _mission(db, mission_id)
    row = db.scalar(select(models.RedTeamReport).where(models.RedTeamReport.mission_id == mission_id).order_by(models.RedTeamReport.created_at.desc(), models.RedTeamReport.id.desc()))
    return _red_team_read(row) if row else {"mission_id": mission_id, "findings": []}


def generate_interview_pack(db: Session, mission_id: UUID, provider=None) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    current = _workflow_of(mission)
    resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission.id).order_by(models.TargetResume.version.desc()))
    report = db.scalar(select(models.RedTeamReport).where(models.RedTeamReport.mission_id == mission.id).order_by(models.RedTeamReport.created_at.desc(), models.RedTeamReport.id.desc()))
    if resume is None or resume.status != "CONFIRMED":
        raise _http(409, "请先确认优化后的简历，再生成面试问题。")
    if current not in {
        WorkflowState.INTERVIEW_PREP_READY.value,
        WorkflowState.INTERVIEW_IN_PROGRESS.value,
        WorkflowState.STRESS_TEST_REQUIRED.value,
        WorkflowState.TARGET_RESUME_CONFIRMED.value,
        WorkflowState.STRENGTHENING_REQUIRED.value,
        WorkflowState.PROOF_IN_PROGRESS.value,
        WorkflowState.CLAIM_REEVALUATION_REQUIRED.value,
        WorkflowState.RESUME_UPGRADE_AVAILABLE.value,
    }:
        raise _http(409, "请先确认优化后的简历，再生成面试问题。")
    extraction = _coerce_extraction(mission.parsed_jd)
    what = _coerce_what_matters(mission.what_matters)
    target = _target_resume_payload_from_row(resume)
    red = RedTeamPayload.model_validate({"findings": report.findings if report else []})
    version_row = db.scalar(select(models.InterviewPack).where(models.InterviewPack.mission_id == mission.id).order_by(models.InterviewPack.version.desc()))
    version = version_row.version + 1 if version_row else 1
    try:
        pack = (provider or get_mission_provider()).build_interview_pack(extraction=extraction, what_matters=what, interview_intel=mission.interview_intel or [], target_resume=target, red_team=red)
    except Exception:
        # Soft-fail: keep Mission interview tab usable with heuristic topics when LLM/upstream fails.
        from .mission_provider import OpenAIMissionProvider
        pack = OpenAIMissionProvider._interview_pack_fallback(
            extraction=extraction,
            what_matters=what,
            interview_intel=mission.interview_intel or [],
            target_resume=target,
            red_team=red,
        )
        enriched = OpenAIMissionProvider._enrich_interview_topics(
            list(pack.topics or []),
            extraction=extraction,
            what_matters=what,
            interview_intel=mission.interview_intel or [],
        )
        pack = InterviewPackPayload.model_validate({"topics": enriched[:12]})
    row = models.InterviewPack(mission_id=mission.id, version=version, topics=[item.model_dump(mode="json") for item in pack.topics])
    db.add(row)
    mission.status = MissionStatus.INTERVIEW_PREP.value
    _set_workflow(mission, WorkflowState.INTERVIEW_PREP_READY)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    out = _interview_pack_read(row)
    out["workflow_state"] = _workflow_of(mission)
    return out


def _interview_pack_read(row: models.InterviewPack) -> dict[str, object]:
    topics = []
    for raw in (row.topics or []):
        if not isinstance(raw, dict):
            continue
        item = dict(raw)
        topic = _scrub_user_text(str(item.get("topic") or "").strip()) if str(item.get("topic") or "").strip() else ""
        if not topic:
            # keep original if scrub emptied a non-uuid topic
            topic = str(item.get("topic") or "").strip()
        if not topic:
            continue
        patterns = [str(x).strip() for x in (item.get("question_patterns") or []) if str(x).strip()]
        for key in ("question", "questions", "sample_questions"):
            extra = item.get(key)
            if isinstance(extra, str) and extra.strip():
                patterns.append(extra.strip())
            elif isinstance(extra, list):
                patterns.extend(str(x).strip() for x in extra if str(x).strip())
        patterns = [p for p in dict.fromkeys(patterns) if p]
        if not patterns or all("哪个近期项目最能证明你的" in p for p in patterns):
            patterns = [
                f"结合目标岗位，用一段可核对经历说明你如何体现「{topic}」。",
                f"「{topic}」中你的个人决策与团队贡献分别是什么？结果怎样验证？",
            ]
        evidence = [str(x).strip() for x in (item.get("evidence_expected") or []) if str(x).strip()]
        for key in ("knowledge_to_study", "knowledge", "study_points"):
            extra = item.get(key)
            if isinstance(extra, str) and extra.strip():
                evidence.append(extra.strip())
            elif isinstance(extra, list):
                evidence.extend(str(x).strip() for x in extra if str(x).strip())
        evidence = [e for e in dict.fromkeys(evidence) if e]
        evidence = [e for e in evidence if e and "待补充" not in e]
        if not evidence or len(evidence) < 2:
            evidence = [
                f"高频问法：围绕「{topic}」的场景题/追问（优先牛客/该公司面经）",
                f"概念准备：能用自己的话解释「{topic}」与岗位职责的对应关系",
                "证据方向：从目标简历挑 1 条可核对经历，按背景-行动-结果讲清个人贡献",
            ]
        item["topic"] = topic
        item["why"] = _scrub_user_text(str(item.get("why") or "")) or f"面试官很可能围绕「{topic}」追问可验证细节。"
        item["question_patterns"] = patterns[:20]
        item["evidence_expected"] = evidence[:20]
        # FE aliases
        item["question"] = patterns[0]
        item["knowledge_to_study"] = evidence
        topics.append(item)
    return {"id": row.id, "mission_id": row.mission_id, "version": row.version, "topics": topics, "created_at": row.created_at}


def get_interview_pack(db: Session, mission_id: UUID) -> dict[str, object]:
    _mission(db, mission_id)
    row = db.scalar(select(models.InterviewPack).where(models.InterviewPack.mission_id == mission_id).order_by(models.InterviewPack.version.desc()))
    return _interview_pack_read(row) if row else {"mission_id": mission_id, "topics": []}


def proof_snapshot(db: Session, mission_id: UUID) -> dict[str, object]:
    """Return the proof UI shape scoped to one Job Mission.

    The legacy profile route follows the newest target job. This adapter first
    resolves the mission target job so opening Mock Interview from Mission A
    cannot accidentally read Mission B after another JD is created.
    """
    mission = _mission(db, mission_id)
    target_job = db.scalar(select(models.TargetJob).where(models.TargetJob.id == mission.target_job_id))
    if target_job is None:
        raise _http(404, "Mission target job not found")
    effective_pid = _effective_profile_id(mission)
    claims = list(db.scalars(
        select(models.ResumeClaim)
        .where(models.ResumeClaim.target_job_id == target_job.id, models.ResumeClaim.profile_id == effective_pid)
        .order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)
    ).all())
    claim = claims[0] if claims else None
    sessions = []
    actions = []
    if claim is not None:
        try:
            sessions = list_interview_sessions(db, claim.id)
        except HTTPException as exc:
            # Mission-local bind mismatch or stale fingerprint: surface claims without crashing strengthen UI.
            if exc.status_code not in {404, 409}:
                raise
            sessions = []
        if sessions and getattr(sessions[0].status, "value", sessions[0].status) == "COMPLETED":
            try:
                actions = list_proof_actions(db, claim.id)
            except HTTPException as exc:
                if exc.status_code not in {404, 409}:
                    raise
                actions = []
    analysis = None
    if claims:
        try:
            analysis = get_claim_analysis(db, target_job.id)
        except HTTPException as exc:
            # 404/409: still expose existing claims so Mission「开始模拟面试」can enter interview
            if exc.status_code in {404, 409}:
                analysis = _analysis_read(target_job, claims)
            else:
                raise
    target_job_payload = _target_job_read(target_job).model_dump(mode="json")
    return {
        "targetJobs": [target_job_payload],
        "targetJob": target_job_payload,
        "analysis": analysis.model_dump(mode="json") if analysis else None,
        "claim": _claim_read(claim).model_dump(mode="json") if claim else None,
        "sessions": [item.model_dump(mode="json") for item in sessions],
        "session": sessions[0].model_dump(mode="json") if sessions else None,
        "latest_completed_session": next((item.model_dump(mode="json") for item in sessions if item.status.value == "COMPLETED"), None),
        "actions": [item.model_dump(mode="json") for item in actions],
    }


def proof_state(db: Session, mission_id: UUID) -> dict[str, object]:
    mission = _mission(db, mission_id)
    effective_pid = _effective_profile_id(mission)
    claims = list(db.scalars(select(models.ResumeClaim).where(models.ResumeClaim.target_job_id == mission.target_job_id, models.ResumeClaim.profile_id == effective_pid).order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)).all())
    for claim in claims:
        if claim.readiness_status in {"WEAK_EVIDENCE", "UNSUPPORTED"}:
            try:
                seed_deterministic_proof_actions(db, claim.id)
            except HTTPException:
                continue
    claim_ids = [claim.id for claim in claims]
    actions = list(db.scalars(select(models.ProofAction).where(models.ProofAction.claim_id.in_(claim_ids))).all()) if claim_ids else []
    artifacts = list(db.scalars(select(models.ProofArtifact).where(models.ProofArtifact.claim_id.in_(claim_ids))).all()) if claim_ids else []
    return {
        "mission_id": mission.id,
        "claims": [{"id": row.id, "claim": row.claim, "readiness_status": row.readiness_status, "confidence": row.confidence, "evidence_refs": row.evidence_refs or [], "matched_capabilities": row.matched_capabilities or [], "risk_reason": row.risk_reason} for row in claims],
        "proof_actions": [{"id": row.id, "claim_id": row.claim_id, "title": row.title, "target_capability": row.target_capability, "existing_project_reference": row.existing_project_reference, "status": row.status, "definition_of_done": row.definition_of_done, "expected_evidence": row.expected_evidence, "artifact_type": row.artifact_type} for row in actions],
        "proof_artifacts": [{"id": row.id, "action_id": row.action_id, "claim_id": row.claim_id, "artifact_type": row.artifact_type, "manually_confirmed": row.manually_confirmed, "verified_fields": row.verified_fields or []} for row in artifacts],
    }


def recover_existing_evidence(db: Session, mission_id: UUID, payload: RecoverEvidenceCreate) -> dict[str, object]:
    mission = _mission(db, mission_id)
    claim = db.scalar(select(models.ResumeClaim).where(models.ResumeClaim.id == payload.claim_id, models.ResumeClaim.target_job_id == mission.target_job_id, models.ResumeClaim.profile_id == _effective_profile_id(mission)))
    if claim is None:
        raise _http(404, "该主张不属于当前任务，或未绑定到本岗位档案。请重新生成当前岗位的主张分析。")
    if not payload.confirmed:
        return {"next": "PROOF_SPRINT", "reason": "未确认已有证据；请开始一次有边界的补强冲刺。", "readiness_status": "WEAK_EVIDENCE", "proof_actions": []}
    evidence_text = (payload.evidence_text or payload.artifact_text or "").strip()
    if not evidence_text:
        raise _http(422, "确认已有证据时需要填写证据说明或材料内容")
    normalized_evidence = evidence_text.casefold()
    obvious_test_markers = (
        "审计测试",
        "测试文字",
        "audit test",
        "test evidence",
        "lorem ipsum",
        "foo bar",
    )
    if len(evidence_text) < 8 or any(marker in normalized_evidence for marker in obvious_test_markers):
        raise _http(422, "这段内容看起来像测试或占位文字，请填写可核对的真实事实、材料或结果。")
    action = db.scalar(select(models.ProofAction).where(models.ProofAction.claim_id == claim.id).order_by(models.ProofAction.created_at, models.ProofAction.id))
    if action is None:
        action = models.ProofAction(profile_id=_effective_profile_id(mission), claim_id=claim.id, mission_id=mission.id, title="Record confirmed existing evidence", why_now="A Red Team finding needs an existing evidence surface.", target_claim=claim.claim, target_gap="EVIDENCE_GAP", estimated_hours=0.5, artifact_type=payload.artifact_type, definition_of_done="The confirmed evidence is recorded and reviewable.", expected_evidence="User confirmed evidence note or artifact.", target_capability=payload.target_capability, existing_project_reference=payload.existing_project_reference, status="COMPLETED")
        db.add(action)
        db.flush()
    artifact = models.ProofArtifact(profile_id=_effective_profile_id(mission), claim_id=claim.id, action_id=action.id, artifact_type="USER_CONFIRMED", artifact_text=evidence_text, manually_confirmed=True, verified_fields=["USER_CONFIRMED"])
    db.add(artifact)
    before = claim.readiness_status
    claim.readiness_status = {
        "WEAK_EVIDENCE": "DEFENDABLE",
        "UNSUPPORTED": "WEAK_EVIDENCE",
    }.get(before, before)
    claim.evidence_refs = sanitize_evidence_refs([*(claim.evidence_refs or []), str(artifact.id)])
    claim.risk_reason = "User confirmed an existing evidence surface; add a document or artifact before relying on it in an interview."
    ready_states = {
        WorkflowState.INTERVIEW_PREP_READY.value,
        WorkflowState.INTERVIEW_IN_PROGRESS.value,
        WorkflowState.INTERVIEW_DEBRIEF_READY.value,
        WorkflowState.OUTCOME.value,
    }
    if mission.status not in {MissionStatus.APPLIED.value, MissionStatus.INTERVIEWING.value, MissionStatus.COMPLETED.value} and _workflow_of(mission) not in ready_states:
        mission.status = MissionStatus.STRENGTHENING.value
    mission.updated_at = datetime.now(timezone.utc)
    try:
        db.commit()
        db.refresh(artifact)
    except SQLAlchemyError as exc:
        db.rollback()
        raise _http(503, "Existing evidence persistence failed") from exc
    return {"next": "RE_EVALUATE", "claim_id": claim.id, "before_readiness": before, "after_readiness": claim.readiness_status, "artifact_id": artifact.id, "message": "已记录为用户确认的现有证据；建议再补充文档或材料以继续加强。"}


def create_mission_proof_actions(db: Session, mission_id: UUID, claim_id: UUID | None = None):
    """Create proof actions for the mission-effective profile.

    Regenerates claim analysis when the current mission has no claims bound to
    resume_source.bound_profile_id. Never surfaces English profile-binding errors.
    """
    mission = _mission(db, mission_id)
    effective_pid = _effective_profile_id(mission)

    def _load_claim():
        return db.scalar(
            select(models.ResumeClaim)
            .where(
                models.ResumeClaim.target_job_id == mission.target_job_id,
                models.ResumeClaim.profile_id == effective_pid,
                *([models.ResumeClaim.id == claim_id] if claim_id else []),
            )
            .order_by(models.ResumeClaim.sort_order, models.ResumeClaim.id)
        )

    claim = _load_claim()
    if claim is None:
        # Strengthen buttons must regenerate Claim Analysis for CURRENT mission profile.
        try:
            generate_claims_for_mission(db, mission_id)
        except HTTPException as exc:
            detail = str(exc.detail or "")
            return _weak_proof_soft_state(
                message=detail if any("\u4e00" <= ch <= "\u9fff" for ch in detail) else "当前任务没有可绑定的主张，请重新生成当前岗位的主张分析。",
            )
        claim = _load_claim()
    if claim is None:
        return _weak_proof_soft_state(
            message="当前任务没有绑定到本岗位档案的主张，请重新生成当前岗位的主张分析。",
        )
    try:
        return generate_proof_actions(db, claim.id)
    except HTTPException as exc:
        detail = str(exc.detail or "")
        # Prefer deterministic executable actions over an empty soft wall.
        if exc.status_code in {409, 422}:
            try:
                seeded = seed_deterministic_proof_actions(db, claim.id)
                if seeded:
                    return seeded
            except HTTPException:
                pass
            chinese = any("一" <= ch <= "鿿" for ch in detail)
            return _weak_proof_soft_state(
                message=detail if chinese else "当前无法生成可执行补强动作，请重新生成当前岗位的主张分析后重试。",
                next_action="请重新生成当前岗位的主张分析" if (not chinese or "主张" in detail or "档案" in detail) else detail,
            )
        raise


def mission_re_evaluate(db: Session, mission_id: UUID, claim_id: UUID):
    mission = _mission(db, mission_id)
    claim = db.scalar(select(models.ResumeClaim).where(models.ResumeClaim.id == claim_id, models.ResumeClaim.target_job_id == mission.target_job_id))
    if claim is None:
        raise _http(404, "Resume claim is not part of this Mission")
    return reevaluate_claim(db, claim.id)


def add_mission_outcome(db: Session, mission_id: UUID, payload: MissionOutcomeCreate) -> dict[str, object]:
    mission = _mission(db, mission_id)
    prior_status = mission.status
    prior_workflow = mission.workflow_state
    round_ok = bool((payload.interview_round or "").strip())
    questions_ok = any(str(q or "").strip() for q in (payload.questions_asked or []))
    struggle_ok = bool((payload.where_struggled or "").strip())
    feedback_ok = bool((payload.interviewer_feedback or "").strip())
    if not (round_ok or questions_ok or struggle_ok or feedback_ok):
        # Do not persist outcome or advance status / workflow_state on empty debrief.
        raise _http(422, "请至少填写面试轮次、被问到的问题、卡点或面试官反馈中的一项后再保存。")
    _ = (prior_status, prior_workflow)
    row = models.InterviewOutcome(mission_id=mission.id, application_status=payload.application_status, interview_round=payload.interview_round, questions_asked=list(payload.questions_asked), where_struggled=payload.where_struggled, interviewer_feedback=payload.interviewer_feedback, notes=payload.notes, confirmed_for_intel=payload.confirmed_for_intel)
    db.add(row)
    mission.status = MissionStatus.COMPLETED.value if payload.application_status.casefold() in {"rejected", "accepted", "withdrawn", "completed"} else MissionStatus.INTERVIEWING.value
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(row)
    return _outcome_read(row)


def _outcome_read(row: models.InterviewOutcome) -> dict[str, object]:
    return {"id": row.id, "mission_id": row.mission_id, "application_status": row.application_status, "interview_round": row.interview_round, "questions_asked": row.questions_asked or [], "where_struggled": row.where_struggled, "interviewer_feedback": row.interviewer_feedback, "notes": row.notes, "confirmed_for_intel": row.confirmed_for_intel, "created_at": row.created_at}


def get_readiness(db: Session, mission_id: UUID) -> dict[str, object]:
    mission = _mission(db, mission_id)
    claims = list(db.scalars(select(models.ResumeClaim).where(models.ResumeClaim.target_job_id == mission.target_job_id)).all())
    resumes = list(db.scalars(select(models.TargetResume).where(models.TargetResume.mission_id == mission.id)).all())
    latest_report = db.scalar(select(models.RedTeamReport).where(models.RedTeamReport.mission_id == mission.id).order_by(models.RedTeamReport.created_at.desc(), models.RedTeamReport.id.desc()))
    blocks: list[str] = []
    if not resumes:
        blocks.append("Create a Target Resume")
    weak = [row for row in claims if row.readiness_status in {"WEAK_EVIDENCE", "UNSUPPORTED"}]
    if weak:
        blocks.append(f"Strengthen {len(weak)} claim(s) before relying on them in an interview")
    high_risk = [item for item in (latest_report.findings if latest_report else []) if str(item.get("risk_level", "")).upper() == "HIGH"]
    if high_risk:
        blocks.append(f"Resolve {len(high_risk)} high-risk Red Team finding(s)")
    if not mission.interview_packs:
        blocks.append("Build the company-specific Interview Pack")
    if not blocks:
        status = "READY_TO_APPLY"
        why = "The current Mission has a target resume, defendable claims, and no unresolved high-risk findings."
        what = ["Keep evidence and interview answers synchronized."]
    elif weak or high_risk:
        status = "STRENGTHEN_FIRST"
        why = "The current evidence or Red Team review still exposes interview risk."
        what = ["Recover existing evidence or complete the smallest artifactable Proof Sprint."]
    else:
        status = "INSUFFICIENT_EVIDENCE"
        why = "The Mission has not completed its preparation chain."
        what = ["Complete the missing preparation steps before applying."]
    return {"mission_id": mission.id, "status": status, "why": why, "blocks": blocks, "what_would_change": what, "advice_only": True}



def confirm_resume_source(db: Session, mission_id: UUID, payload: ConfirmResumeSource) -> dict[str, object]:
    """Bind resume source for a mission.

    - mode=master: use shared Master Profile (mission.profile_id); clear any mission-local bind.
    - mode=upload|paste with update_master=False: require prior mission-local bind
      (bound_profile_id already on resume_source from bind_mission_resume_from_extraction),
      or reject silent master overwrite.
    - mode=upload|paste with update_master=True: allowed only after explicit caller intent;
      this path does not itself ingest bytes — use bind_mission_resume_from_extraction.
    """
    mission = _mission(db, mission_id)
    now = datetime.now(timezone.utc).isoformat()
    existing = _resume_source_dict(mission)
    previous_bound_raw = existing.get("bound_profile_id")
    try:
        previous_bound_id = UUID(str(previous_bound_raw)) if previous_bound_raw else None
    except (TypeError, ValueError):
        previous_bound_id = None
    if payload.mode == ResumeSourceMode.master:
        # Product: selecting Master trusts the shared archive — promote DRAFT→CONFIRMED
        # when facts exist so 补强 is not blocked without a confirm CTA on Master path.
        master = _profile(db, mission.profile_id)
        if _looks_like_placeholder_profile(master):
            raise _http(
                409,
                "当前 Master 档案看起来是占位模板（如 XX 公司 / 文职助理），不是可用的真实简历。"
                "请改用「上传 PDF」或「粘贴文本」绑定本岗位专用简历后再继续。",
            )
        _promote_master_confirmed_if_ready(db, master)
        mission.resume_source = {
            "mode": "master",
            "bound_at": now,
            "isolation": "shared_master",
            "master_profile_id": str(mission.profile_id),
        }
    else:
        bound = existing.get("bound_profile_id")
        isolation = str(existing.get("isolation") or "")
        if payload.update_master:
            # Explicit Master update must have already written Master via bind_...(update_master=True).
            mission.resume_source = {
                **{k: v for k, v in existing.items() if k not in {"bound_profile_id"}},
                "mode": payload.mode.value,
                "bound_at": now,
                "isolation": "shared_master",
                "updated_master": True,
                "master_profile_id": str(mission.profile_id),
            }
            mission.resume_source.pop("bound_profile_id", None)
        elif isolation == "mission_local" and bound:
            mission.resume_source = {
                **existing,
                "mode": payload.mode.value,
                "bound_at": now,
                "isolation": "mission_local",
                "bound_profile_id": str(bound),
                "master_profile_id": str(existing.get("master_profile_id") or mission.profile_id),
            }
        else:
            raise _http(
                409,
                "上传/粘贴的简历需先走本岗位绑定（不会静默覆盖 Master）。请重新选择文件或文本后再确认。",
            )
    # Drop claims/proof from the previous effective profile when rebinding.
    new_src = _resume_source_dict(mission)
    new_bound_raw = new_src.get("bound_profile_id")
    try:
        new_bound_id = UUID(str(new_bound_raw)) if new_bound_raw else None
    except (TypeError, ValueError):
        new_bound_id = None
    new_effective = new_bound_id or mission.profile_id
    if previous_bound_id and previous_bound_id != new_effective:
        _purge_mission_claims_for_profile(db, mission, previous_bound_id)
    # Also clear Master-profile claims on this target job when switching onto a mission-local bind.
    if new_bound_id and mission.profile_id != new_bound_id:
        _purge_mission_claims_for_profile(db, mission, mission.profile_id)

    # A source-mode switch also invalidates the derived optimization draft. The
    # next resume visit must ask the model about the currently bound profile.
    if previous_bound_id != new_effective or str(existing.get("mode") or "") != payload.mode.value:
        _reset_resume_optimization_state(db, mission)

    mission.status = MissionStatus.RESUME_PREP.value
    _set_workflow(mission, WorkflowState.RESUME_SELECTED)
    advance_workflow(mission, "need_selection", user_confirmed=True)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def bind_mission_resume_from_extraction(
    db: Session,
    mission_id: UUID,
    extraction: ResumeExtractionResult,
    *,
    mode: str,
    update_master: bool = False,
    filename: str | None = None,
    content_hash_value: str | None = None,
    source_section_order: list[str] | None = None,
) -> dict[str, object]:
    """Ingest upload/paste for a mission with copy-on-write by default.

    Default (update_master=False): create a new draft profile from extraction and store
    its id on mission.resume_source.bound_profile_id. Shared Master Profile is untouched.

    Explicit update_master=True: replace Master Profile contents (affects other missions
    that still use Master / shared isolation).
    """
    from .mission_schemas import ResumeSourceMode as _RSM

    if mode not in {_RSM.upload.value, _RSM.paste.value}:
        raise _http(422, "本接口仅支持 upload 或 paste 模式")
    mission = _mission(db, mission_id)
    previous_src = _resume_source_dict(mission)
    previous_bound_raw = previous_src.get("bound_profile_id")
    try:
        previous_bound_id = UUID(str(previous_bound_raw)) if previous_bound_raw else None
    except (TypeError, ValueError):
        previous_bound_id = None
    now = datetime.now(timezone.utc).isoformat()
    master_id = mission.profile_id
    affected = [
        row
        for row in list_missions_sharing_master(db, master_id)
        if row.get("affected_by_master_update") and str(row.get("id")) != str(mission.id)
    ]

    if update_master:
        replace_profile_from_extraction(db, master_id, extraction)
        # replace_profile commits; re-load mission
        mission = _mission(db, mission_id)
        mission.resume_source = {
            "mode": mode,
            "bound_at": now,
            "isolation": "shared_master",
            "updated_master": True,
            "master_profile_id": str(master_id),
            "filename": filename,
            "content_hash": content_hash_value,
            "section_order": list(source_section_order or []),
        }
        bound_profile_id = master_id
    else:
        local = create_draft_profile(db, extraction)
        # create_draft_profile commits; re-load mission in this session
        mission = _mission(db, mission_id)
        mission.resume_source = {
            "mode": mode,
            "bound_at": now,
            "isolation": "mission_local",
            "bound_profile_id": str(local.id),
            "master_profile_id": str(master_id),
            "filename": filename,
            "content_hash": content_hash_value,
            "section_order": list(source_section_order or []),
        }
        bound_profile_id = local.id

    # Purge claims/proof from the previous bind so strengthen uses the new profile only.
    if previous_bound_id and previous_bound_id != bound_profile_id:
        _purge_mission_claims_for_profile(db, mission, previous_bound_id)
    if not update_master and bound_profile_id != master_id:
        _purge_mission_claims_for_profile(db, mission, master_id)

    _reset_resume_optimization_state(db, mission)

    mission.status = MissionStatus.RESUME_PREP.value
    _set_workflow(mission, WorkflowState.RESUME_SELECTED)
    advance_workflow(mission, "need_selection", user_confirmed=True)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    effective = _effective_profile_for_mission(db, mission)
    return {
        "mission": _mission_read(mission),
        "profile_id": str(master_id),
        "bound_profile_id": str(bound_profile_id),
        "isolation": "shared_master" if update_master else "mission_local",
        "updated_master": bool(update_master),
        "experiences": [
            {
                "id": row.id,
                "title": row.title,
                "organization": row.organization,
                "dates": row.dates,
                "description": row.description,
            }
            for row in (effective.experiences or [])
        ],
        "affected_missions": affected,
    }


def confirm_strategy(db: Session, mission_id: UUID) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    if not mission.resume_strategy:
        raise _http(409, "请先生成简历策略，再确认进入下一步。")
    profile = _effective_profile_for_mission(db, mission)
    extraction = _coerce_extraction(mission.parsed_jd)
    what_matters = _coerce_what_matters(mission.what_matters)
    experience_ids = _experience_ids_for_profile(profile)
    selections = ExperienceSelectionPayload(selections=[
        {
            "experience_id": row.experience_id,
            "decision": row.decision,
            "why": row.why,
            "related_capabilities": row.related_capabilities or [],
            "supporting_evidence_refs": row.supporting_evidence_refs or [],
            "confidence": row.confidence,
        }
        for row in db.scalars(select(models.MissionExperienceSelection).where(models.MissionExperienceSelection.mission_id == mission.id)).all()
        if row.experience_id in experience_ids
    ])
    try:
        strategy_payload = ResumeStrategyPayload.model_validate(
            {k: v for k, v in (mission.resume_strategy or {}).items() if not str(k).startswith("_")}
            if isinstance(mission.resume_strategy, dict)
            else mission.resume_strategy
        )
    except Exception:
        raise _http(422, "简历策略格式无效，请重新生成策略后再确认。")
    strategy_payload = _ensure_strategy_grounded(
        strategy_payload,
        profile=profile,
        selections=selections,
        extraction=extraction,
        what_matters=what_matters,
    )
    mission.resume_strategy = strategy_payload.model_dump(mode="json")

    current = _workflow_of(mission)
    if current not in {
        WorkflowState.RESUME_STRATEGY_REQUIRED.value,
        WorkflowState.EXPERIENCES_CONFIRMED.value,
        WorkflowState.RESUME_STRATEGY_CONFIRMED.value,
    }:
        raise _http(409, "当前还不能确认简历策略。")
    advance_workflow(mission, "confirm_strategy", user_confirmed=True)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def confirm_target_resume(db: Session, mission_id: UUID) -> dict[str, object]:
    mission = _mission(db, mission_id)
    _require_resume_source(mission)
    resume = db.scalar(select(models.TargetResume).where(models.TargetResume.mission_id == mission.id).order_by(models.TargetResume.version.desc()))
    if resume is None:
        raise _http(409, "请先生成目标简历。")
    # Repair drafts created before the mutually-exclusive rewrite invariant
    # existed. Keep the first accepted/edited version for each source
    # experience and make later alternatives selectable again.
    chosen_sources: set[UUID] = set()
    for bullet in sorted(resume.bullets, key=lambda item: (item.sort_order, str(item.id))):
        if bullet.source_experience_id is None or bullet.status not in {"ACCEPTED", "EDITED"}:
            continue
        if bullet.source_experience_id in chosen_sources:
            bullet.status = "REJECTED"
            bullet.updated_at = datetime.now(timezone.utc)
        else:
            chosen_sources.add(bullet.source_experience_id)
    # Confirm only supported, grounded source bullets by default. Synthetic
    # project drafts and any NEEDS_CONFIRMATION bullet remain suggestions until
    # the user explicitly confirms the underlying fact.
    for bullet in resume.bullets:
        flags = {str(value).upper() for value in (bullet.risk_flags or [])}
        fact_confirmed = "FACT_CONFIRMED" in flags
        needs_fact_confirmation = "SYNTHETIC_PROJECT" in flags or "GROUNDING:NEEDS_CONFIRMATION" in flags
        if bullet.status == "SUGGESTED" and bullet.source_experience_id in chosen_sources:
            # Another rewrite for this experience is already selected.
            bullet.status = "REJECTED"
            bullet.updated_at = datetime.now(timezone.utc)
            continue
        if bullet.status == "SUGGESTED" and (fact_confirmed or not needs_fact_confirmation):
            bullet.status = "ACCEPTED"
            if not (bullet.final_text or "").strip():
                bullet.final_text = bullet.suggested_text
            if bullet.source_experience_id:
                chosen_sources.add(bullet.source_experience_id)
            bullet.updated_at = datetime.now(timezone.utc)
    current = _workflow_of(mission)
    if current not in {
        WorkflowState.TARGET_RESUME_DRAFT.value,
        WorkflowState.RESUME_STRATEGY_CONFIRMED.value,
        WorkflowState.TARGET_RESUME_CONFIRMED.value,
    }:
        raise _http(409, "当前还不能确认目标简历。")
    unresolved = []
    for bullet in resume.bullets:
        flags = {str(value).upper() for value in (bullet.risk_flags or [])}
        needs_fact = "SYNTHETIC_PROJECT" in flags or "GROUNDING:NEEDS_CONFIRMATION" in flags
        # Synthetic projects are proposals, not facts. They must never block the
        # confirmed resume/PDF hand-off: leave them visible as rejected
        # suggestions so the user can complete the real resume without claiming
        # an unfinished portfolio project.
        if "SYNTHETIC_PROJECT" in flags and "FACT_CONFIRMED" not in flags and bullet.status in {"SUGGESTED", "NEEDS_CONFIRMATION"}:
            bullet.status = "REJECTED"
            bullet.updated_at = datetime.now(timezone.utc)
            continue
        # A model suggestion that adds an unconfirmed fact is not allowed to
        # enter the final resume by default. Reject it during the single
        # confirmation step; the user can still edit it and explicitly confirm
        # the fact later.
        if bullet.status in {"SUGGESTED", "NEEDS_CONFIRMATION"} and needs_fact and "FACT_CONFIRMED" not in flags:
            bullet.status = "REJECTED"
            bullet.updated_at = datetime.now(timezone.utc)
            continue
        # Rejected alternatives and omitted synthetic drafts are intentional
        # exclusions. They must never keep the user from generating the final
        # resume; only a still-selected suggestion or an explicitly selected
        # fact-dependent bullet can remain unresolved.
        if bullet.status in {"SUGGESTED", "NEEDS_CONFIRMATION"} or (
            bullet.status in {"ACCEPTED", "EDITED"} and needs_fact and "FACT_CONFIRMED" not in flags
        ):
            unresolved.append(bullet)
    if unresolved:
        raise _http(409, "还有内容需要确认事实后才能生成最终简历。")
    resume.status = "CONFIRMED"
    advance_workflow(mission, "confirm_target", user_confirmed=True)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def advance_mission_workflow(db: Session, mission_id: UUID, payload: AdvanceWorkflow) -> dict[str, object]:
    mission = _mission(db, mission_id)
    advance_workflow(mission, payload.event, user_confirmed=payload.user_confirmed)
    # Convenience: moving to resume from role
    if payload.event == "select_resume":
        _set_workflow(mission, WorkflowState.RESUME_REQUIRED)
    if payload.event == "strengthen":
        mission.status = MissionStatus.STRENGTHENING.value
    if payload.event == "interview_ready":
        mission.status = MissionStatus.INTERVIEW_PREP.value
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)


def _serialize_interview_intel(items: list[object]) -> list[dict[str, object]]:
    """JSON-column safe: dataclasses -> dicts via intel_records."""
    if not items:
        return []
    records: list[dict[str, object]] = []
    pending: list[InterviewIntelResult] = []
    for item in items:
        if isinstance(item, InterviewIntelResult):
            pending.append(item)
            continue
        if pending:
            records.extend(intel_records(pending))
            pending = []
        if isinstance(item, dict):
            records.append(dict(item))
    if pending:
        records.extend(intel_records(pending))
    return records


def retry_company_intel(db: Session, mission_id: UUID, provider=None) -> dict[str, object]:
    """Best-effort refresh of interview_intel without failing the mission."""
    mission = _mission(db, mission_id)
    try:
        extraction = _coerce_extraction(mission.parsed_jd)
        retriever = InterviewIntelRetriever()
        raw: list[object] = []
        for method_name in ("retrieve_for_mission", "retrieve", "search", "get_intel"):
            method = getattr(retriever, method_name, None)
            if not callable(method):
                continue
            try:
                result = method(company=extraction.company, role=extraction.role, role_family=extraction.role_family)
            except TypeError:
                try:
                    result = method(extraction.company, extraction.role, extraction.role_family)
                except TypeError:
                    result = method(extraction)  # last resort
            if isinstance(result, list):
                raw = list(result)
            elif result:
                raw = list(result)
            break
        if not raw and hasattr(MissionIntelligenceService, "reload_intel"):
            service = MissionIntelligenceService(provider=provider or get_mission_provider(), retriever=retriever)
            raw = list(service.reload_intel(extraction) or [])  # type: ignore[attr-defined]
        intel = _serialize_interview_intel(raw)
        mission.interview_intel = intel
        mission.updated_at = datetime.now(timezone.utc)
        db.commit()
        db.refresh(mission)
        out = _mission_read(mission)
        if not intel:
            out["warnings"] = list(dict.fromkeys([*(out.get("warnings") or []), "company_intel_unavailable"]))
        return out
    except Exception:
        logger.exception("retry_company_intel failed mission_id=%s", mission_id)
        try:
            db.rollback()
        except Exception:
            logger.exception("retry_company_intel rollback failed mission_id=%s", mission_id)
        mission = _mission(db, mission_id)
        out = _mission_read(mission)
        out["warnings"] = list(dict.fromkeys([*(out.get("warnings") or []), "company_intel_unavailable"]))
        return out

def mark_role_continue(db: Session, mission_id: UUID) -> dict[str, object]:
    """Primary CTA on role page: 下一步：选择简历"""
    mission = _mission(db, mission_id)
    if _workflow_of(mission) == WorkflowState.ROLE_UNDERSTOOD.value:
        advance_workflow(mission, "select_resume", user_confirmed=True)
    elif _workflow_of(mission) in {WorkflowState.JD_REQUIRED.value, WorkflowState.JOB_ANALYZING.value}:
        _set_workflow(mission, WorkflowState.RESUME_REQUIRED)
    mission.updated_at = datetime.now(timezone.utc)
    db.commit()
    db.refresh(mission)
    return _mission_read(mission)
