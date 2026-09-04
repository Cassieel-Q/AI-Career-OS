from __future__ import annotations

from io import BytesIO

import fitz
from fastapi.testclient import TestClient

from app import main
from app.main import process_resume_extraction
from app.resume_normalization import normalize_resume_extraction
from app.resume_schemas import ResumeExtractionResult


def test_grounding_uses_raw_value_before_canonicalization() -> None:
    result = ResumeExtractionResult(skills=[{"name": "PPT", "evidence_text": "PPT"}])

    processed = process_resume_extraction(result, "PPT")

    assert processed.result.skills[0].raw_value == "PPT"
    assert processed.result.skills[0].name == "PowerPoint"
    assert processed.result.skills[0].canonical_value == "PowerPoint"
    assert processed.result.skills[0].evidence_text == "PPT"


def test_one_unsupported_item_is_quarantined_without_discarding_grounded_items() -> None:
    result = ResumeExtractionResult(
        skills=[
            {"name": "Python", "evidence_text": "Python"},
            {"name": "Unicorn Stack", "evidence_text": "Unicorn Stack"},
            {"name": "SQL", "evidence_text": "SQL"},
            {"name": "FastAPI", "evidence_text": "FastAPI"},
        ]
    )

    processed = process_resume_extraction(result, "Python SQL FastAPI")

    assert [skill.name for skill in processed.result.skills] == ["Python", "SQL", "FastAPI"]
    assert [warning.code for warning in processed.warnings] == ["UNSUPPORTED_FACT"]
    assert processed.warnings[0].category == "skill"


def test_non_empty_campus_section_is_reported_when_initial_output_omits_it() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    processed = process_resume_extraction(
        result,
        "专业技能\nPython\n\n校园经历\n学生会干事\n",
        allow_repair=False,
    )

    assert "MISSING_SECTION_CONTENT:CAMPUS" in processed.completeness_warnings


def test_targeted_campus_repair_uses_only_the_campus_section() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "CAMPUS"
            assert section_text == "校园经历\n学生会干事"
            return ResumeExtractionResult(
                experiences=[
                    {
                        "title": "学生会干事",
                        "source_section": "校园经历",
                        "evidence_text": "学生会干事",
                    }
                ]
            )

    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    processed = process_resume_extraction(
        result,
        "专业技能\nPython\n\n校园经历\n学生会干事",
        provider=Provider(),
    )

    assert processed.result.experiences[0].title == "学生会干事"
    assert processed.result.experiences[0].experience_type == "CAMPUS"
    assert "MISSING_SECTION_CONTENT:CAMPUS" not in processed.completeness_warnings


def test_targeted_repair_cannot_import_a_fact_outside_the_source_section() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "CAMPUS"
            return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    result = ResumeExtractionResult(skills=[{"name": "SQL", "evidence_text": "SQL"}])

    processed = process_resume_extraction(
        result,
        "专业技能\nSQL\n\n校园经历\n学生会干事",
        provider=Provider(),
    )

    assert [skill.name for skill in processed.result.skills] == ["SQL"]
    assert any(warning.code == "UNSUPPORTED_FACT" for warning in processed.warnings)
    assert "MISSING_SECTION_CONTENT:CAMPUS" in processed.completeness_warnings


def test_credential_score_is_preserved_without_inferred_pass_fail_status() -> None:
    result = ResumeExtractionResult(
        certifications=[{"name": "CET-6 300", "evidence_text": "CET-6 300"}]
    )

    normalized = normalize_resume_extraction(result)

    assert normalized.certifications[0].name == "CET-6"
    assert normalized.certifications[0].score == "300"
    assert normalized.certifications[0].status is None


def test_office_tools_are_atomic_and_generic_office_software_is_not_invented() -> None:
    explicit = normalize_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Word、Excel、PPT", "evidence_text": "Word、Excel、PPT"}])
    )
    generic = normalize_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "办公软件", "evidence_text": "办公软件"}])
    )

    assert [skill.name for skill in explicit.skills] == ["Word", "Excel", "PowerPoint"]
    assert [skill.name for skill in generic.skills] == ["办公软件"]


def test_language_ability_is_not_promoted_to_a_credential() -> None:
    normalized = normalize_resume_extraction(
        ResumeExtractionResult(
            certifications=[{"name": "英语读写能力", "evidence_text": "英语读写能力"}],
        )
    )

    assert [skill.name for skill in normalized.skills] == ["English"]
    assert normalized.certifications == []


def test_unsupported_facts_never_persist_in_created_profile() -> None:
    class Provider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(
                skills=[
                    {"name": "Python", "evidence_text": "Python"},
                    {"name": "SQL", "evidence_text": "SQL"},
                    {"name": "FastAPI", "evidence_text": "FastAPI"},
                    {"name": "Unicorn Stack", "evidence_text": "Unicorn Stack"},
                ]
            )

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Python SQL FastAPI")
    pdf = document.tobytes()
    document.close()
    main.set_resume_provider(Provider())
    try:
        response = TestClient(main.app).post(
            "/api/v1/resumes",
            files={"file": ("resume.pdf", BytesIO(pdf), "application/pdf")},
        )
    finally:
        main.set_resume_provider(None)

    assert response.status_code == 200, response.text
    assert [skill["name"] for skill in response.json()["skills"]] == ["Python", "SQL", "FastAPI"]
