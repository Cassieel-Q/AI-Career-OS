from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from uuid import UUID

import pytest
from sqlalchemy.orm import Session

from app import models
from app.profile_schemas import CareerPreferencePriority, ProfileStatus
from app.role_exploration_provider import RoleExplorationContext, set_role_exploration_provider
from app.role_exploration_schemas import ExplorationLevel, RoleCode, RoleExplorationProviderItem, RoleExplorationProviderPayload
from app.role_exploration_service import create_role_exploration
from app.role_profiles import ROLE_PROFILE_BY_CODE, ROLE_PROFILE_VERSION


@dataclass(frozen=True)
class SyntheticContext:
    name: str
    priorities: tuple[CareerPreferencePriority, CareerPreferencePriority]
    order: tuple[RoleCode, ...]


SYNTHETIC_CONTEXTS = (
    SyntheticContext(
        "product-operations-fast-entry",
        (CareerPreferencePriority.LESS_CODING, CareerPreferencePriority.FAST_EMPLOYMENT),
        tuple(reversed(tuple(RoleCode))),
    ),
    SyntheticContext(
        "python-development-current-fit",
        (CareerPreferencePriority.CURRENT_FIT, CareerPreferencePriority.LESS_CODING),
        tuple(RoleCode)[2:] + tuple(RoleCode)[:2],
    ),
    SyntheticContext(
        "algorithm-data-long-term-growth",
        (CareerPreferencePriority.LONG_TERM_GROWTH, CareerPreferencePriority.CURRENT_FIT),
        tuple(RoleCode),
    ),
)


class _SyntheticProvider:
    def __init__(self, order: tuple[RoleCode, ...]) -> None:
        self.order = order
        self.contexts: list[RoleExplorationContext] = []

    def explore(self, context: RoleExplorationContext) -> RoleExplorationProviderPayload:
        self.contexts.append(context)
        evidence_refs = tuple(fact.id for fact in context.facts)
        preference_refs = tuple(preference.value for preference in context.preferences)
        assert evidence_refs
        assert len(preference_refs) == 2
        return RoleExplorationProviderPayload(
            items=[
                RoleExplorationProviderItem(
                    role_code=role_code,
                    level=ExplorationLevel.RECOMMENDED if index == 0 else ExplorationLevel.POSSIBLE,
                    reasons=["Synthetic fit grounded in supplied profile evidence"],
                    concerns=["Validate role-specific scope before applying"],
                    evidence_refs=[evidence_refs[index % len(evidence_refs)]],
                    preference_refs=[preference_refs[index % len(preference_refs)]],
                )
                for index, role_code in enumerate(self.order)
            ]
        )


def _synthetic_profile(db: Session, context: SyntheticContext) -> models.UserProfile:
    profile = models.UserProfile(status=ProfileStatus.CONFIRMED.value)
    profile.education = [
        models.Education(
            institution="Synthetic Institute",
            degree="BSc Information Systems",
            field_of_study="Applied Computing",
            evidence_text="Synthetic Institute BSc Information Systems",
            source_type="AI_EXTRACTED",
            raw_value="BSc Information Systems",
            canonical_value="BSc Information Systems",
        )
    ]
    # Include deterministic Office aliases and technical skills as normalized input.
    profile.skills = [
        models.ProfileSkill(name="Word", evidence_text="Word", source_type="AI_EXTRACTED", raw_value="Word", canonical_value="Word"),
        models.ProfileSkill(name="Excel", evidence_text="Excel", source_type="AI_EXTRACTED", raw_value="Excel", canonical_value="Excel"),
        models.ProfileSkill(name="PowerPoint", evidence_text="PPT", source_type="AI_EXTRACTED", raw_value="PPT", canonical_value="PowerPoint"),
        models.ProfileSkill(name="Python", evidence_text="Python", source_type="AI_EXTRACTED", raw_value="Python", canonical_value="Python"),
        models.ProfileSkill(name="SQL", evidence_text="SQL", source_type="AI_EXTRACTED", raw_value="SQL", canonical_value="SQL"),
    ]
    profile.experiences = [
        models.Experience(
            title="Synthetic workflow project",
            organization="Example Lab",
            description="Improved a fictional data workflow",
            experience_type="PROJECT",
            evidence_text="Synthetic workflow project",
            source_type="AI_EXTRACTED",
            raw_value="Synthetic workflow project",
            canonical_value="Synthetic workflow project",
        )
    ]
    # Explicit credential score is retained; no unsupported credential is supplied.
    profile.certifications = [
        models.Certification(
            name="CET-4",
            score="500",
            evidence_text="CET-4 500",
            source_type="AI_EXTRACTED",
            raw_value="CET-4 500",
            canonical_value="CET-4 500",
        )
    ]
    profile.career_preference = models.CareerPreference(
        priority_1=context.priorities[0].value,
        priority_2=context.priorities[1].value,
        weekly_hours=20,
    )
    db.add(profile)
    db.commit()
    db.refresh(profile)
    return profile


