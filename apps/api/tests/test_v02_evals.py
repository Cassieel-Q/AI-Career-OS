from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parents[3]))

from evals.schema import compare_cases


def test_curated_v02_seed_cases_cover_required_metrics_and_pass_expected_outputs():
    cases = json.loads((Path(__file__).parents[3] / "evals" / "seed_cases.json").read_text(encoding="utf-8"))
    results = compare_cases(cases)
    assert len(results) == 15
    assert all(result.passed for result in results)
    assert {case["expected"]["gap_type"] for case in cases} == {"ARTICULATION_GAP", "EVIDENCE_GAP", "KNOWLEDGE_GAP", "PROJECT_GAP"}
    assert all(result.jd_grounding_accuracy == 1.0 for result in results)
    assert all(result.experience_selection_relevance == 1.0 for result in results)
    assert all(result.red_team_risk_recall == 1.0 for result in results)
    assert all(result.interview_retrieval_relevance == 1.0 for result in results)
    assert all(result.proof_action_artifactability == 1.0 for result in results)
