"""Code-owned immutable catalog for the six exploratory AI roles."""
from __future__ import annotations

from dataclasses import dataclass

from .role_exploration_schemas import CodingIntensity, EntryBarrier, RoleCode

ROLE_PROFILE_VERSION: str = "v1"


@dataclass(frozen=True, slots=True)
class RoleProfile:
    role_code: RoleCode
    display_name: str
    summary: str
    core_responsibilities: tuple[str, ...]
    key_capabilities: tuple[str, ...]
    coding_intensity: CodingIntensity
    entry_barrier: EntryBarrier
    typical_evidence: tuple[str, ...]
    career_characteristics: tuple[str, ...]


ROLE_PROFILES: tuple[RoleProfile, ...] = (
    RoleProfile(RoleCode.AI_PRODUCT_MANAGER, "AI Product Manager", "Defines AI product outcomes and coordinates delivery.", ("product discovery", "roadmap", "cross-functional alignment"), ("problem framing", "communication", "prioritization"), CodingIntensity.LOW, EntryBarrier.MEDIUM, ("product ownership", "stakeholder coordination"), ("customer-facing", "cross-functional")),
    RoleProfile(RoleCode.AI_APPLICATION_ENGINEER, "AI Application Engineer", "Builds software products that use AI capabilities.", ("application development", "integration", "testing"), ("Python or TypeScript", "APIs", "software engineering"), CodingIntensity.HIGH, EntryBarrier.MEDIUM, ("software projects", "engineering experience"), ("hands-on", "implementation-focused")),
    RoleProfile(RoleCode.AI_SOLUTION_CONSULTANT, "AI Solution Consultant", "Translates organizational needs into practical AI solutions.", ("discovery workshops", "solution design", "adoption support"), ("requirements analysis", "communication", "domain translation"), CodingIntensity.MEDIUM, EntryBarrier.MEDIUM, ("client or domain projects", "solution proposals"), ("advisory", "customer-facing")),
    RoleProfile(RoleCode.LLM_ALGORITHM_ENGINEER, "LLM Algorithm Engineer", "Develops and evaluates model and algorithm behavior.", ("model experimentation", "evaluation", "algorithm development"), ("machine learning", "statistics", "Python"), CodingIntensity.HIGH, EntryBarrier.HIGH, ("ML research", "algorithm projects"), ("research-oriented", "technical depth")),
    RoleProfile(RoleCode.AI_DATA_ANALYST, "AI Data Analyst", "Uses data analysis to support AI and business decisions.", ("data preparation", "analysis", "insight communication"), ("SQL", "statistics", "visualization"), CodingIntensity.MEDIUM, EntryBarrier.LOW, ("analytical projects", "data reporting"), ("evidence-led", "business-facing")),
    RoleProfile(RoleCode.AI_PRODUCT_OPERATIONS, "AI Product Operations", "Improves the operating rhythm and quality of AI products.", ("workflow operations", "quality monitoring", "process improvement"), ("coordination", "documentation", "metrics literacy"), CodingIntensity.LOW, EntryBarrier.LOW, ("operations projects", "process improvement"), ("execution-focused", "cross-functional")),
)

ROLE_PROFILE_BY_CODE: dict[RoleCode, RoleProfile] = {profile.role_code: profile for profile in ROLE_PROFILES}
