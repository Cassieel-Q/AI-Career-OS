from __future__ import annotations

from datetime import datetime
from enum import StrEnum
from typing import Self
from urllib.parse import urlparse
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class _StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ReadinessStatus(StrEnum):
    SUPPORTED = "SUPPORTED"
    DEFENDABLE = "DEFENDABLE"
    WEAK_EVIDENCE = "WEAK_EVIDENCE"
    UNSUPPORTED = "UNSUPPORTED"


class InterviewGapType(StrEnum):
    KNOWLEDGE_GAP = "KNOWLEDGE_GAP"
    PROJECT_GAP = "PROJECT_GAP"
    EVIDENCE_GAP = "EVIDENCE_GAP"
    ARTICULATION_GAP = "ARTICULATION_GAP"


class InterviewSessionStatus(StrEnum):
    ACTIVE = "ACTIVE"
    COMPLETED = "COMPLETED"
    INVALIDATED = "INVALIDATED"


class ProofActionStatus(StrEnum):
    PROPOSED = "PROPOSED"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    SKIPPED = "SKIPPED"


class AttackSurfaceArea(StrEnum):
    PRODUCT = "PRODUCT"
    AI = "AI"
    ENGINEERING = "ENGINEERING"
    METRICS = "METRICS"
    BUSINESS_IMPACT = "BUSINESS_IMPACT"


class _TextModel(_StrictModel):
    @field_validator("name", "summary", "claim", "current_text", "suggested_text", "reason", "jd_relevance", "risk_reason", mode="before", check_fields=False)
    @classmethod
    def strip_text(cls, value: object) -> object:
        return value.strip() if isinstance(value, str) else value


def _normalize_source_url(value: object) -> str | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise ValueError("source_url must be a string or null")
    normalized = value.strip()
    if not normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("source_url must be an HTTP(S) URL with a host")
    return normalized


def _required_text(value: object, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must contain non-whitespace text")
    return value.strip()


class TargetJobCreate(_StrictModel):
    raw_text: str = Field(min_length=1, max_length=50_000)
    source_url: str | None = None

    @field_validator("raw_text", mode="before")
    @classmethod
    def validate_raw_text(cls, value: object) -> str:
        if not isinstance(value, str) or not value.strip():
            raise ValueError("raw_text must contain non-whitespace text")
        return value

    _normalize_source_url = field_validator("source_url", mode="before")(_normalize_source_url)


class TargetJobRequirement(_StrictModel):
    id: UUID
    name: str = Field(min_length=1, max_length=255)
    category: str = Field(min_length=1, max_length=32)
    evidence_text: str = Field(min_length=1, max_length=1_000)


class TargetJobCapability(_StrictModel):
    name: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=600)
    atomic_requirement_ids: list[UUID] = Field(default_factory=list, max_length=20)


class AttackSurfaceItem(_StrictModel):
    area: AttackSurfaceArea
    risk: str = Field(min_length=1, max_length=300)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=12)


class ClaimProposal(_TextModel):
    claim: str = Field(min_length=1, max_length=600)
    current_text: str | None = Field(default=None, max_length=600)
    suggested_text: str | None = Field(default=None, max_length=600)
    reason: str = Field(min_length=1, max_length=600)
    jd_relevance: str = Field(min_length=1, max_length=600)
    matched_capabilities: list[TargetJobCapability] = Field(default_factory=list, max_length=12)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=12)
    readiness_status: ReadinessStatus
    confidence: float = Field(ge=0, le=1)
    risk_reason: str = Field(min_length=1, max_length=600)
    attack_surface: list[AttackSurfaceItem] = Field(default_factory=list, max_length=5)

    @model_validator(mode="after")
    def require_safe_suggestion(self) -> Self:
        if self.suggested_text and self.readiness_status in {ReadinessStatus.SUPPORTED, ReadinessStatus.DEFENDABLE} and not self.evidence_refs:
            raise ValueError("supported or defendable suggestions require grounded evidence_refs")
        return self


class ClaimProposalPayload(_StrictModel):
    claims: list[ClaimProposal] = Field(min_length=1, max_length=50)


