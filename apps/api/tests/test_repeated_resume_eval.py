from app.main import process_resume_extraction
from app.resume_schemas import ResumeExtractionResult


def _signature(result: ResumeExtractionResult) -> tuple[tuple[str, ...], tuple[str, ...], tuple[str, ...]]:
    return (
        tuple(sorted(skill.name for skill in result.skills)),
        tuple(sorted(certification.name for certification in result.certifications)),
        tuple(sorted((experience.title, experience.experience_type.value) for experience in result.experiences)),
    )


def test_five_equivalent_raw_outputs_have_one_normalized_semantic_signature() -> None:
    source = "专业技能：Word、Excel、PPT；Python\n语言能力：英语读写能力\n证书：CET-6 300"
    variants = [
        ResumeExtractionResult(
            skills=[
                {"name": "Word、Excel、PPT", "evidence_text": "Word、Excel、PPT"},
                {"name": "Python", "evidence_text": "Python"},
                {"name": "英语读写能力", "evidence_text": "英语读写能力"},
            ],
            certifications=[{"name": "CET-6 300", "evidence_text": "CET-6 300"}],
        ),
        ResumeExtractionResult(
            skills=[
                {"name": "Word", "evidence_text": "Word"},
                {"name": "Excel", "evidence_text": "Excel"},
                {"name": "PPT", "evidence_text": "PPT"},
                {"name": "Python", "evidence_text": "Python"},
                {"name": "英语", "evidence_text": "英语"},
            ],
            certifications=[{"name": "CET-6", "evidence_text": "CET-6"}],
        ),
        ResumeExtractionResult(
            skills=[{"name": "Word、Excel、PPT", "evidence_text": "Word、Excel、PPT"},
                    {"name": "Python", "evidence_text": "Python"},
                    {"name": "英语读写能力", "evidence_text": "英语读写能力"}],
            certifications=[{"name": "CET-6 300", "evidence_text": "CET-6 300"}],
        ),
        ResumeExtractionResult(
            skills=[
                {"name": "Word", "evidence_text": "专业技能：Word、Excel、PPT；Python"},
                {"name": "Excel", "evidence_text": "专业技能：Word、Excel、PPT；Python"},
                {"name": "PPT", "evidence_text": "专业技能：Word、Excel、PPT；Python"},
                {"name": "Python", "evidence_text": "Python"},
                {"name": "英语", "evidence_text": "英语读写能力"},
            ],
            certifications=[{"name": "CET-6", "evidence_text": "证书：CET-6 300"}],
        ),
        ResumeExtractionResult(
            skills=[{"name": "PowerPoint", "raw_value": "PPT", "evidence_text": "PPT"},
                    {"name": "Excel", "evidence_text": "Excel"},
                    {"name": "Word", "evidence_text": "Word"},
                    {"name": "Python", "evidence_text": "Python"},
                    {"name": "英语读写能力", "evidence_text": "英语读写能力"}],
            certifications=[{"name": "CET-6 300", "evidence_text": "CET-6 300"}],
        ),
    ]

    signatures = [_signature(process_resume_extraction(variant, source).result) for variant in variants]

    assert len(set(signatures)) == 1
    assert signatures[0] == (("English", "Excel", "PowerPoint", "Python", "Word"), ("CET-6",), ())
