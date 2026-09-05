from __future__ import annotations

from io import BytesIO
import logging
import sys
from types import SimpleNamespace

import fitz
import pytest
from fastapi.testclient import TestClient

from app import main
from app.main import process_resume_extraction
from app.resume_normalization import normalize_resume_extraction
from app.resume_schemas import ResumeExtractionResult
from app.resume_sections import detect_sections


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


def test_single_unsupported_skill_does_not_abort_a_usable_extraction() -> None:
    result = ResumeExtractionResult(
        skills=[
            {"name": "Python", "evidence_text": "Python"},
            {"name": "Unicorn Stack", "evidence_text": "Unicorn Stack"},
        ]
    )

    processed = process_resume_extraction(result, "Python")

    assert [skill.name for skill in processed.result.skills] == ["Python"]
    assert len(processed.warnings) == 1
    assert processed.warnings[0].reason == "evidence_not_in_source"


def test_unsupported_certification_and_experience_are_quarantined_individually() -> None:
    result = ResumeExtractionResult(
        skills=[{"name": "Python", "evidence_text": "Python"}],
        experiences=[{"title": "Fabricated role", "evidence_text": "Fabricated role"}],
        certifications=[{"name": "CET-6", "evidence_text": "CET-6"}],
    )

    processed = process_resume_extraction(result, "Python")

    assert [skill.name for skill in processed.result.skills] == ["Python"]
    assert processed.result.experiences == []
    assert processed.result.certifications == []
    assert {(warning.category, warning.reason) for warning in processed.warnings} == {
        ("experience", "evidence_not_in_source"),
        ("certification", "evidence_not_in_source"),
    }


def test_non_empty_campus_section_is_reported_when_initial_output_omits_it() -> None:
    result = ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

    processed = process_resume_extraction(
        result,
        "专业技能\nPython\n\n校园经历\n学生会干事\n",
        allow_repair=False,
    )

    assert "MISSING_SECTION_CONTENT:CAMPUS" in processed.completeness_warnings