class TargetJobRead(_StrictModel):
    id: UUID
    profile_id: UUID
    raw_text: str
    source_url: str | None
    content_hash: str
    status: str
    created_at: datetime
    updated_at: datetime


class ResumeClaimRead(_StrictModel):
    id: UUID
    target_job_id: UUID
    profile_id: UUID
    claim: str
    current_text: str | None
    suggested_text: str | None
    reason: str
    jd_relevance: str
    matched_capabilities: list[TargetJobCapability]
    evidence_refs: list[UUID]
    readiness_status: ReadinessStatus
    confidence: float
    risk_reason: str
    attack_surface: list[AttackSurfaceItem]
    fingerprint: str
    created_at: datetime
    updated_at: datetime


class ClaimAnalysisRead(_StrictModel):
    target_job_id: UUID
    profile_id: UUID
    fingerprint: str
    claims: list[ResumeClaimRead]
    # 事实改了之后「只标记不替换」：不静默重算，也不把旧分析伪装成新鲜结果。
    stale: bool = False
    stale_reasons: list[str] = Field(default_factory=list, max_length=8)


class ClaimAnalysisStaleRead(_StrictModel):
    """事实变更后的过期提示（与 match_contract.stale_status 的口径一致）。"""

    target_job_id: UUID
    stale: bool
    reasons: list[str] = Field(default_factory=list, max_length=8)
    analyzed_at: datetime | None = None


class InterviewSessionCreate(_StrictModel):
    claim_id: UUID


class InterviewTurnCreate(_StrictModel):
    answer: str = Field(min_length=1, max_length=8_000)

    @field_validator("answer", mode="before")
    @classmethod
    def validate_answer(cls, value: object) -> str:
        return _required_text(value, "answer")


class InterviewTurnRead(_StrictModel):
    id: UUID
    # Historical sessions can contain more rounds than the current five-round
    # product cap. Keep reads compatible while new submissions stop at five.
    round_number: int = Field(ge=1, le=100)
    skill_id: str
    question: str
    answer: str | None
    followup_dimensions: list[str]
    evaluation: dict[str, object]
    created_at: datetime


class InterviewSessionRead(_StrictModel):
    id: UUID
    profile_id: UUID
    target_job_id: UUID
    claim_id: UUID
    mission_id: UUID | None = None
    status: InterviewSessionStatus
    round_count: int = Field(ge=0, le=100)
    next_question: str | None
    next_skill_id: str | None
    strong_points: list[str]
    weak_points: list[str]
    gap_type: InterviewGapType | None
    gap_why: str | None
    gap_evidence: list[UUID]
    recommended_next_action: str | None
    turns: list[InterviewTurnRead]
    created_at: datetime
    updated_at: datetime


class InterviewQuestionPayload(_StrictModel):
    question: str = Field(min_length=1, max_length=1_000)
    skill_id: str = Field(min_length=1, max_length=64)
    followup_dimensions: list[str] = Field(default_factory=list, max_length=8)


class ReferenceKnownFact(_StrictModel):
    """参考回答中引用的、可在原始材料里找到的已知事实。"""

    text: str = Field(min_length=1, max_length=400)
    source_kind: str = Field(default="SOURCE_EXTRACTED", max_length=40)
    source_id: str | None = Field(default=None, max_length=120)
    quote: str | None = Field(default=None, max_length=400)


class ReferenceMissingFact(_StrictModel):
    """要写出完整回答还缺什么。只提问题，不代答。"""

    aspect: str = Field(min_length=1, max_length=200)
    question: str = Field(default="", max_length=400)


class ReferenceAnswerDetail(_StrictModel):
    """结构化参考答案（指令 1.2）。

    - ``known_facts``：已知事实，带来源引用。
    - ``missing_facts``：需要补充的行动 / 发现 / 困难 / 结果。
    - ``answer_structure``：STAR 之类的表达结构。
    - ``sample_wording``：**仅在事实充分时**生成的可使用示范表达，不补造第一人称经历。
    - ``grounded``：模型自审结论；为 False 或缺失时，示范表达一律降级。
    """

    grounded: bool = False
    known_facts: list[ReferenceKnownFact] = Field(default_factory=list, max_length=12)
    missing_facts: list[ReferenceMissingFact] = Field(default_factory=list, max_length=12)
    answer_structure: list[str] = Field(default_factory=list, max_length=8)
    sample_wording: str | None = Field(default=None, max_length=1_200)
    blocked_reason: str | None = Field(default=None, max_length=400)
    screening: dict[str, object] = Field(default_factory=dict)


