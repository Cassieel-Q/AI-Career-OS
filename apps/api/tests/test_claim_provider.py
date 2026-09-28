from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from openai import BadRequestError

from app.claim_provider import (
    ClaimProviderInvalidResponseError,
    ClaimProviderUpstreamError,
    OpenAIClaimAnalysisProvider,
    _timeout_seconds,
    sanitize_evidence_refs,
)


FACT_ID = UUID("11111111-1111-4111-8111-111111111111")


def test_claim_provider_uses_faster_default_timeout(monkeypatch) -> None:
    monkeypatch.delenv("OPENAI_TIMEOUT_SECONDS", raising=False)
    monkeypatch.delenv("OPENAI_CLAIM_TIMEOUT_SECONDS", raising=False)
    assert _timeout_seconds() == 15.0
    monkeypatch.setenv("OPENAI_CLAIM_TIMEOUT_SECONDS", "19")
    assert _timeout_seconds() == 19.0


class FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.request: dict[str, object] | None = None

    def create(self, **kwargs):
        self.request = kwargs
        if self.error:
            raise self.error
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def provider(completions: FakeCompletions) -> OpenAIClaimAnalysisProvider:
    return OpenAIClaimAnalysisProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=completions)))


def valid_payload() -> dict:
    return {
        "claims": [
            {
                "claim": "Designed an LLM evaluation workflow",
                "current_text": "Worked on LLM evaluation",
                "suggested_text": "Designed an LLM evaluation workflow",
                "reason": "The experience is present but under-explained.",
                "jd_relevance": "Matches the evaluation responsibility.",
                "matched_capabilities": [{"name": "LLM evaluation", "summary": "Evaluation design", "atomic_requirement_ids": []}],
                "evidence_refs": [str(FACT_ID)],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.7,
                "risk_reason": "No evaluation artifact is recorded.",
                "attack_surface": [{"area": "AI", "risk": "Explain evaluation design", "evidence_refs": [str(FACT_ID)]}],
            }
        ]
    }