def test_campus_experience_does_not_satisfy_a_non_empty_work_section() -> None:
    source = "校园经历\n学生会干事\n\n工作经历\nBackend Engineer"
    result = ResumeExtractionResult(
        experiences=[
            {
                "title": "学生会干事",
                "experience_type": "CAMPUS",
                "source_section": "校园经历",
                "evidence_text": "学生会干事",
            }
        ]
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert "MISSING_SECTION_CONTENT:EXPERIENCE" in processed.completeness_warnings


def test_grounded_work_experience_satisfies_work_without_a_false_missing_warning() -> None:
    source = "校园经历\n学生会干事\n\n工作经历\nBackend Engineer"
    result = ResumeExtractionResult(
        experiences=[
            {
                "title": "学生会干事",
                "experience_type": "CAMPUS",
                "source_section": "校园经历",
                "evidence_text": "学生会干事",
            },
            {
                "title": "Backend Engineer",
                "experience_type": "WORK",
                "source_section": "工作经历",
                "evidence_text": "Backend Engineer",
            },
        ]
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert "MISSING_SECTION_CONTENT:CAMPUS" not in processed.completeness_warnings
    assert "MISSING_SECTION_CONTENT:EXPERIENCE" not in processed.completeness_warnings


def test_internship_section_with_only_campus_result_triggers_targeted_repair() -> None:
    source = "校园经历\n学生会干事\n\n实习经历\nData Intern"

    class Provider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            self.calls.append(section_label)
            assert section_label == "EXPERIENCE"
            assert section_text == "实习经历\nData Intern"
            return ResumeExtractionResult(
                experiences=[
                    {
                        "title": "Data Intern",
                        "experience_type": "INTERNSHIP",
                        "evidence_text": "Data Intern",
                    }
                ]
            )

    provider = Provider()
    processed = process_resume_extraction(
        ResumeExtractionResult(
            experiences=[
                {
                    "title": "学生会干事",
                    "experience_type": "CAMPUS",
                    "source_section": "校园经历",
                    "evidence_text": "学生会干事",
                }
            ]
        ),
        source,
        provider=provider,
    )

    assert provider.calls == ["EXPERIENCE"]
    assert [item.title for item in processed.result.experiences] == ["学生会干事", "Data Intern"]
    assert "MISSING_SECTION_CONTENT:EXPERIENCE" not in processed.completeness_warnings


def test_project_section_is_not_satisfied_by_unrelated_work_experience() -> None:
    source = "项目经历\nProject Alpha\n\n工作经历\nBackend Engineer"
    result = ResumeExtractionResult(
        experiences=[
            {
                "title": "Backend Engineer",
                "experience_type": "WORK",
                "source_section": "工作经历",
                "evidence_text": "Backend Engineer",
            }
        ]
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert "MISSING_SECTION_CONTENT:EXPERIENCE" in processed.completeness_warnings


def test_combined_internship_work_heading_accepts_either_compatible_type() -> None:
    source = "实习/工作经历\nData Intern"
    result = ResumeExtractionResult(
        experiences=[
            {
                "title": "Data Intern",
                "experience_type": "INTERNSHIP",
                "source_section": "实习/工作经历",
                "evidence_text": "Data Intern",
            }
        ]
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert "MISSING_SECTION_CONTENT:EXPERIENCE" not in processed.completeness_warnings


@pytest.mark.parametrize(
    ("section_key", "attempt", "expected_stage"),
    [
        ("EDUCATION", 1, "education_repair_1"),
        ("EDUCATION", 2, "education_repair_2"),
        ("EXPERIENCE", 1, "experience_repair"),
        ("CAMPUS", 1, "campus_repair"),
        ("SKILLS", 1, "other_section_repair"),
    ],
)
def test_repair_stage_names_are_explicit_and_bounded(
    section_key: str,
    attempt: int,
    expected_stage: str,
) -> None:
    assert main._experience_repair_stage(section_key, attempt) == expected_stage


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


def test_each_missing_top_level_section_gets_one_grounded_targeted_repair() -> None:
    source = "教育背景\nAcademic record\n\n专业技能\nPython\n\n工作经历\nBackend Intern"

    class Provider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            self.calls.append(section_label)
            if section_label == "EDUCATION":
                return ResumeExtractionResult(
                    education=[{"institution": "Academic record", "evidence_text": "Academic record"}]
                )
            if section_label == "SKILLS":
                return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])
            if section_label == "EXPERIENCE":
                return ResumeExtractionResult(
                experiences=[
                        {
                            "title": "Backend Intern",
                            "experience_type": "WORK",
                            "evidence_text": "Backend Intern",
                        }
                    ]
                )
            raise AssertionError(f"unexpected section: {section_label}")

    provider = Provider()
    processed = process_resume_extraction(ResumeExtractionResult(), source, provider=provider)

    assert [item.institution for item in processed.result.education] == ["Academic record"]
    assert [item.name for item in processed.result.skills] == ["Python"]
    assert [item.title for item in processed.result.experiences] == ["Backend Intern"]
    assert set(provider.calls) == {"EDUCATION", "SKILLS", "EXPERIENCE"}
    assert len(provider.calls) == 3
    assert processed.completeness_warnings == []


@pytest.mark.parametrize(
    ("heading", "expected_key"),
    [
        ("教育背景", "EDUCATION"),
        ("教育经历", "EDUCATION"),
        ("学历信息", "EDUCATION"),
        ("工作经历", "EXPERIENCE"),
        ("实习经历", "EXPERIENCE"),
        ("实习/工作经历", "EXPERIENCE"),
        ("工作/实习经历", "EXPERIENCE"),
        ("校园经历", "CAMPUS"),
        ("项目经历", "EXPERIENCE"),
        ("专业技能", "SKILLS"),
        ("技能", "SKILLS"),
        ("技能特长", "SKILLS"),
        ("个人技能", "SKILLS"),
        ("职业技能", "SKILLS"),
        ("证书", "CREDENTIALS"),
        ("资格证书", "CREDENTIALS"),
        ("技能证书", "CREDENTIALS"),
        ("语言证书", "CREDENTIALS"),
        ("主修课程", "COURSES"),
        ("核心课程", "COURSES"),
        ("相关课程", "COURSES"),
    ],
)
def test_explicit_top_level_heading_aliases_are_detected(heading: str, expected_key: str) -> None:
    sections = detect_sections(f"{heading}\nGrounded content")

    assert [(section.key, section.heading) for section in sections] == [(expected_key, heading)]


def test_empty_targeted_repair_surfaces_structured_partial_result_warning() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            return ResumeExtractionResult()

    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\nAcademic record\n\n专业技能\nPython",
        provider=Provider(),
    )

    assert processed.result.education == []
    assert [skill.name for skill in processed.result.skills] == ["Python"]
    assert "MISSING_SECTION_CONTENT:EDUCATION" in processed.completeness_warnings
    assert any(
        warning.code == "EDUCATION_EXTRACTION_INCOMPLETE"
        and warning.category == "education"
        for warning in processed.warnings
    )


def test_first_pass_education_is_retained_without_repair() -> None:
    source = "教育背景\nXX大学 工商管理\n\n专业技能\nPython"
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "XX大学",
                "field_of_study": "工商管理",
                "evidence_text": "XX大学 工商管理",
            }
        ],
        skills=[{"name": "Python", "evidence_text": "Python"}],
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert processed.result.education[0].institution == "XX大学"
    assert processed.result.education[0].field_of_study == "工商管理"
    assert processed.completeness_warnings == []