class InterviewEvaluation(_StrictModel):
    score: int | None = Field(default=None, ge=0, le=10)
    reference_answer: str | None = Field(default=None, max_length=4_000)
    reference_answer_detail: ReferenceAnswerDetail | None = None
    strong_points: list[str] = Field(default_factory=list, max_length=8)
    weak_points: list[str] = Field(default_factory=list, max_length=8)
    gap_type: InterviewGapType | None = None
    why: str | None = Field(default=None, max_length=600)
    evidence_refs: list[UUID] = Field(default_factory=list, max_length=12)
    recommended_next_action: str | None = Field(default=None, max_length=600)


class InterviewResponsePayload(_StrictModel):
    question: str | None = Field(default=None, max_length=1_000)
    skill_id: str | None = Field(default=None, max_length=64)
    followup_dimensions: list[str] = Field(default_factory=list, max_length=8)
    evaluation: InterviewEvaluation


class ProofActionProposal(_StrictModel):
    title: str = Field(min_length=1, max_length=255)
    why_now: str = Field(min_length=1, max_length=600)
    target_claim: str = Field(min_length=1, max_length=600)
    target_gap: InterviewGapType
    estimated_hours: float = Field(gt=0, le=80)
    artifact_type: str = Field(min_length=1, max_length=64)
    definition_of_done: str = Field(min_length=1, max_length=600)
    expected_evidence: str = Field(min_length=1, max_length=600)


class ProofActionCreate(_StrictModel):
    actions: list[ProofActionProposal] = Field(min_length=1, max_length=3)


class ProofActionRead(ProofActionProposal):
    id: UUID
    claim_id: UUID
    profile_id: UUID
    status: ProofActionStatus
    completed_at: datetime | None
    updated_at: datetime


class ProofArtifactCreate(_StrictModel):
    action_id: UUID
    artifact_type: str = Field(min_length=1, max_length=64)
    artifact_url: str | None = None
    artifact_text: str | None = Field(default=None, max_length=20_000)
    manually_confirmed: bool = False
    verified_fields: list[str] = Field(default_factory=list, max_length=20)

    _normalize_artifact_url = field_validator("artifact_url", mode="before")(_normalize_source_url)

    @model_validator(mode="after")
    def require_artifact_content(self) -> Self:
        if not self.artifact_url and not (self.artifact_text and self.artifact_text.strip()):
            raise ValueError("artifact_url or artifact_text is required")
        return self


class ProofArtifactRead(ProofArtifactCreate):
    id: UUID
    claim_id: UUID
    profile_id: UUID
    created_at: datetime


class ReevaluateRead(_StrictModel):
    claim_id: UUID
    before_readiness: ReadinessStatus
    after_readiness: ReadinessStatus
    before_confidence: float
    after_confidence: float
    new_evidence_refs: list[UUID]
    reason: str
    artifacts: list[ProofArtifactRead]


class ProofGuidanceRead(_StrictModel):
    """LLM guidance shown after the user chooses a strengthening path.

    This is intentionally ephemeral: the user receives a plan or follow-up
    questions directly and is not asked to upload a proof artifact first.
    """

    claim_id: UUID
    action_type: str = Field(min_length=1, max_length=64)
    title: str = Field(min_length=1, max_length=255)
    summary: str = Field(min_length=1, max_length=2_000)
    questions: list[str] = Field(default_factory=list, max_length=5)
    steps: list[str] = Field(default_factory=list, max_length=8)
    learning: list[str] = Field(default_factory=list, max_length=8)
    expected_outputs: list[str] = Field(default_factory=list, max_length=8)
    generated_by: str = Field(default="llm", max_length=32)
