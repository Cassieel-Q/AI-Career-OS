from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from evals.schema import STATUS_COMPARED, STATUS_NOT_RUN, compare_case, compare_cases


def _seed_cases() -> list[dict]:
    return json.loads(
        (Path(__file__).parents[3] / "evals" / "seed_cases.json").read_text(encoding="utf-8")
    )


def test_missing_actual_is_not_run_and_does_not_pass():
    cases = _seed_cases()
    results = compare_cases(cases)
    assert len(results) == 15
    assert all(result.status == STATUS_NOT_RUN for result in results)
    assert all(not result.passed for result in results)


def test_compare_case_none_actual_is_not_run():
    case = _seed_cases()[0]
    result = compare_case(case, actual=None)
    assert result.status == STATUS_NOT_RUN
    assert result.passed is False
    assert result.case_id == case["id"]


def test_empty_dict_actual_is_compared_not_substituted_with_expected():
    """Regression: `actual or expected` treated {} as missing and auto-passed."""
    case = _seed_cases()[0]
    result = compare_case(case, actual={})
    assert result.status == STATUS_COMPARED
    assert result.passed is False


def test_curated_v02_seed_cases_pass_when_actual_equals_expected():
    cases = _seed_cases()
    actual_by_id = {case["id"]: dict(case["expected"]) for case in cases}
    results = compare_cases(cases, actual_by_id)
    assert len(results) == 15
    assert all(result.status == STATUS_COMPARED for result in results)
    assert all(result.passed for result in results)
    assert {case["expected"]["gap_type"] for case in cases} == {
        "ARTICULATION_GAP",
        "EVIDENCE_GAP",
        "KNOWLEDGE_GAP",
        "PROJECT_GAP",
    }
    assert all(result.jd_grounding_accuracy == 1.0 for result in results)
    assert all(result.experience_selection_relevance == 1.0 for result in results)
    assert all(result.red_team_risk_recall == 1.0 for result in results)
    assert all(result.interview_retrieval_relevance == 1.0 for result in results)
    assert all(result.proof_action_artifactability == 1.0 for result in results)


def test_wrong_actual_fails_comparison():
    case = _seed_cases()[0]
    wrong = dict(case["expected"])
    wrong["grounded"] = not bool(wrong["grounded"])
    wrong["readiness_status"] = "UNSUPPORTED"
    result = compare_case(case, actual=wrong)
    assert result.status == STATUS_COMPARED
    assert result.passed is False
