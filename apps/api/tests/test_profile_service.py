import pytest
from pydantic import ValidationError

from app.profile_schemas import ProfileSkillInput


def test_proficiency_is_unset_by_default() -> None:
    skill = ProfileSkillInput(name="Python")

    assert skill.proficiency is None


def test_invalid_proficiency_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileSkillInput(name="Python", proficiency="EXPERT")


def test_user_entered_fact_may_omit_evidence() -> None:
    skill = ProfileSkillInput(name="SQL", source_type="USER_ENTERED")

    assert skill.evidence_text is None


def test_ai_extracted_fact_requires_evidence() -> None:
    with pytest.raises(ValidationError):
        ProfileSkillInput(name="Python", source_type="AI_EXTRACTED")


def test_blank_primary_name_is_rejected() -> None:
    with pytest.raises(ValidationError):
        ProfileSkillInput(name="   ")
