from __future__ import annotations

import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.role_exploration_provider import (
    OpenAIRoleExplorationProvider,
    RoleExplorationContext,
    RoleExplorationFact,
    RoleExplorationPreference,
    RoleExplorationProviderConnectionError,
    RoleExplorationProviderInvalidResponseError,
    RoleExplorationProviderNotConfiguredError,
    RoleExplorationProviderTimeoutError,
    build_role_exploration_context,
    get_role_exploration_provider,
    set_role_exploration_provider,
)
from app.role_exploration_schemas import (
    ExplorationLevel,
    RoleCode,
    RoleExplorationProviderPayload,
)
from app.role_profiles import ROLE_PROFILES
from app.profile_schemas import CareerPreferencePriority


def _context() -> RoleExplorationContext:
    return RoleExplorationContext(
        facts=(RoleExplorationFact(id=UUID("11111111-1111-4111-8111-111111111111"), value="Python"),),
        preferences=(RoleExplorationPreference(value=CareerPreferencePriority.CURRENT_FIT, position=1),),
        catalog_profiles=ROLE_PROFILES,
    )


def test_missing_api_key_is_typed_configuration_error(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    with pytest.raises(RoleExplorationProviderNotConfiguredError):
        OpenAIRoleExplorationProvider()


def test_provider_injection_is_deterministic() -> None:
    class FakeProvider:
        def explore(self, context: RoleExplorationContext) -> RoleExplorationProviderPayload:
            return RoleExplorationProviderPayload(items=[])

    fake = FakeProvider()
    set_role_exploration_provider(fake)
    try:
        assert get_role_exploration_provider() is fake
    finally:
        set_role_exploration_provider(None)


def test_prompt_contains_ids_preferences_and_role_codes_without_output_logging(monkeypatch: pytest.MonkeyPatch, caplog) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps({"items": []})))] )

    class FakeClient:
        chat = SimpleNamespace(completions=FakeCompletions())

    provider = OpenAIRoleExplorationProvider(client=FakeClient())
    with pytest.raises(RoleExplorationProviderInvalidResponseError):
        provider.explore(_context())
    prompt = f"{captured['messages']}"
    assert "11111111-1111-4111-8111-111111111111" in prompt
    assert "CURRENT_FIT" in prompt
    for role_code in RoleCode:
        assert role_code.value in prompt
    assert "Python" in prompt
    assert "no role names" in prompt.lower()
    assert "percentage" in prompt.lower()
    assert all("Python" not in record.getMessage() for record in caplog.records)


def test_context_builder_copies_orm_career_preference_relation() -> None:
    profile_id = UUID("22222222-2222-4222-8222-222222222222")
    career_preference = SimpleNamespace(
        priority_order=["FAST_EMPLOYMENT", "CURRENT_FIT"],
        weekly_hours=20,
    )
    profile = SimpleNamespace(
        id=profile_id,
        education=[],
        skills=[],
        experiences=[],
        certifications=[],
        career_preference=career_preference,
    )

    context = build_role_exploration_context(profile)

    assert [preference.value for preference in context.preferences] == [
        CareerPreferencePriority.FAST_EMPLOYMENT,
        CareerPreferencePriority.CURRENT_FIT,
    ]
    assert [preference.position for preference in context.preferences] == [1, 2]
    assert context.weekly_hours == 20
    assert context.profile_id == profile_id


