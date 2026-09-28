import json
from types import SimpleNamespace
from uuid import UUID

import httpx
import pytest

from app.roadmap_provider import OpenAIRoadmapProvider, RoadmapProviderInvalidResponseError, roadmap_timeout_seconds


class InvalidRoadmapClient:
    class _Completions:
        @staticmethod
        def create(**_request):
            return SimpleNamespace(
                choices=[SimpleNamespace(message=SimpleNamespace(content='{"weeks":[]}'))]
            )

    chat = SimpleNamespace(completions=_Completions())


class CapturingRoadmapClient:
    def __init__(self, content: str):
        self.content = content
        self.request = None

        class _Completions:
            def create(inner_self, **request):
                self.request = request
                return SimpleNamespace(
                    choices=[SimpleNamespace(message=SimpleNamespace(content=self.content))]
                )

        self.chat = SimpleNamespace(completions=_Completions())


class TimeoutRoadmapClient:
    class _Completions:
        @staticmethod
        def create(**_request):
            raise httpx.ReadTimeout("provider timed out")

    chat = SimpleNamespace(completions=_Completions())


GAP_ID = UUID("11111111-1111-1111-1111-111111111111")


def _valid_response() -> str:
    return json.dumps({
        "weeks": [
            {
                "week_number": week_number,
                "objective": f"Objective {week_number}",
                "focus_gap_ids": [str(GAP_ID)],
                "measurable_outcome": f"Outcome {week_number}",
                "tasks": [{
                    "title": f"Task {week_number}",
                    "objective": "Create a reviewable artifact",
                    "estimated_minutes": 30,
                    "related_gap_id": str(GAP_ID),
                    "completion_criteria": "Artifact is saved",
                }],
            }
            for week_number in range(1, 5)
        ],
    })


def test_provider_classifies_malformed_roadmap_schema_without_exposing_payload():
    provider = OpenAIRoadmapProvider(client=InvalidRoadmapClient())

    with pytest.raises(RoadmapProviderInvalidResponseError) as caught:
        provider.plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": "gap-1", "capability_name": "Technical capability"}],
        )

    assert caught.value.reason == "schema_validation"
    assert "weeks" not in str(caught.value)


def test_provider_captures_safe_locations_for_the_observed_nested_week_failure():
    nested = json.dumps({
        "weeks": [{"week": week} for week in json.loads(_valid_response())["weeks"]],
    })

    with pytest.raises(RoadmapProviderInvalidResponseError) as caught:
        OpenAIRoadmapProvider(client=CapturingRoadmapClient(nested)).plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
        )

    assert caught.value.reason == "schema_validation"
    assert {tuple(error["loc"]) for error in caught.value.validation_errors} >= {
        ("weeks", 0, "week_number"),
        ("weeks", 0, "week"),
    }
    assert all(set(error) == {"loc", "type"} for error in caught.value.validation_errors)
    assert "Objective 1" not in str(caught.value)


def test_provider_parses_deepseek_compatible_json_object_without_relaxing_schema():
    client = CapturingRoadmapClient(_valid_response())

    proposal = OpenAIRoadmapProvider(client=client).plan(
        target_role="AI_PRODUCT_MANAGER",
        weekly_hours=10,
        priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
    )

    assert [week.week_number for week in proposal.weeks] == [1, 2, 3, 4]
    assert client.request["response_format"] == {"type": "json_object"}
    assert "JSON only" in client.request["messages"][0]["content"]
    assert "Do not wrap a week" in client.request["messages"][0]["content"]
    assert "exactly" in client.request["messages"][0]["content"]


def test_provider_classifies_malformed_json_without_exposing_content():
    with pytest.raises(RoadmapProviderInvalidResponseError) as caught:
        OpenAIRoadmapProvider(client=CapturingRoadmapClient("not-json")).plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
        )

    assert caught.value.reason == "json_decode"
    assert "not-json" not in str(caught.value)


def test_provider_rejects_wrong_week_count_and_forbidden_status_safely():
    fewer_weeks = json.loads(_valid_response())
    fewer_weeks["weeks"] = fewer_weeks["weeks"][:3]
    with pytest.raises(RoadmapProviderInvalidResponseError) as count_error:
        OpenAIRoadmapProvider(client=CapturingRoadmapClient(json.dumps(fewer_weeks))).plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
        )
    assert count_error.value.reason == "schema_validation"
    assert any(tuple(error["loc"]) == ("weeks",) for error in count_error.value.validation_errors)

    forbidden_status = json.loads(_valid_response())
    forbidden_status["weeks"][0]["tasks"][0]["status"] = "TODO"
    with pytest.raises(RoadmapProviderInvalidResponseError) as status_error:
        OpenAIRoadmapProvider(client=CapturingRoadmapClient(json.dumps(forbidden_status))).plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
        )
    assert status_error.value.reason == "schema_validation"
    assert any(tuple(error["loc"]) == ("weeks", 0, "tasks", 0, "status") for error in status_error.value.validation_errors)


def test_provider_classifies_timeout_as_a_retryable_timeout():
    from app.roadmap_provider import RoadmapProviderTimeoutError

    with pytest.raises(RoadmapProviderTimeoutError):
        OpenAIRoadmapProvider(client=TimeoutRoadmapClient()).plan(
            target_role="AI_PRODUCT_MANAGER",
            weekly_hours=10,
            priorities=[{"gap_id": str(GAP_ID), "capability_name": "Technical capability"}],
        )


def test_roadmap_timeout_has_a_narrow_provider_specific_default(monkeypatch):
    monkeypatch.setenv("OPENAI_TIMEOUT_SECONDS", "30")
    monkeypatch.delenv("ROADMAP_TIMEOUT_SECONDS", raising=False)
    assert roadmap_timeout_seconds() == 45.0

    monkeypatch.setenv("ROADMAP_TIMEOUT_SECONDS", "50")
    assert roadmap_timeout_seconds() == 50.0
