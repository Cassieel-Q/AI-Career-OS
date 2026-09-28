"""Small, deterministic human-comparison harness for the v0.2 proof chain.

The harness deliberately compares structured labels and evidence references. It
does not call a provider, so reviewers can run it offline against curated
outputs before deciding whether a prompt or adapter change is safe.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    jd_grounding_accuracy: float
    unsupported_requirement_rate: float
    resume_grounding: float
    unsupported_claim_rate: float
    claim_evidence_precision: float
    experience_selection_relevance: float
    red_team_risk_recall: float
    interview_retrieval_relevance: float
    followup_relevance: float
    gap_type_accuracy: float
    interview_followup_relevance: float
    proof_action_artifactability: float
    action_artifactability: float

    @property
    def passed(self) -> bool:
        return all(value == 1.0 for value in self.__dict__.values() if isinstance(value, float))


def _rate(condition: bool) -> float:
    return 1.0 if condition else 0.0


def compare_case(case: dict[str, Any], actual: dict[str, Any] | None = None) -> EvalResult:
    expected = case["expected"]
    actual = actual or expected
    expected_claim = expected["readiness_status"]
    actual_claim = actual.get("readiness_status")
    expected_gap = expected.get("gap_type")
    actual_gap = actual.get("gap_type")
    expected_evidence = set(expected.get("evidence_refs", []))
    actual_evidence = set(actual.get("evidence_refs", []))
    if actual_evidence:
        precision = len(actual_evidence & expected_evidence) / len(actual_evidence)
    else:
        precision = 1.0 if not expected_evidence else 0.0

    def expected_metric(name: str, fallback: bool = True) -> bool:
        return bool(expected.get(name, fallback))

    def actual_metric(name: str, fallback: bool) -> bool:
        return bool(actual.get(name, fallback))

    jd_expected = expected_metric("jd_grounded", expected.get("grounded", True))
    jd_actual = actual_metric("jd_grounded", actual.get("grounded", jd_expected))
    unsupported_expected = expected_metric("unsupported_requirement", True)
    unsupported_actual = actual_metric("unsupported_requirement", unsupported_expected)
    experience_expected = expected_metric("experience_selection_relevant", True)
    experience_actual = actual_metric("experience_selection_relevant", experience_expected)
    red_team_expected = expected_metric("red_team_recalled", True)
    red_team_actual = actual_metric("red_team_recalled", red_team_expected)
    retrieval_expected = expected_metric("interview_retrieval_relevant", True)
    retrieval_actual = actual_metric("interview_retrieval_relevant", retrieval_expected)
    followup_expected = expected_metric("followup_relevant", True)
    followup_actual = actual_metric("followup_relevant", followup_expected)
    artifact_expected = expected_metric("artifact_producing", True)
    artifact_actual = actual_metric("artifact_producing", artifact_expected)
    return EvalResult(
        case_id=case["id"],
        jd_grounding_accuracy=_rate(jd_actual == jd_expected),
        unsupported_requirement_rate=_rate(unsupported_actual == unsupported_expected),
        resume_grounding=_rate(actual.get("grounded", False) == expected["grounded"]),
        unsupported_claim_rate=_rate(actual_claim == expected_claim),
        claim_evidence_precision=precision,
        experience_selection_relevance=_rate(experience_actual == experience_expected),
        red_team_risk_recall=_rate(red_team_actual == red_team_expected),
        interview_retrieval_relevance=_rate(retrieval_actual == retrieval_expected),
        followup_relevance=_rate(followup_actual == followup_expected),
        gap_type_accuracy=_rate(actual_gap == expected_gap),
        interview_followup_relevance=_rate(actual.get("followup_relevant", False) == expected["followup_relevant"]),
        proof_action_artifactability=_rate(artifact_actual == artifact_expected),
        action_artifactability=_rate(actual.get("artifact_producing", False) == expected["artifact_producing"]),
    )


def compare_cases(cases: list[dict[str, Any]], actual_by_id: dict[str, dict[str, Any]] | None = None) -> list[EvalResult]:
    actual_by_id = actual_by_id or {}
    return [compare_case(case, actual_by_id.get(case["id"])) for case in cases]
