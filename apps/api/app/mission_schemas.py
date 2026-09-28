from __future__ import annotations

from enum import Enum
from datetime import datetime
from typing import Self
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

from .jd_identity_normalize import normalize_location, normalize_seniority


class _Strict(BaseModel):
    model_config = ConfigDict(extra="forbid")


class MissionStatus(str, Enum):
    DRAFT = "DRAFT"
    RESUME_PREP = "RESUME_PREP"
    STRENGTHENING = "STRENGTHENING"
    INTERVIEW_PREP = "INTERVIEW_PREP"
    APPLIED = "APPLIED"
    INTERVIEWING = "INTERVIEWING"
    COMPLETED = "COMPLETED"
    ARCHIVED = "ARCHIVED"


class WorkflowState(str, Enum):
    JD_REQUIRED = "JD_REQUIRED"
    JOB_ANALYZING = "JOB_ANALYZING"
    ROLE_UNDERSTOOD = "ROLE_UNDERSTOOD"
    RESUME_REQUIRED = "RESUME_REQUIRED"
    RESUME_SELECTED = "RESUME_SELECTED"
    EXPERIENCE_SELECTION_REQUIRED = "EXPERIENCE_SELECTION_REQUIRED"
    EXPERIENCES_CONFIRMED = "EXPERIENCES_CONFIRMED"
    RESUME_STRATEGY_REQUIRED = "RESUME_STRATEGY_REQUIRED"
    RESUME_STRATEGY_CONFIRMED = "RESUME_STRATEGY_CONFIRMED"
    TARGET_RESUME_DRAFT = "TARGET_RESUME_DRAFT"
    TARGET_RESUME_CONFIRMED = "TARGET_RESUME_CONFIRMED"
    STRESS_TEST_REQUIRED = "STRESS_TEST_REQUIRED"
    STRENGTHENING_REQUIRED = "STRENGTHENING_REQUIRED"
    PROOF_IN_PROGRESS = "PROOF_IN_PROGRESS"
    CLAIM_REEVALUATION_REQUIRED = "CLAIM_REEVALUATION_REQUIRED"
    RESUME_UPGRADE_AVAILABLE = "RESUME_UPGRADE_AVAILABLE"
    INTERVIEW_PREP_READY = "INTERVIEW_PREP_READY"
    INTERVIEW_IN_PROGRESS = "INTERVIEW_IN_PROGRESS"
    INTERVIEW_DEBRIEF_READY = "INTERVIEW_DEBRIEF_READY"
    OUTCOME = "OUTCOME"


class ResumeSourceMode(str, Enum):
    master = "master"
    upload = "upload"
    paste = "paste"


class ConfirmResumeSource(_Strict):
    mode: ResumeSourceMode
    # When True with upload/paste, intentionally overwrite shared Master Profile.
    # Default False = mission-local copy-on-write (bound_profile_id in resume_source).
    update_master: bool = False


class AdvanceWorkflow(_Strict):
    event: str = Field(min_length=1, max_length=64)
    user_confirmed: bool = True


class ExperienceDecision(str, Enum):
    KEEP_AND_HIGHLIGHT = "KEEP_AND_HIGHLIGHT"
    KEEP = "KEEP"
    DEEMPHASIZE = "DEEMPHASIZE"
    OMIT = "OMIT"


class ResumeBulletStatus(str, Enum):
    SUGGESTED = "SUGGESTED"
    ACCEPTED = "ACCEPTED"
    EDITED = "EDITED"
    REJECTED = "REJECTED"


class GroundingStatus(str, Enum):
    SUPPORTED = "SUPPORTED"
    NEEDS_CONFIRMATION = "NEEDS_CONFIRMATION"
    UNSUPPORTED = "UNSUPPORTED"


class Priority(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    RESUME_SPECIFIC = "RESUME_SPECIFIC"


class JDRequirement(_Strict):
    id: str = Field(min_length=1, max_length=96)
    text: str = Field(min_length=1, max_length=1_000)
    category: str = Field(min_length=1, max_length=64)
    evidence_text: str = Field(default="", max_length=1_000)


class JobExtractionPayload(_Strict):
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    role_family: str = Field(min_length=1, max_length=64)
    seniority: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=255)
    responsibilities: list[str] = Field(default_factory=list, max_length=60)
    requirements: list[JDRequirement] = Field(default_factory=list, max_length=80)
    preferred_requirements: list[JDRequirement] = Field(default_factory=list, max_length=50)
    capabilities: list[str] = Field(default_factory=list, max_length=60)
    keywords: list[str] = Field(default_factory=list, max_length=100)

    @field_validator("seniority", mode="before")
    @classmethod
    def _coerce_seniority(cls, value: object) -> str:
        return normalize_seniority(value)

    @field_validator("location", mode="before")
    @classmethod
    def _coerce_location(cls, value: object) -> str | None:
        return normalize_location(value)


class CapabilityInsight(_Strict):
    name: str = Field(min_length=1, max_length=255)
    why: str = Field(min_length=1, max_length=1_000)
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class RequirementInsight(_Strict):
    text: str = Field(min_length=1, max_length=1_000)
    importance: Priority | str
    evidence_refs: list[str] = Field(default_factory=list, max_length=20)


