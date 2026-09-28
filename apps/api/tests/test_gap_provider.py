from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest
from openai import BadRequestError

from app.gap_provider import (
    GapProviderConnectionError,
    GapProviderInvalidResponseError,
    OpenAIGapAnalysisProvider,
)


REQUIREMENT_ID = UUID("11111111-1111-4111-8111-111111111111")


def _payload(*, extra: dict | None = None) -> dict:
    item = {
        "requirement_id": str(REQUIREMENT_ID),
        "state": "PARTIAL",
        "severity": "MEDIUM",
        "proximity": "MEDIUM",
        "feasibility": "HIGH",
        "rationale": "The supplied evidence is related but incomplete.",
        "evidence_refs": [],
    }
    if extra:
        item.update(extra)
    return {"items": [item]}


class FakeCompletions:
    def __init__(self, content: str | None = None, error: Exception | None = None) -> None:
        self.content = content
        self.error = error
        self.request: dict[str, object] | None = None

    def create(self, **kwargs):
        self.request = kwargs
        if self.error is not None:
            raise self.error
        return SimpleNamespace(
            choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
        )


def _provider(completions: FakeCompletions) -> OpenAIGapAnalysisProvider:
    return OpenAIGapAnalysisProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=completions))
    )


def test_deepseek_gap_provider_uses_json_object_chat_completion_and_strict_parse(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    monkeypatch.setenv("OPENAI_MODEL", "deepseek-v4-pro")
    completions = FakeCompletions(json.dumps(_payload()))

    result = _provider(completions).compare(
        requirements=[{"id": str(REQUIREMENT_ID), "name": "Technical capability"}],
        profile_facts=[],
    )

    assert result.items[0].requirement_id == REQUIREMENT_ID
    assert completions.request is not None
    assert completions.request["response_format"] == {"type": "json_object"}
    assert completions.request["extra_body"] == {"thinking": {"type": "disabled"}}
    assert completions.request["model"] == "deepseek-v4-pro"
    system_prompt = str(completions.request["messages"][0]["content"])
    assert "json" in system_prompt.lower()
    assert all(value in system_prompt for value in ("LOW", "MEDIUM", "HIGH"))
    assert "uppercase" in system_prompt
    assert not hasattr(completions.request["response_format"], "model_dump")


@pytest.mark.parametrize(
    ("content", "reason"),
    [
        ("", "empty_response"),
        ("not-json", "json_decode"),
        (json.dumps(_payload(extra={"unexpected": "must be rejected"})), "schema_validation"),
    ],
)
def test_gap_provider_rejects_malformed_or_schema_invalid_json(monkeypatch, content: str, reason: str) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    completions = FakeCompletions(content)

    with pytest.raises(GapProviderInvalidResponseError) as caught:
        _provider(completions).compare(requirements=[], profile_facts=[])

    assert caught.value.reason == reason


def test_gap_provider_classifies_upstream_request_rejection(monkeypatch) -> None:
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com")
    request = httpx.Request("POST", "https://api.deepseek.com/chat/completions")
    response = httpx.Response(400, request=request)
    error = BadRequestError(
        "provider rejected the JSON mode prompt",
        response=response,
        body={
            "message": "Prompt must contain the word 'json' in some form",
            "type": "invalid_request_error",
            "param": None,
            "code": "invalid_request_error",
        },
    )

    with pytest.raises(GapProviderConnectionError) as caught:
        _provider(FakeCompletions(error=error)).compare(requirements=[], profile_facts=[])

    assert caught.value.status_code == 400
    assert caught.value.provider_code == "invalid_request_error"
    assert caught.value.provider_type == "invalid_request_error"