def test_empty_first_education_repair_gets_one_final_education_only_retry() -> None:
    source = "教育背景\nXXU 工商管理\n\n专业技能\nPython"

    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            self.calls += 1
            if self.calls == 1:
                return ResumeExtractionResult()
            return ResumeExtractionResult(
                education=[
                    {
                        "institution": "XXU",
                        "field_of_study": "工商管理",
                        "evidence_text": "XXU 工商管理",
                    }
                ]
            )

    provider = Provider()
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        provider=provider,
    )

    assert provider.calls == 2
    assert [item.institution for item in processed.result.education] == ["XXU"]
    assert processed.completeness_warnings == []
    assert any(warning.code == "EDUCATION_FIRST_PASS_EMPTY" for warning in processed.warnings)
    assert any(warning.code == "EDUCATION_REPAIR_EMPTY" for warning in processed.warnings)


def test_partial_education_record_preserves_grounded_fields_and_rejects_unsupported_degree() -> None:
    source = "教育背景\nXX大学 工商管理\n\n专业技能\nPython"
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "XX大学",
                "degree": "博士",
                "field_of_study": "工商管理",
                "evidence_text": "XX大学 工商管理",
            }
        ],
        skills=[{"name": "Python", "evidence_text": "Python"}],
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    education = processed.result.education[0]
    assert education.institution == "XX大学"
    assert education.field_of_study == "工商管理"
    assert education.degree is None


def test_education_optional_field_must_be_in_the_education_evidence() -> None:
    source = "教育背景\nXX大学 工商管理\n\n工作经历\n博士"
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "XX大学",
                "degree": "博士",
                "evidence_text": "XX大学 工商管理",
            }
        ]
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert processed.result.education[0].institution == "XX大学"
    assert processed.result.education[0].degree is None
    assert any(
        warning.category == "education.degree" and warning.reason == "field_not_in_evidence"
        for warning in processed.warnings
    )


def test_targeted_education_evidence_offsets_are_absolute_to_the_resume() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            return ResumeExtractionResult(
                education=[
                    {
                        "institution": "Academic record",
                        "field_of_study": "Business Administration",
                        "evidence_text": "Academic record Business Administration",
                    }
                ]
            )

    source = "姓名\nAlice\n\nEducation\nAcademic record Business Administration\n\nSkills\nPython"
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        provider=Provider(),
    )

    education = processed.result.education[0]
    assert education.evidence_start is not None
    assert education.evidence_end is not None
    assert source[education.evidence_start : education.evidence_end] == education.evidence_text
    assert education.evidence_start == source.index("Academic record Business Administration")


