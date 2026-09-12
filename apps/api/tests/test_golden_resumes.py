import json
from pathlib import Path

import pytest

from app.main import validate_evidence_trace
from app.resume_evaluation import evaluate_golden_extraction
from app.resume_normalization import normalize_resume_extraction
from app.resume_schemas import ResumeExtractionResult


GOLDEN_DIR = Path(__file__).parent / "golden_resumes"


@pytest.mark.parametrize("fixture_path", sorted(GOLDEN_DIR.glob("*.json")), ids=lambda path: path.stem)
def test_golden_resume_normalization(fixture_path: Path) -> None:
    fixture = json.loads(fixture_path.read_text(encoding="utf-8"))
    normalized = normalize_resume_extraction(ResumeExtractionResult.model_validate(fixture["extraction"]))
    validate_evidence_trace(normalized, fixture["source_text"])

    metrics = evaluate_golden_extraction(normalized, fixture["expected"])

    assert metrics == {
        "extraction_recall": 1.0,
        "classification_consistency": 1.0,
        "normalization_consistency": 1.0,
        "hallucinated_fact_count": 0,
    }