def _snapshot(profile: models.UserProfile) -> dict[str, Any]:
    def child_rows(collection: list[Any], fields: tuple[str, ...]) -> tuple[tuple[str, ...], ...]:
        return tuple(tuple(str(getattr(item, field, None)) for field in fields) for item in collection)

    preference = profile.career_preference
    return {
        "status": profile.status,
        "education": child_rows(profile.education, ("id", "institution", "degree", "canonical_value", "evidence_text", "source_type")),
        "skills": child_rows(profile.skills, ("id", "name", "canonical_value", "raw_value", "evidence_text", "source_type")),
        "experiences": child_rows(profile.experiences, ("id", "title", "canonical_value", "evidence_text", "source_type")),
        "certifications": child_rows(profile.certifications, ("id", "name", "score", "canonical_value", "evidence_text", "source_type")),
        "preferences": None
        if preference is None
        else (preference.priority_1, preference.priority_2, preference.weekly_hours),
    }


@pytest.mark.parametrize("context_spec", SYNTHETIC_CONTEXTS, ids=lambda item: item.name)
def test_synthetic_contexts_generate_grounded_six_roles_without_mutating_sources(
    db_session: Session, context_spec: SyntheticContext
) -> None:
    profile = _synthetic_profile(db_session, context_spec)
    before = _snapshot(profile)
    provider = _SyntheticProvider(context_spec.order)
    set_role_exploration_provider(provider)
    try:
        read = create_role_exploration(db_session, profile.id)
    finally:
        set_role_exploration_provider(None)

    assert read.profile_id == profile.id
    assert read.role_profile_version == ROLE_PROFILE_VERSION == "v1"
    items = read.result.items
    assert len(items) == 6
    assert len({item.role_code for item in items}) == 6
    assert {item.role_code for item in items} == set(RoleCode)
    assert {item.role_name for item in items} == {
        ROLE_PROFILE_BY_CODE[role_code].display_name for role_code in RoleCode
    }
    assert provider.contexts, "provider must receive the copied context"
    context = provider.contexts[0]
    assert [preference.value for preference in context.preferences] == list(context_spec.priorities)

    valid_evidence_ids = {UUID(row[0]) for row in before["education"] + before["skills"] + before["experiences"] + before["certifications"]}
    used_preferences: set[CareerPreferencePriority] = set()
    result_json = read.result.model_dump(mode="json")
    assert set(result_json) == {"role_profile_version", "items"}
    for item in items:
        assert set(item.model_dump(mode="json")) == {
            "role_code",
            "role_name",
            "level",
            "reasons",
            "concerns",
            "evidence_refs",
            "preference_refs",
        }
        assert item.evidence_refs
        assert set(item.evidence_refs) <= valid_evidence_ids
        used_preferences.update(item.preference_refs)
        assert not any(key in item.model_dump(mode="json") for key in ("probability", "percentage", "salary", "market"))
    assert used_preferences == set(context_spec.priorities)
    assert {fact.value for fact in context.facts if fact.kind == "skill"} >= {"Word", "Excel", "PowerPoint", "Python", "SQL"}
    assert any(fact.kind == "certification" and fact.value == "CET-4 500" for fact in context.facts)
    assert not any("unsupported" in fact.value.casefold() for fact in context.facts)
    assert not any("probability" in text.casefold() or "%" in text for item in items for text in (*item.reasons, *item.concerns))

    db_session.expire_all()
    persisted = db_session.get(models.UserProfile, profile.id)
    assert persisted is not None
    assert _snapshot(persisted) == before