def test_unresolvable_repair_evidence_offsets_fail_closed() -> None:
    source = "Education\nExample University"
    section = detect_sections(source)[0]
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "Missing University",
                "evidence_text": "Missing University",
                "evidence_start": 4,
                "evidence_end": 21,
            }
        ]
    )

    rebased = main._rebase_section_evidence(result, source, section)

    assert rebased.education[0].evidence_start is None
    assert rebased.education[0].evidence_end is None


def test_repeated_education_merge_preserves_optional_fields_and_courses() -> None:
    base = ResumeExtractionResult(
        education=[
            {
                "institution": "XX大学",
                "evidence_text": "XX大学",
                "relevant_courses": ["数学"],
            }
        ]
    )
    repair = ResumeExtractionResult(
        education=[
            {
                "institution": "XX大学",
                "degree": "本科",
                "field_of_study": "工商管理",
                "evidence_text": "XX大学 工商管理",
                "relevant_courses": ["统计学"],
            }
        ]
    )

    merged = main._merge_repair(base, repair, "EDUCATION", "教育背景")

    assert len(merged.education) == 1
    assert merged.education[0].degree == "本科"
    assert merged.education[0].field_of_study == "工商管理"
    assert merged.education[0].relevant_courses == ["数学", "统计学"]
    assert merged.education[0].evidence_text == "XX大学 工商管理"


def test_ungrounded_education_repair_has_redacted_stage_diagnostic() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            return ResumeExtractionResult(
                education=[{"institution": "Fabricated University", "evidence_text": "not in source"}]
            )

    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\nXXU\n\n专业技能\nPython",
        provider=Provider(),
    )

    assert processed.result.education == []
    assert any(warning.code == "EDUCATION_REPAIR_UNGROUNDED" for warning in processed.warnings)
    education_diagnostics = [
        warning
        for warning in processed.warnings
        if warning.code.startswith("EDUCATION_")
    ]
    assert education_diagnostics
    assert all("XXU" not in warning.evidence_text for warning in education_diagnostics)
    assert all("XXU" not in warning.raw_value for warning in education_diagnostics)


def test_exhausted_education_repairs_surface_incomplete_diagnostic() -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls = 0

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            self.calls += 1
            return ResumeExtractionResult()

    provider = Provider()
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\nXXU\n\n专业技能\nPython",
        provider=provider,
    )

    assert provider.calls == 2
    assert processed.result.education == []
    assert any(warning.code == "EDUCATION_EXTRACTION_INCOMPLETE" for warning in processed.warnings)


def test_repaired_education_survives_api_serialization() -> None:
    class Provider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}])

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            assert section_label == "EDUCATION"
            return ResumeExtractionResult(
                education=[
                    {
                        "institution": "Academic record",
                        "degree": "PhD",
                        "field_of_study": "Business Administration",
                        "evidence_text": "Academic record Business Administration",
                    }
                ]
            )

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Education\nAcademic record Business Administration\nSkills\nPython")
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
    assert response.json()["education"][0]["institution"] == "Academic record"
    assert response.json()["education"][0]["field_of_study"] == "Business Administration"
    assert response.json()["education"][0]["degree"] is None


def test_explicit_institution_is_recovered_without_an_extra_llm_call() -> None:
    class Provider:
        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            raise AssertionError("deterministic institution recovery should run first")

    source = "教育背景\n北京大学\n\n专业技能\nPython"
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        provider=Provider(),
    )

    assert [item.institution for item in processed.result.education] == ["北京大学"]
    assert any(warning.code == "INSTITUTION_RECOVERED" for warning in processed.warnings)


