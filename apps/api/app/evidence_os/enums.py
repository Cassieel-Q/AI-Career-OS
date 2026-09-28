from __future__ import annotations
from enum import StrEnum

class VerificationStatus(StrEnum):
    CONFIRMED = "confirmed"
    PENDING = "pending"
    EXPIRED = "expired"
    REJECTED = "rejected"

class ResponsibilityLevel(StrEnum):
    CONTRIBUTED = "contributed"
    OWNED_MODULE = "owned_module"
    LED_DELIVERY = "led_delivery"
    PROJECT_OWNER = "project_owner"

class EvidenceType(StrEnum):
    USER_CONFIRMED = "user_confirmed"
    RESUME_PRIOR = "resume_prior"
    PRD = "prd"
    REPO = "repo"
    PORTFOLIO = "portfolio"
    DOCUMENT = "document"
    CONVERSATION = "conversation"
    METRIC_ARTIFACT = "metric_artifact"

class RequirementPriority(StrEnum):
    HARD_GATE = "hard_gate"
    CORE = "core"
    PREFERRED = "preferred"
    TOOLING = "tooling"
    NICE_TO_HAVE = "nice_to_have"
    NOISE = "noise"

class MatchStatus(StrEnum):
    COVERED = "covered"
    WEAK = "weak"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"
    NEEDS_EXCAVATION = "needs_excavation"

class PositioningMode(StrEnum):
    CONSERVATIVE = "conservative"
    AMBITIOUS = "ambitious"

class VersionStatus(StrEnum):
    DRAFT = "draft"
    AWAITING_APPROVAL = "awaiting_approval"
    APPROVED = "approved"
    RENDERED = "rendered"
    SUPERSEDED = "superseded"

class EvalKind(StrEnum):
    KEYWORD_COVERAGE = "keyword_coverage"
    REQUIREMENT_COVERAGE = "requirement_coverage"
    EVIDENCE_COVERAGE = "evidence_coverage"
    PARSING_RISK = "parsing_risk"
    FORMATTING_RISK = "formatting_risk"

class ResumeSection(StrEnum):
    SUMMARY = "summary"
    EXPERIENCE = "experience"
    PROJECT = "project"
    SKILLS = "skills"
    EDUCATION = "education"
    OTHER = "other"