def test_deepseek_claim_provider_uses_json_object_and_manual_strict_parse(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-v4-pro")
    completions = FakeCompletions(json.dumps(valid_payload()))

    result = provider(completions).analyze(
        target_job={"raw_text": "Build evaluation workflows"},
        profile_facts=[{"id": str(FACT_ID), "kind": "experience", "value": "LLM evaluation"}],
    )

    assert result.claims[0].evidence_refs == [FACT_ID]
    assert completions.request is not None
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert completions.request["model"] == "deepseek-v4-pro"
    assert "JSON" in str(completions.request["messages"][0]["content"])
    assert not hasattr(completions.request["response_format"], "model_dump")


@pytest.mark.parametrize(
    ("content", "reason"),
    [("", "empty_response"), ("not-json", "json_decode"), (json.dumps({"claims": []}), "schema_validation")],
)
def test_claim_provider_rejects_malformed_or_schema_invalid_json(monkeypatch, content: str, reason: str) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")

    with pytest.raises(ClaimProviderInvalidResponseError) as caught:
        provider(FakeCompletions(content)).analyze(target_job={}, profile_facts=[])

    assert caught.value.reason == reason
    assert "not-json" not in str(caught.value)


def test_claim_provider_normalizes_partial_claim_schema(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    content = json.dumps(
        {
            "claims": [
                {
                    "claim": "做过评测流程",
                    "readiness_status": "weak",
                    "attack_surface": [{"area": "Product", "risk": "讲清个人贡献"}],
                    "matched_capabilities": ["评测"],
                    "evidence_refs": [str(FACT_ID)],
                }
            ]
        }
    )
    result = provider(FakeCompletions(content)).analyze(
        target_job={"raw_text": "Build evaluation workflows"},
        profile_facts=[{"id": str(FACT_ID), "kind": "experience", "value": "LLM evaluation"}],
    )
    assert result.claims[0].claim.startswith("做过")
    assert result.claims[0].readiness_status.value == "WEAK_EVIDENCE"
    assert result.claims[0].attack_surface[0].area.value == "PRODUCT"


def test_claim_provider_preserves_safe_upstream_status_metadata(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(400, request=request)
    error = BadRequestError(
        "provider rejected the request",
        response=response,
        body={"message": "bad request", "type": "invalid_request_error", "code": "invalid_request_error"},
    )

    with pytest.raises(ClaimProviderUpstreamError) as caught:
        provider(FakeCompletions(error=error)).analyze(target_job={}, profile_facts=[])

    assert caught.value.status_code == 400
    assert caught.value.provider_code == "invalid_request_error"

def test_claim_provider_caps_to_three_resume_writable_claims(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    claims = []
    for i in range(8):
        claims.append(
            {
                "claim": f"unsupported gap {i}",
                "suggested_text": None,
                "reason": "missing",
                "jd_relevance": "mapped",
                "matched_capabilities": [],
                "evidence_refs": [],
                "readiness_status": "UNSUPPORTED",
                "confidence": 0.2,
                "risk_reason": "no evidence",
                "attack_surface": [],
            }
        )
    for i, label in enumerate(["A", "B", "C", "D"]):
        claims.append(
            {
                "claim": f"writable {label}",
                "current_text": f"raw {label}",
                "suggested_text": f"Improved {label} for the JD",
                "reason": "reframe",
                "jd_relevance": "high",
                "matched_capabilities": [{"name": label, "summary": label, "atomic_requirement_ids": []}],
                "evidence_refs": [str(FACT_ID)],
                "readiness_status": "WEAK_EVIDENCE",
                "confidence": 0.8 - i * 0.05,
                "risk_reason": "needs story",
                "attack_surface": [{"area": "AI", "risk": "probe", "evidence_refs": [str(FACT_ID)]}],
            }
        )
    result = provider(FakeCompletions(json.dumps({"claims": claims}))).analyze(
        target_job={"raw_text": "Build evaluation workflows"},
        profile_facts=[{"id": str(FACT_ID), "kind": "experience", "value": "LLM evaluation"}],
    )
    assert len(result.claims) == 3
    assert all(claim.suggested_text for claim in result.claims)
    assert all(claim.readiness_status.value != "UNSUPPORTED" for claim in result.claims)
    assert "at most 3" in OpenAIClaimAnalysisProvider._system_prompt()


def test_sanitize_evidence_refs_drops_none_and_invalid() -> None:
    """Write-path guard: never keep Python None coerced to the literal "None"."""
    cleaned = sanitize_evidence_refs(
        [
            None,
            "None",
            "null",
            "",
            "   ",
            "not-a-uuid",
            "00000000-0000-0000-0000-000000000000",
            FACT_ID,
            str(FACT_ID),
            "None",
        ]
    )
    assert cleaned == [str(FACT_ID)]
    assert "None" not in cleaned
    assert None not in cleaned


def test_normalize_claim_item_strips_none_evidence_refs() -> None:
    normalized = OpenAIClaimAnalysisProvider._normalize_claim_item(
        {
            "claim": "Led evaluation workflow for LLM quality",
            "suggested_text": None,
            "reason": "grounded",
            "jd_relevance": "maps to JD",
            "matched_capabilities": [],
            "evidence_refs": [None, "None", "", "  ", str(FACT_ID), "bogus"],
            "readiness_status": "WEAK_EVIDENCE",
            "confidence": 0.6,
            "risk_reason": "needs artifact",
            "attack_surface": [
                {"area": "AI", "risk": "probe eval design", "evidence_refs": [None, "None", str(FACT_ID)]}
            ],
        }
    )
    assert normalized is not None
    assert normalized["evidence_refs"] == [str(FACT_ID)]
    assert "None" not in normalized["evidence_refs"]
    assert normalized["attack_surface"][0]["evidence_refs"] == [str(FACT_ID)]


def test_soft_claims_skip_missing_fact_id() -> None:
    soft = OpenAIClaimAnalysisProvider._soft_claims_from_facts(
        [
            {"id": None, "kind": "experience", "value": "Built eval harness"},
            {"id": "None", "kind": "experience", "value": "Owned quality gates"},
            {"id": str(FACT_ID), "kind": "experience", "value": "Ran LLM offline eval"},
        ]
    )
    claims = soft["claims"]
    assert claims
    for claim in claims:
        assert "None" not in claim["evidence_refs"]
        for ref in claim["evidence_refs"]:
            assert ref and ref != "None"
            UUID(ref)
    # The valid-id fact should produce a clean ref list.
    asserted = [c for c in claims if c["evidence_refs"] == [str(FACT_ID)]]
    assert asserted, "expected soft claim grounded on FACT_ID"

