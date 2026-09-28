from __future__ import annotations

from typing import Any

from app.resume_schemas import ResumeExtractionResult


def _facts(result: ResumeExtractionResult) -> dict[str, set[tuple[Any, ...]]]:
    return {
        "education": {
            (item.institution, item.field_of_study, course)
            for item in result.education
            for course in (item.relevant_courses or [None])
        },
        "skills": {(item.name,) for item in result.skills},
        "experiences": {(item.title, item.experience_type.value) for item in result.experiences},
        "certifications": {(item.name,) for item in result.certifications},
    }


def evaluate_golden_extraction(
    result: ResumeExtractionResult, expected: dict[str, list[dict[str, Any]]]
) -> dict[str, float | int]:
    expected_facts = {
        "education": {
            (item["institution"], item.get("field_of_study"), course)
            for item in expected.get("education", [])
            for course in (item.get("relevant_courses") or [None])
        },
        "skills": {(item,) for item in expected.get("skills", [])},
        "experiences": {(item["title"], item["experience_type"]) for item in expected.get("experiences", [])},
        "certifications": {(item,) for item in expected.get("certifications", [])},
    }
    actual_facts = _facts(result)
    expected_total = sum(len(facts) for facts in expected_facts.values())
    matched_total = sum(len(expected_facts[category] & actual_facts[category]) for category in expected_facts)
    hallucinated_total = sum(len(actual_facts[category] - expected_facts[category]) for category in actual_facts)
    return {
        "extraction_recall": matched_total / expected_total if expected_total else 1.0,
        "classification_consistency": matched_total / expected_total if expected_total else 1.0,
        "normalization_consistency": 1.0 if matched_total == expected_total else 0.0,
        "hallucinated_fact_count": hallucinated_total,
    }
