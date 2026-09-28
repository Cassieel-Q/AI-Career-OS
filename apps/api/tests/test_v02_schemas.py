from uuid import uuid4

import pytest
from pydantic import ValidationError

from app.proof_schemas import (
    AttackSurfaceArea,
    InterviewGapType,
    ProofActionCreate,
    ProofActionProposal,
    ProofArtifactCreate,
    ReadinessStatus,
    TargetJobCreate,
)


def test_target_job_accepts_one_non_blank_jd_and_normalizes_blank_source_url() -> None:
    payload = TargetJobCreate(raw_text="  Build AI products.  ", source_url="   ")

    assert payload.raw_text == "  Build AI products.  "
    assert payload.source_url is None


def test_target_job_rejects_extra_fields_and_invalid_urls() -> None:
    with pytest.raises(ValidationError):
        TargetJobCreate(raw_text="A real job", extra_field="nope")
    with pytest.raises(ValidationError):
        TargetJobCreate(raw_text="A real job", source_url="javascript:alert(1)")


def test_proof_action_requires_artifact_producing_contract() -> None:
    proposal = ProofActionProposal(
        title="Build a 15-case evaluation set",
        why_now="The selected claim has weak evaluation evidence.",
        target_claim="Designed an LLM evaluation framework",
        target_gap=InterviewGapType.EVIDENCE_GAP,
        estimated_hours=3,
        artifact_type="DATASET",
        definition_of_done="A versioned dataset with 15 cases and expected labels.",
        expected_evidence="Repository URL and a short README.",
    )

    assert proposal.target_gap is InterviewGapType.EVIDENCE_GAP
    assert proposal.estimated_hours == 3

    with pytest.raises(ValidationError):
        ProofActionCreate(actions=[proposal] * 4)


def test_artifact_requires_url_or_text_and_never_accepts_unknown_fields() -> None:
    action_id = uuid4()
    artifact = ProofArtifactCreate(action_id=action_id, artifact_type="REPORT", artifact_url="https://example.com/report")
    assert artifact.artifact_url == "https://example.com/report"

    with pytest.raises(ValidationError):
        ProofArtifactCreate(action_id=action_id, artifact_type="REPORT")
    with pytest.raises(ValidationError):
        ProofArtifactCreate(action_id=action_id, artifact_type="REPORT", artifact_url="https://example.com", secret="x")


def test_enums_keep_claim_readiness_gap_and_attack_surface_values_strict() -> None:
    assert ReadinessStatus.WEAK_EVIDENCE.value == "WEAK_EVIDENCE"
    assert InterviewGapType.ARTICULATION_GAP.value == "ARTICULATION_GAP"
    assert AttackSurfaceArea.BUSINESS_IMPACT.value == "BUSINESS_IMPACT"