class WhatMattersPayload(_Strict):
    core_capabilities: list[CapabilityInsight] = Field(default_factory=list, max_length=30)
    high_importance_requirements: list[RequirementInsight] = Field(default_factory=list, max_length=50)
    evidence_expected: list[str] = Field(default_factory=list, max_length=30)
    likely_success_signals: list[str] = Field(default_factory=list, max_length=30)
    bonus_capabilities: list[str] = Field(default_factory=list, max_length=30)
    potential_interview_focus: list[str] = Field(default_factory=list, max_length=30)
    confidence: float = Field(ge=0, le=1)
    jd_evidence_refs: list[str] = Field(default_factory=list, max_length=80)

    @model_validator(mode="after")
    def require_grounding(self) -> Self:
        refs = set(self.jd_evidence_refs)
        for item in [*self.core_capabilities, *self.high_importance_requirements]:
            if not set(item.evidence_refs).issubset(refs):
                raise ValueError("What Matters evidence_refs must be included in jd_evidence_refs")
        return self


class ExperienceSelection(_Strict):
    experience_id: UUID
    decision: ExperienceDecision
    why: str = Field(min_length=1, max_length=1_000)
    related_capabilities: list[str] = Field(default_factory=list, max_length=20)
    supporting_evidence_refs: list[UUID] = Field(default_factory=list, max_length=20)
    confidence: float = Field(ge=0, le=1)


class ExperienceSelectionPayload(_Strict):
    selections: list[ExperienceSelection] = Field(default_factory=list, max_length=50)


class ExperienceStrategy(_Strict):
    experience_id: UUID
    role_in_story: str = Field(min_length=1, max_length=600)
    what_to_highlight: list[str] = Field(default_factory=list, max_length=20)
    what_to_avoid: list[str] = Field(default_factory=list, max_length=20)
    target_capabilities: list[str] = Field(default_factory=list, max_length=20)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=20)
    interview_risk_notes: list[str] = Field(default_factory=list, max_length=20)


class ResumeStrategyPayload(_Strict):
    positioning_statement: str = Field(min_length=1, max_length=600)
    recommended_experience_order: list[UUID] = Field(default_factory=list, max_length=20)
    experience_guidance: list[ExperienceStrategy] = Field(default_factory=list, max_length=20)


class ResumeBulletProposal(_Strict):
    source_experience_id: UUID | None = None
    original_text: str = Field(min_length=1, max_length=2_000)
    suggested_text: str = Field(min_length=1, max_length=2_000)
    final_text: str | None = Field(default=None, max_length=2_000)
    reason: str = Field(min_length=1, max_length=1_000)
    jd_refs: list[str] = Field(default_factory=list, max_length=30)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=30)
    resume_skill_refs: list[str] = Field(default_factory=list, max_length=20)
    risk_flags: list[str] = Field(default_factory=list, max_length=20)
    target_capabilities: list[str] = Field(default_factory=list, max_length=20)
    grounding_status: GroundingStatus = GroundingStatus.SUPPORTED


class TargetResumePayload(_Strict):
    positioning_statement: str = Field(min_length=1, max_length=600)
    recommended_experience_order: list[UUID] = Field(default_factory=list, max_length=20)
    bullets: list[ResumeBulletProposal] = Field(default_factory=list, max_length=80)
    section_order: list[str] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=40)
    excluded_suggestions: list[str] = Field(default_factory=list, max_length=40)


class TargetResumeBulletSuggestion(_Strict):
    original_text: str = Field(min_length=1, max_length=2_000)
    suggested_text: str = Field(min_length=1, max_length=2_000)
    why_changed: str = Field(min_length=1, max_length=1_000)
    target_capabilities: list[str] = Field(default_factory=list, max_length=20)
    jd_evidence_refs: list[str] = Field(default_factory=list, max_length=30)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=30)
    resume_skill_refs: list[str] = Field(default_factory=list, max_length=20)
    grounding_status: GroundingStatus = GroundingStatus.SUPPORTED
    risk_flags: list[str] = Field(default_factory=list, max_length=20)


class TargetResumeExperienceBlock(_Strict):
    source_experience_id: UUID | None = None
    display_name: str = Field(min_length=1, max_length=255)
    role_in_resume: str = Field(default="", max_length=600)
    include: bool = True
    bullets: list[TargetResumeBulletSuggestion] = Field(default_factory=list, max_length=20)


class TargetResumeGenerationResult(_Strict):
    """Strict LLM contract for Target Resume optimization (evidence-grounded)."""

    positioning_summary: str = Field(default="", max_length=600)
    section_order: list[str] = Field(default_factory=list, max_length=20)
    experiences: list[TargetResumeExperienceBlock] = Field(default_factory=list, max_length=20)
    skills: list[str] = Field(default_factory=list, max_length=40)
    excluded_suggestions: list[str] = Field(default_factory=list, max_length=40)