def test_recovered_institution_uses_an_exact_absolute_source_span() -> None:
    source = "姓名\nAlice\n\n教育背景\n北京大学\n\n专业技能\nPython"

    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        allow_repair=False,
    )

    education = processed.result.education[0]
    assert education.institution == "北京大学"
    assert education.evidence_start is not None
    assert education.evidence_end is not None
    assert source[education.evidence_start : education.evidence_end] == "北京大学"


@pytest.mark.parametrize(
    "institution",
    [
        "北京职业技术学院",
        "中国科学院",
        "Example College",
        "Example Institute",
        "Example School",
        "University of Oxford",
    ],
)
def test_explicit_institution_suffix_variants_are_supported(institution: str) -> None:
    source = f"Education\n{institution}\n\nSkills\nPython"
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        allow_repair=False,
    )

    assert [item.institution for item in processed.result.education] == [institution]


@pytest.mark.parametrize(
    ("education_line", "institution"),
    [
        ("毕业院校北京大学", "北京大学"),
        ("就读北京大学", "北京大学"),
        ("(北京大学)", "北京大学"),
    ],
)
def test_institution_recovery_strips_only_known_context_and_punctuation(
    education_line: str,
    institution: str,
) -> None:
    source = f"教育背景\n{education_line}\n\n专业技能\nPython"
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        source,
        allow_repair=False,
    )

    assert [item.institution for item in processed.result.education] == [institution]
    education = processed.result.education[0]
    assert source[education.evidence_start : education.evidence_end] == institution


def test_recovered_institution_merges_grounded_partial_education_fields() -> None:
    source = "教育背景\n北京大学 本科 工商管理 2020-2024 主修课程：数据结构\n\n专业技能\nPython"
    result = ResumeExtractionResult(
        education=[
            {
                "institution": "Fabricated University",
                "degree": "本科",
                "field_of_study": "工商管理",
                "dates": "2020-2024",
                "relevant_courses": ["数据结构"],
                "evidence_text": "本科 工商管理 2020-2024 主修课程：数据结构",
            }
        ],
        skills=[{"name": "Python", "evidence_text": "Python"}],
    )

    processed = process_resume_extraction(result, source, allow_repair=False)

    education = processed.result.education[0]
    assert education.institution == "北京大学"
    assert education.degree == "本科"
    assert education.field_of_study == "工商管理"
    assert education.dates == "2020-2024"
    assert education.relevant_courses == ["数据结构"]
    assert source[education.evidence_start : education.evidence_end] == education.evidence_text


def test_no_school_like_token_does_not_invent_an_institution() -> None:
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\n2020-2024 工商管理\n\n专业技能\nPython",
        allow_repair=False,
    )

    assert processed.result.education == []
    assert any(warning.code == "INSTITUTION_NOT_EXTRACTED" for warning in processed.warnings)


def test_multiple_school_candidates_are_reported_as_ambiguous_without_a_guess() -> None:
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\n北京大学 / 清华大学\n\n专业技能\nPython",
        allow_repair=False,
    )

    assert processed.result.education == []
    assert any(warning.code == "INSTITUTION_RECOVERY_AMBIGUOUS" for warning in processed.warnings)


def test_institution_outside_education_section_is_not_recovered() -> None:
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\n工商管理\n\n工作经历\n北京大学\n\n专业技能\nPython",
        allow_repair=False,
    )

    assert processed.result.education == []
    assert any(warning.code == "INSTITUTION_NOT_EXTRACTED" for warning in processed.warnings)


def test_ungrounded_institution_gets_a_distinct_recovery_diagnostic() -> None:
    processed = process_resume_extraction(
        ResumeExtractionResult(
            education=[{"institution": "清华大学", "evidence_text": "清华大学"}],
            skills=[{"name": "Python", "evidence_text": "Python"}],
        ),
        "教育背景\n北京大学\n\n专业技能\nPython",
        allow_repair=False,
    )

    assert [item.institution for item in processed.result.education] == ["北京大学"]
    assert any(warning.code == "INSTITUTION_NOT_GROUNDED" for warning in processed.warnings)
    assert any(warning.code == "INSTITUTION_RECOVERED" for warning in processed.warnings)


