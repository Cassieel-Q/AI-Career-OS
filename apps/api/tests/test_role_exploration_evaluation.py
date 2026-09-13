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
    education_marker: str
    experience_marker: str
    technical_skills: tuple[str, ...]
    credential_marker: str
    office_aliases: bool = False


SYNTHETIC_CONTEXTS = (
    SyntheticContext(
        "product-operations-fast-entry",
        (CareerPreferencePriority.LESS_CODING, CareerPreferencePriority.FAST_EMPLOYMENT),
        tuple(reversed(tuple(RoleCode))),
        "Workflow Operations",
        "Operations workflow pilot",
        ("SQL", "Workflow Mapping"),
        "Workflow Foundations Certificate",
        True,
    ),
    SyntheticContext(
        "python-development-current-fit",
        (CareerPreferencePriority.CURRENT_FIT, CareerPreferencePriority.LESS_CODING),
        tuple(RoleCode)[2:] + tuple(RoleCode)[:2],
        "Python Application Development",
        "Python service prototype",
        ("Python", "FastAPI", "Git"),
        "Python Application Certificate",
    ),
    SyntheticContext(
        "algorithm-data-long-term-growth",
        (CareerPreferencePriority.LONG_TERM_GROWTH, CareerPreferencePriority.CURRENT_FIT),
        tuple(RoleCode),
        "Algorithmic Data Analytics",
        "Synthetic ranking-model study",
        ("Python", "SQL", "Statistics", "Pandas"),
        "Data Analytics Certificate",
    ),
)


UNSUPPORTED_CREDENTIAL_NAMES = (
    "PMP",
    "普通话二级甲等",
    "计算机二级",
    "Putonghua Level 2A",
    "Mandarin Proficiency Test Level 2-A",
    "Computer Rank Examination Level 2",
    "National Computer Rank Examination Level 2",
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
            institution=f"Synthetic {context.education_marker} Institute",
            degree="BSc Applied Computing",
            field_of_study=context.education_marker,
            dates="2020-2024",
            relevant_courses=[context.education_marker, "Synthetic Capstone"],
            evidence_text=f"Synthetic {context.education_marker} Institute {context.education_marker}",
            source_type="AI_EXTRACTED",
            raw_value=context.education_marker,
            canonical_value=context.education_marker,
            evidence_start=11,
            evidence_end=42,
        )
    ]
    # Include Office aliases for the operations context and context-specific technical skills.
    office_skills = (
        [
            models.ProfileSkill(name="Word", evidence_text="Word", source_type="AI_EXTRACTED", raw_value="Word", canonical_value="Word"),
            models.ProfileSkill(name="Excel", evidence_text="Excel", source_type="AI_EXTRACTED", raw_value="Excel", canonical_value="Excel"),
            models.ProfileSkill(name="PowerPoint", evidence_text="PPT", source_type="AI_EXTRACTED", raw_value="PPT", canonical_value="PowerPoint"),
        ]
        if context.office_aliases
        else []
    )
    profile.skills = office_skills + [
        models.ProfileSkill(
            name=skill,
            proficiency="PROJECT_READY" if skill in context.technical_skills else "BASIC",
            evidence_text=skill,
            source_type="AI_EXTRACTED",
            raw_value=skill,
            canonical_value=skill,
        )
        for skill in context.technical_skills
    ]
    profile.experiences = [
        models.Experience(
            title=context.experience_marker,
            organization=f"{context.education_marker} Example Lab",
            dates="2023-2024",
            description=f"Improved a fictional {context.experience_marker.casefold()} workflow",
            experience_type="PROJECT",
            evidence_text=context.experience_marker,
            source_type="AI_EXTRACTED",
            raw_value=context.experience_marker,
            canonical_value=context.experience_marker,
            evidence_start=51,
            evidence_end=80,
        )
    ]
    # Explicit scored CET-4 and a context-specific fictional credential are retained.
    profile.certifications = [
        models.Certification(
            name="CET-4",
            issuer="Synthetic Language Board",
            date="2024-06",
            score="500",
            status="PASSED",
            evidence_text="CET-4 500",
            source_type="AI_EXTRACTED",
            raw_value="CET-4 500",
            canonical_value="CET-4 500",
        ),
        models.Certification(
            name=context.credential_marker,
            issuer=f"{context.education_marker} Institute",
            date="2024-07",
            score="PASS",
            status="COMPLETED",
            evidence_text=context.credential_marker,
            source_type="AI_EXTRACTED",
            raw_value=context.credential_marker,
            canonical_value=context.credential_marker,
        ),
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
        "education": child_rows(
            profile.education,
            (
                "id",
                "institution",
                "degree",
                "field_of_study",
                "dates",
                "relevant_courses",
                "evidence_text",
                "source_type",
                "raw_value",
                "canonical_value",
                "evidence_start",
                "evidence_end",
            ),
        ),
        "skills": child_rows(
            profile.skills,
            (
                "id",
                "name",
                "proficiency",
                "evidence_text",
                "source_type",
                "raw_value",
                "canonical_value",
                "evidence_start",
                "evidence_end",
            ),
        ),
        "experiences": child_rows(
            profile.experiences,
            (
                "id",
                "title",
                "organization",
                "dates",
                "description",
                "experience_type",
                "evidence_text",
                "source_type",
                "raw_value",
                "canonical_value",
                "evidence_start",
                "evidence_end",
            ),
        ),
        "certifications": child_rows(
            profile.certifications,
            (
                "id",
                "name",
                "issuer",
                "date",
                "score",
                "status",
                "evidence_text",
                "source_type",
                "raw_value",
                "canonical_value",
                "evidence_start",
                "evidence_end",
            ),
        ),
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
    context_values = {fact.value for fact in context.facts}
    assert context_spec.education_marker in context_values
    assert context_spec.experience_marker in context_values
    assert context_spec.credential_marker in context_values
    assert set(context_spec.technical_skills) <= context_values
    if context_spec.office_aliases:
        # Office aliases must be canonicalized (including PPT -> PowerPoint) when present.
        assert {"Word", "Excel", "PowerPoint"} <= {
            fact.value for fact in context.facts if fact.kind == "skill"
        }
        assert not any(fact.value == "PPT" for fact in context.facts if fact.kind == "skill")

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
    skill_values = {fact.value for fact in context.facts if fact.kind == "skill"}
    assert set(context_spec.technical_skills) <= skill_values
    assert any(fact.kind == "certification" and fact.value == "CET-4 500" for fact in context.facts)
    provider_blob = "\n".join(f"{fact.kind}:{fact.value}" for fact in context.facts).casefold()
    result_blob = str(result_json).casefold()
    for credential_name in UNSUPPORTED_CREDENTIAL_NAMES:
        assert credential_name.casefold() not in provider_blob
        assert credential_name.casefold() not in result_blob
    assert not any("unsupported" in fact.value.casefold() for fact in context.facts)
    assert not any("probability" in text.casefold() or "%" in text for item in items for text in (*item.reasons, *item.concerns))
    for item in items:
        item_text = " ".join((*item.reasons, *item.concerns)).casefold()
        for credential_name in UNSUPPORTED_CREDENTIAL_NAMES:
            assert credential_name.casefold() not in item_text

    db_session.expire_all()
    persisted = db_session.get(models.UserProfile, profile.id)
    assert persisted is not None
    assert _snapshot(persisted) == before
