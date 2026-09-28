"""Bridge Evidence OS gates with Profile / Proof domain."""
from __future__ import annotations

from typing import Any

from .evidence_os import gates


def validate_claim_wording(text: str) -> list[dict[str, str]]:
    """Return gate violations for resume/proof claim wording (empty if ok)."""
    issues: list[dict[str, str]] = []
    try:
        gates.assert_no_metric_estimate(text, field="wording")
    except gates.GateViolation as exc:
        issues.append(exc.as_dict())
    try:
        gates.assert_no_ats_pass_claim(text)
    except gates.GateViolation as exc:
        issues.append(exc.as_dict())
    return issues


def profile_to_evidence_facts(profile: object) -> list[dict[str, Any]]:
    """Project existing Profile rows into Evidence-OS-friendly fact dicts (no DB write)."""
    from .resume_intelligence import DefaultCareerEvidenceIntelligence

    return DefaultCareerEvidenceIntelligence.profile_facts(profile)


def proof_artifact_does_not_auto_verify(artifact_status: str | None) -> bool:
    """Task completion is not the same as verified evidence."""
    return (artifact_status or "").upper() in {"DONE", "COMPLETED", "SUBMITTED", "CHECKED"}