class TargetResumeGenerateRequest(_Strict):
    source_resume_id: str | None = Field(default=None, max_length=128)
    strategy_version: int | None = Field(default=None, ge=1, le=10_000)


class RedTeamFinding(_Strict):
    claim: str = Field(min_length=1, max_length=1_000)
    jd_relevance: str = Field(min_length=1, max_length=1_000)
    evidence_strength: str = Field(min_length=1, max_length=1_000)
    company_interview_trigger: str = Field(min_length=1, max_length=1_000)
    attack_dimensions: list[str] = Field(default_factory=list, max_length=5)
    likely_followups: list[str] = Field(default_factory=list, max_length=20)
    risk_level: str = Field(min_length=1, max_length=24)
    why: str = Field(min_length=1, max_length=1_000)
    recommended_next_step: str = Field(min_length=1, max_length=1_000)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=30)
    claim_id: UUID | None = None


class RedTeamPayload(_Strict):
    findings: list[RedTeamFinding] = Field(default_factory=list, max_length=80)


class InterviewTopic(_Strict):
    priority: Priority
    topic: str = Field(min_length=1, max_length=600)
    why: str = Field(min_length=1, max_length=1_000)
    claims: list[str] = Field(default_factory=list, max_length=20)
    capabilities: list[str] = Field(default_factory=list, max_length=20)
    intel_refs: list[str] = Field(default_factory=list, max_length=20)
    question_patterns: list[str] = Field(default_factory=list, max_length=20)
    evidence_expected: list[str] = Field(default_factory=list, max_length=20)


class InterviewPackPayload(_Strict):
    topics: list[InterviewTopic] = Field(default_factory=list, max_length=50)


class MissionCreate(_Strict):
    raw_text: str = Field(min_length=20, max_length=100_000)
    source_url: str | None = Field(default=None, max_length=2_000)


class MissionReanalyze(_Strict):
    raw_text: str = Field(min_length=20, max_length=100_000)
    source_url: str | None = Field(default=None, max_length=2_000)


class MissionIdentityUpdate(_Strict):
    company: str = Field(min_length=1, max_length=255)
    role: str = Field(min_length=1, max_length=255)
    role_family: str = Field(min_length=1, max_length=64)
    seniority: str = Field(min_length=1, max_length=64)
    location: str | None = Field(default=None, max_length=255)

    @field_validator("seniority", mode="before")
    @classmethod
    def _coerce_seniority(cls, value: object) -> str:
        return normalize_seniority(value)

    @field_validator("location", mode="before")
    @classmethod
    def _coerce_location(cls, value: object) -> str | None:
        return normalize_location(value)


class MissionOutcomeCreate(_Strict):
    application_status: str = Field(min_length=1, max_length=32)
    interview_round: str | None = Field(default=None, max_length=64)
    questions_asked: list[str] = Field(default_factory=list, max_length=100)
    where_struggled: str | None = Field(default=None, max_length=4_000)
    interviewer_feedback: str | None = Field(default=None, max_length=4_000)
    notes: str | None = Field(default=None, max_length=4_000)
    confirmed_for_intel: bool = False

    @model_validator(mode="after")
    def require_debrief_substance(self) -> Self:
        round_ok = bool((self.interview_round or "").strip())
        questions_ok = any(str(q or "").strip() for q in (self.questions_asked or []))
        struggle_ok = bool((self.where_struggled or "").strip())
        feedback_ok = bool((self.interviewer_feedback or "").strip())
        if not (round_ok or questions_ok or struggle_ok or feedback_ok):
            raise ValueError("请至少填写面试轮次、被问到的问题、卡点或面试官反馈中的一项后再保存。")
        return self


class TargetResumeBulletUpdate(_Strict):
    status: ResumeBulletStatus | None = None
    final_text: str | None = Field(default=None, max_length=2_000)
    # Explicitly separates accepting the wording from confirming that a newly
    # introduced fact is true. Persisted in risk_flags to avoid a schema migration.
    fact_confirmed: bool | None = None


class RecoverEvidenceCreate(_Strict):
    claim_id: UUID
    confirmed: bool
    evidence_text: str | None = Field(default=None, max_length=20_000)
    artifact_type: str = Field(default="USER_CONFIRMED", min_length=1, max_length=64)
    artifact_text: str | None = Field(default=None, max_length=20_000)
    target_capability: str | None = Field(default=None, max_length=255)
    existing_project_reference: str | None = Field(default=None, max_length=2_000)


class MissionRead(_Strict):
    id: UUID
    profile_id: UUID
    target_job_id: UUID
    display_name: str
    company: str
    role: str
    role_family: str
    seniority: str
    location: str | None
    status: MissionStatus
    workflow_state: WorkflowState | str = WorkflowState.ROLE_UNDERSTOOD
    resume_source: dict[str, object] | None = None
    warnings: list[str] = Field(default_factory=list)
    parsed_jd: JobExtractionPayload | dict[str, object]
    what_matters: WhatMattersPayload | dict[str, object]
    resume_strategy: dict[str, object]
    interview_intel: list[dict[str, object]]
    created_at: datetime
    updated_at: datetime