def test_model_environment_fallback_precedence(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_MODEL", "shared-model")
    monkeypatch.setenv("OPENAI_ROLE_EXPLORATION_MODEL", "role-model")
    provider = OpenAIRoleExplorationProvider(client=object())
    assert provider.model == "role-model"

    monkeypatch.delenv("OPENAI_ROLE_EXPLORATION_MODEL")
    provider = OpenAIRoleExplorationProvider(client=object())
    assert provider.model == "shared-model"

    monkeypatch.delenv("OPENAI_MODEL")
    provider = OpenAIRoleExplorationProvider(client=object())
    assert provider.model == "gpt-4o-mini"


def test_deepseek_request_disables_thinking(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    monkeypatch.setenv("OPENAI_BASE_URL", "https://api.deepseek.com/v1")
    captured: dict[str, object] = {}

    class FakeCompletions:
        def create(self, **kwargs):
            captured.update(kwargs)
            payload = {
                "items": [
                    {
                        "role_code": RoleCode.AI_PRODUCT_MANAGER,
                        "level": ExplorationLevel.POSSIBLE,
                        "reasons": ["grounded"],
                        "evidence_refs": ["11111111-1111-4111-8111-111111111111"],
                    }
                ]
            }
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    provider = OpenAIRoleExplorationProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions()))
    )
    provider.explore(_context())

    assert captured["extra_body"] == {"thinking": {"type": "disabled"}}


def test_extra_keys_and_unknown_role_codes_are_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")

    class ExtraKeyCompletions:
        def create(self, **kwargs):
            payload = {
                "items": [
                    {
                        "role_code": RoleCode.AI_PRODUCT_MANAGER,
                        "level": ExplorationLevel.POSSIBLE,
                        "reasons": ["grounded"],
                        "evidence_refs": ["11111111-1111-4111-8111-111111111111"],
                        "role_name": "must not be accepted",
                    }
                ]
            }
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    provider = OpenAIRoleExplorationProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=ExtraKeyCompletions()))
    )
    with pytest.raises(RoleExplorationProviderInvalidResponseError):
        provider.explore(_context())

    class UnknownCodeCompletions:
        def create(self, **kwargs):
            payload = {
                "items": [
                    {
                        "role_code": "UNKNOWN_ROLE",
                        "level": ExplorationLevel.POSSIBLE,
                        "reasons": ["grounded"],
                        "evidence_refs": ["11111111-1111-4111-8111-111111111111"],
                    }
                ]
            }
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])

    provider = OpenAIRoleExplorationProvider(
        client=SimpleNamespace(chat=SimpleNamespace(completions=UnknownCodeCompletions()))
    )
    with pytest.raises(RoleExplorationProviderInvalidResponseError):
        provider.explore(_context())


def test_valid_json_object_is_parsed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    ref = UUID("11111111-1111-4111-8111-111111111111")
    payload = {"items": [{"role_code": RoleCode.AI_PRODUCT_MANAGER, "level": ExplorationLevel.POSSIBLE, "reasons": ["grounded"], "evidence_refs": [str(ref)]}]}
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content=json.dumps(payload)))])
    provider = OpenAIRoleExplorationProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    result = provider.explore(_context())
    assert result.items[0].role_code is RoleCode.AI_PRODUCT_MANAGER


def test_malformed_json_raises_typed_invalid_response(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    class FakeCompletions:
        def create(self, **kwargs):
            return SimpleNamespace(choices=[SimpleNamespace(message=SimpleNamespace(content="not-json"))])
    provider = OpenAIRoleExplorationProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=FakeCompletions())))
    with pytest.raises(RoleExplorationProviderInvalidResponseError):
        provider.explore(_context())


def test_timeout_and_connection_errors_are_typed(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OPENAI_API_KEY", "test-key")
    class TimeoutCompletions:
        def create(self, **kwargs):
            raise httpx.TimeoutException("timed out")
    provider = OpenAIRoleExplorationProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=TimeoutCompletions())))
    with pytest.raises(RoleExplorationProviderTimeoutError):
        provider.explore(_context())

    class ConnectionCompletions:
        def create(self, **kwargs):
            raise httpx.ConnectError("offline")
    provider = OpenAIRoleExplorationProvider(client=SimpleNamespace(chat=SimpleNamespace(completions=ConnectionCompletions())))
    with pytest.raises(RoleExplorationProviderConnectionError):
        provider.explore(_context())