def test_openai_provider_uses_bounded_timeout_and_retry_defaults(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_MAX_RETRIES", raising=False)

    main.OpenAIResumeProvider()

    assert captured["timeout"] == 30.0
    assert captured["max_retries"] == 0


def test_openai_provider_reads_timeout_and_retry_overrides(monkeypatch) -> None:
    captured: dict[str, object] = {}

    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            captured.update(kwargs)

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "12.5")
    monkeypatch.setenv("OPENAI_MAX_RETRIES", "2")

    main.OpenAIResumeProvider()

    assert captured["timeout"] == 12.5
    assert captured["max_retries"] == 2


@pytest.mark.parametrize(
    ("variable", "value"),
    [
        ("OPENAI_TIMEOUT_SECONDS", "0"),
        ("OPENAI_TIMEOUT_SECONDS", "121"),
        ("OPENAI_TIMEOUT_SECONDS", "nan"),
        ("OPENAI_TIMEOUT_SECONDS", "not-a-number"),
        ("OPENAI_MAX_RETRIES", "-1"),
        ("OPENAI_MAX_RETRIES", "3"),
        ("OPENAI_MAX_RETRIES", "not-a-number"),
    ],
)
def test_openai_provider_rejects_invalid_timeout_or_retry_config(monkeypatch, variable: str, value: str) -> None:
    class FakeOpenAI:
        def __init__(self, **kwargs: object) -> None:
            pass

    monkeypatch.setitem(sys.modules, "openai", SimpleNamespace(OpenAI=FakeOpenAI))
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv(variable, value)

    with pytest.raises(ValueError, match=variable):
        main.OpenAIResumeProvider()


def test_resume_repair_calls_obey_the_total_llm_budget() -> None:
    class Provider:
        def __init__(self) -> None:
            self.calls: list[str] = []

        def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
            self.calls.append(section_label)
            return ResumeExtractionResult()

    provider = Provider()
    processed = process_resume_extraction(
        ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
        "教育背景\n工商管理\n\n校园经历\n学生会干事\n\n工作经历\n工程师\n\n专业技能\nPython\n\n证书\nCET-6",
        provider=provider,
        initial_llm_calls=1,
    )

    assert len(provider.calls) == 4
    assert processed.total_llm_calls == 5
    assert any(warning.code == "SECTION_REPAIR_BUDGET_EXHAUSTED" for warning in processed.warnings)


def test_initial_llm_call_count_cannot_start_above_the_resume_budget() -> None:
    with pytest.raises(ValueError, match="initial_llm_calls"):
        process_resume_extraction(
            ResumeExtractionResult(skills=[{"name": "Python", "evidence_text": "Python"}]),
            "Python",
            initial_llm_calls=main.MAX_LLM_CALLS_PER_RESUME + 1,
        )


def test_resume_timing_diagnostics_are_redacted(caplog) -> None:
    source = "Example University resume text"
    class Provider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(
                education=[{"institution": "Example University", "evidence_text": "Example University"}],
                skills=[{"name": "resume-secret", "evidence_text": "resume-secret"}],
            )

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), source)
    pdf = document.tobytes()
    document.close()
    main.set_resume_provider(Provider())
    try:
        with caplog.at_level(logging.INFO, logger=main.logger.name):
            response = TestClient(main.app).post(
                "/api/v1/resumes",
                files={"file": ("resume.pdf", BytesIO(pdf), "application/pdf")},
            )
    finally:
        main.set_resume_provider(None)

    assert response.status_code == 200, response.text
    timing_logs = [record.getMessage() for record in caplog.records if "resume_timing" in record.getMessage()]
    assert timing_logs
    timing_log = timing_logs[-1]
    for field_name in (
        "pdf_extract_ms",
        "initial_llm_ms",
        "education_repair_1_ms",
        "education_repair_2_ms",
        "other_section_repair_ms",
        "grounding_normalization_ms",
        "db_persist_ms",
        "total_resume_ms",
        "total_llm_calls",
    ):
        assert field_name in timing_log
    assert source not in timing_log
    assert "resume-secret" not in timing_log
    assert all(source not in record.getMessage() for record in caplog.records)
    assert all("resume-secret" not in record.getMessage() for record in caplog.records)


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


