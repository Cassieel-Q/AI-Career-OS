"""Small, deterministic human-comparison harness for the v0.2 proof chain.

The harness deliberately compares structured labels and evidence references. It
does not call a provider, so reviewers can run it offline against curated
outputs before deciding whether a prompt or adapter change is safe.

Missing actual outputs are reported as NOT_RUN. They must never be compared
against expected labels by silently substituting expected for actual.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any


STATUS_COMPARED = "COMPARED"
STATUS_NOT_RUN = "NOT_RUN"


@dataclass(frozen=True)
class EvalResult:
    case_id: str
    status: str
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
        if self.status != STATUS_COMPARED:
            return False
        return all(value == 1.0 for value in self.__dict__.values() if isinstance(value, float))


def _rate(condition: bool) -> float:
    return 1.0 if condition else 0.0


def _not_run_result(case_id: str) -> EvalResult:
    return EvalResult(
        case_id=case_id,
        status=STATUS_NOT_RUN,
        jd_grounding_accuracy=0.0,
        unsupported_requirement_rate=0.0,
        resume_grounding=0.0,
        unsupported_claim_rate=0.0,
        claim_evidence_precision=0.0,
        experience_selection_relevance=0.0,
        red_team_risk_recall=0.0,
        interview_retrieval_relevance=0.0,
        followup_relevance=0.0,
        gap_type_accuracy=0.0,
        interview_followup_relevance=0.0,
        proof_action_artifactability=0.0,
        action_artifactability=0.0,
    )


def compare_case(case: dict[str, Any], actual: dict[str, Any] | None = None) -> EvalResult:
    """Compare one curated case against a real actual output.

    ``actual`` must be provided by the caller. ``None`` means the model or
    pipeline did not produce an output for this case and yields ``NOT_RUN``.
    An empty dict is treated as a real (poor) actual, not as missing.
    """
    if actual is None:
        return _not_run_result(str(case["id"]))

    expected = case["expected"]
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
        status=STATUS_COMPARED,
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
        interview_followup_relevance=_rate(
            actual.get("followup_relevant", False) == expected["followup_relevant"]
        ),
        proof_action_artifactability=_rate(artifact_actual == artifact_expected),
        action_artifactability=_rate(
            actual.get("artifact_producing", False) == expected["artifact_producing"]
        ),
    )


def compare_cases(
    cases: list[dict[str, Any]],
    actual_by_id: dict[str, dict[str, Any]] | None = None,
) -> list[EvalResult]:
    """Compare many cases. Missing ids in ``actual_by_id`` become NOT_RUN."""
    actual_by_id = actual_by_id or {}
    results: list[EvalResult] = []
    for case in cases:
        case_id = case["id"]
        if case_id not in actual_by_id:
            results.append(_not_run_result(str(case_id)))
            continue
        results.append(compare_case(case, actual_by_id[case_id]))
    return results
