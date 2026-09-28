from __future__ import annotations

import json
from types import SimpleNamespace

import pytest

from app.proof_action_provider import OpenAIProofActionProvider, ProofActionProviderInvalidResponseError


class FakeCompletions:
    def __init__(self, content: str) -> None:
        self.content = content
        self.request = None

    def create(self, **kwargs):
        self.request = kwargs
        return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))])


def test_proof_action_provider_returns_bounded_artifact_actions() -> None:
    payload = {
        "actions": [{
            "title": "Build a 15-case evaluation set",
            "why_now": "The claim needs an artifact.",
            "target_claim": "Designed an LLM evaluation workflow",
            "target_gap": "EVIDENCE_GAP",
            "estimated_hours": 3,
            "artifact_type": "DATASET",
            "definition_of_done": "A versioned dataset exists.",
            "expected_evidence": "Repository URL",
        }]
    }
    completions = FakeCompletions(json.dumps(payload))
    result = OpenAIProofActionProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=completions))).plan(
        claim={"claim": "Designed an LLM evaluation workflow"},
        debrief={"gap_type": "EVIDENCE_GAP"},
        evidence=[{"id": "fact-1", "value": "LLM evaluation"}],
    )

    assert result.actions[0].artifact_type == "DATASET"
    assert completions.request["response_format"] == {"type": "json_object"}


def test_proof_action_provider_rejects_malformed_json() -> None:
    provider = OpenAIProofActionProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions("not-json"))))

    with pytest.raises(ProofActionProviderInvalidResponseError) as caught:
        provider.plan(claim={}, debrief={}, evidence=[])

    assert caught.value.reason == "json_decode"