def test_explicit_office_tools_and_credentials_are_recovered_when_llm_is_incomplete() -> None:
    source = "专业技能：Word、Excel、PPT 等办公软件\n证书：CET-4 500；CET-6 300；普通话二级甲等"
    result = ResumeExtractionResult(skills=[{"name": "办公软件", "evidence_text": "办公软件"}])

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert [skill.name for skill in processed.result.skills] == ["Word", "Excel", "PowerPoint"]
    assert [certification.name for certification in processed.result.certifications] == [
        "CET-4",
        "CET-6",
        "普通话二级甲等",
    ]
    assert [certification.score for certification in processed.result.certifications] == ["500", "300", None]
    assert all(certification.status is None for certification in processed.result.certifications)


def test_explicit_recovery_uses_real_source_spans() -> None:
    source = "专业技能：Word、Excel、PPT 等办公软件\n证书：CET-4 500"

    processed = process_resume_extraction(ResumeExtractionResult(), source, allow_repair=False)

    office = {skill.name: skill for skill in processed.result.skills}
    assert office["PowerPoint"].evidence_text == "PPT"
    assert source[office["PowerPoint"].evidence_start : office["PowerPoint"].evidence_end] == "PPT"
    credential = processed.result.certifications[0]
    assert credential.evidence_text == "CET-4 500"
    assert source[credential.evidence_start : credential.evidence_end] == "CET-4 500"


def test_office_aliases_are_recovered_from_the_skills_section() -> None:
    source = "专业技能\nMicrosoft Word、Microsoft Excel、Microsoft PowerPoint"

    processed = process_resume_extraction(ResumeExtractionResult(), source, allow_repair=False)

    assert [skill.name for skill in processed.result.skills] == ["Word", "Excel", "PowerPoint"]
    assert [skill.evidence_text for skill in processed.result.skills] == [
        "Microsoft Word",
        "Microsoft Excel",
        "Microsoft PowerPoint",
    ]


def test_supported_credential_aliases_are_recovered_from_explicit_sections() -> None:
    source = "证书\n大学英语四级；大学英语六级；IELTS；TOEFL；JLPT\n语言能力\n普通话二级甲等"

    processed = process_resume_extraction(ResumeExtractionResult(), source, allow_repair=False)

    assert [certification.name for certification in processed.result.certifications] == [
        "CET-4",
        "CET-6",
        "IELTS",
        "TOEFL",
        "JLPT",
        "普通话二级甲等",
    ]
    assert all(certification.score is None for certification in processed.result.certifications)
    assert all(certification.status is None for certification in processed.result.certifications)


def test_generic_office_software_remains_generic_without_atomic_source_tokens() -> None:
    source = "专业技能：办公软件"
    result = ResumeExtractionResult(skills=[{"name": "办公软件", "evidence_text": "办公软件"}])

    processed = process_resume_extraction(result, source, allow_repair=False)

    assert [skill.name for skill in processed.result.skills] == ["办公软件"]


def test_single_unsupported_skill_is_rejected_at_api_without_returning_502() -> None:
    class Provider:
        def extract(self, evidence_text: str) -> ResumeExtractionResult:
            return ResumeExtractionResult(
                skills=[
                    {"name": "Python", "evidence_text": "Python"},
                    {"name": "Unicorn Stack", "evidence_text": "Unicorn Stack"},
                ]
            )

    document = fitz.open()
    page = document.new_page()
    page.insert_text((72, 72), "Python")
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
    assert [skill["name"] for skill in response.json()["skills"]] == ["Python"]


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
