import pytest

from app.main import validate_evidence_trace
from app.resume_normalization import normalize_resume_extraction
from app.resume_schemas import ResumeExtractionResult


def test_office_skill_bundle_is_split_and_canonicalized_with_source_evidence() -> None:
    result = ResumeExtractionResult(
        skills=[
            {
                "name": "Word、Excel、PPT",
                "evidence_text": "专业技能：Word、Excel、PPT",
            }
        ]
    )

    normalized = normalize_resume_extraction(result)
    validate_evidence_trace(normalized, "专业技能：Word、Excel、PPT")

    assert [skill.name for skill in normalized.skills] == ["Word", "Excel", "PowerPoint"]
    assert all(skill.evidence_text == "专业技能：Word、Excel、PPT" for skill in normalized.skills)


def test_section_aware_fields_and_language_classification_are_normalized() -> None:
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "Example University",
                "field_of_study": "Computer Science",
                "relevant_courses": ["Machine Learning", "Database Systems"],
                "evidence_text": (
                    "教育背景 Example University Computer Science "
                    "主修课程：Machine Learning、Database Systems"
                ),
            }
        ],
        experiences=[
            {
                "title": "Student Union Minister",
                "source_section": "校园经历",
                "experience_type": "WORK",
                "evidence_text": "校园经历 Student Union Minister",
            }
        ],
        skills=[
            {"name": "English communication ability", "evidence_text": "语言能力：English communication ability"},
            {"name": "CET-6", "evidence_text": "证书：CET-6"},
        ],
    )

    normalized = normalize_resume_extraction(result)

    assert normalized.education[0].relevant_courses == ["Machine Learning", "Database Systems"]
    assert normalized.experiences[0].experience_type == "CAMPUS"
    assert [skill.name for skill in normalized.skills] == ["English"]
    assert [certification.name for certification in normalized.certifications] == ["CET-6"]
    validate_evidence_trace(
        normalized,
        (
            "教育背景 Example University Computer Science 主修课程：Machine Learning、Database Systems "
            "校园经历 Student Union Minister 语言能力：English communication ability 证书：CET-6"
        ),
    )


def test_generic_language_ability_is_not_treated_as_a_credential() -> None:
    result = ResumeExtractionResult(
        skills=[],
        certifications=[
            {"name": "普通话沟通良好", "evidence_text": "语言能力：普通话沟通良好"},
        ],
    )

    normalized = normalize_resume_extraction(result)

    assert [skill.name for skill in normalized.skills] == ["普通话"]
    assert normalized.certifications == []


def test_arbitrary_prose_is_not_split_into_fake_skills() -> None:
    result = ResumeExtractionResult(
        skills=[{"name": "data analysis and reporting", "evidence_text": "data analysis and reporting"}]
    )

    normalized = normalize_resume_extraction(result)

    assert [skill.name for skill in normalized.skills] == ["data analysis and reporting"]


@pytest.mark.parametrize(
    ("raw_name", "canonical_name"),
    [("PPT", "PowerPoint"), ("Microsoft PowerPoint", "PowerPoint"), ("Excel", "Excel")],
)
def test_office_aliases_have_one_canonical_name(raw_name: str, canonical_name: str) -> None:
    result = ResumeExtractionResult(skills=[{"name": raw_name, "evidence_text": raw_name}])

    normalized = normalize_resume_extraction(result)

    assert [skill.name for skill in normalized.skills] == [canonical_name]
