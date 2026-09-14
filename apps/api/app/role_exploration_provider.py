"""OpenAI-compatible role exploration provider and immutable input contract."""
from __future__ import annotations

import json
import logging
import math
import os
from dataclasses import dataclass
from typing import Any, Protocol, runtime_checkable
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import ValidationError

from .profile_schemas import CareerPreferencePriority
from .role_exploration_schemas import RoleExplorationProviderPayload
from .role_profiles import ROLE_PROFILES, RoleProfile

logger = logging.getLogger(__name__)


class RoleExplorationProviderError(RuntimeError):
    """Base class for safe, service-mappable provider failures."""


class RoleExplorationProviderNotConfiguredError(RoleExplorationProviderError):
    """Required backend provider configuration is absent or invalid."""


class RoleExplorationProviderConnectionError(RoleExplorationProviderError):
    """The upstream provider could not be reached or returned an upstream error."""


class RoleExplorationProviderTimeoutError(RoleExplorationProviderError):
    """The upstream provider exceeded its timeout."""


class RoleExplorationProviderInvalidResponseError(RoleExplorationProviderError):
    """The upstream response was not a strict, valid provider payload."""


# Names that make exception mapping convenient to callers without exposing upstream errors.
RoleExplorationProviderNetworkError = RoleExplorationProviderConnectionError
RoleExplorationProviderSchemaError = RoleExplorationProviderInvalidResponseError
RoleExplorationProviderConfigurationError = RoleExplorationProviderNotConfiguredError
RoleExplorationProviderUnavailableError = RoleExplorationProviderNotConfiguredError
RoleExplorationProviderUpstreamError = RoleExplorationProviderConnectionError
RoleExplorationProviderJSONError = RoleExplorationProviderInvalidResponseError
RoleExplorationProviderTimeout = RoleExplorationProviderTimeoutError
RoleExplorationProviderConnection = RoleExplorationProviderConnectionError
RoleExplorationProviderInvalidJSONError = RoleExplorationProviderInvalidResponseError


@dataclass(frozen=True, slots=True)
class RoleExplorationFact:
    """A copied Profile child value, addressable by its source-row UUID."""

    id: UUID
    value: str
    kind: str = "fact"

    def __post_init__(self) -> None:
        if not isinstance(self.id, UUID):
            object.__setattr__(self, "id", UUID(str(self.id)))
        if not isinstance(self.value, str) or not self.value.strip():
            raise ValueError("fact value must be a non-empty string")
        if not isinstance(self.kind, str) or not self.kind.strip():
            raise ValueError("fact kind must be a non-empty string")

    @property
    def fact_id(self) -> UUID:
        return self.id


@dataclass(frozen=True, slots=True)
class RoleExplorationPreference:
    """One saved preference value and its stable order in the Profile."""

    value: CareerPreferencePriority
    position: int = 1

    def __post_init__(self) -> None:
        if not isinstance(self.value, CareerPreferencePriority):
            object.__setattr__(self, "value", CareerPreferencePriority(self.value))
        if not isinstance(self.position, int) or self.position < 1:
            raise ValueError("preference position must be a positive integer")

    @property
    def priority(self) -> CareerPreferencePriority:
        return self.value

    @property
    def rank(self) -> int:
        return self.position


@dataclass(frozen=True, slots=True)
class RoleExplorationContext:
    """Immutable, copied inputs supplied to a role exploration provider."""

    facts: tuple[RoleExplorationFact, ...]
    preferences: tuple[RoleExplorationPreference, ...]
    catalog_profiles: tuple[RoleProfile, ...] = ROLE_PROFILES
    profile_id: UUID | None = None
    weekly_hours: int | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "facts", tuple(self.facts))
        object.__setattr__(self, "preferences", tuple(self.preferences))
        object.__setattr__(self, "catalog_profiles", tuple(self.catalog_profiles))
        if self.profile_id is not None and not isinstance(self.profile_id, UUID):
            object.__setattr__(self, "profile_id", UUID(str(self.profile_id)))
        if self.weekly_hours is not None and (not isinstance(self.weekly_hours, int) or self.weekly_hours < 1):
            raise ValueError("weekly_hours must be a positive integer")

    @property
    def profile_facts(self) -> tuple[RoleExplorationFact, ...]:
        return self.facts

    @property
    def saved_preferences(self) -> tuple[RoleExplorationPreference, ...]:
        return self.preferences

    @property
    def catalog(self) -> tuple[RoleProfile, ...]:
        return self.catalog_profiles


def build_role_exploration_context(profile: Any, preferences: Any | None = None) -> RoleExplorationContext:
    """Copy Profile child IDs/values and saved ordered preferences into context.

    The helper accepts either Pydantic read models or ORM-like objects. It never
    retains references to mutable Profile collections.
    """
    facts: list[RoleExplorationFact] = []
    for kind, attribute, value_fields in (
        ("education", "education", ("canonical_value", "raw_value", "institution")),
        ("skill", "skills", ("canonical_value", "raw_value", "name")),
        ("experience", "experiences", ("canonical_value", "raw_value", "title")),
        ("certification", "certifications", ("canonical_value", "raw_value", "name")),
    ):
        for item in tuple(getattr(profile, attribute, ()) or ()):
            item_id = getattr(item, "id", None)
            value = next((getattr(item, field, None) for field in value_fields if getattr(item, field, None)), None)
            if item_id is not None and isinstance(value, str) and value.strip():
                facts.append(RoleExplorationFact(id=UUID(str(item_id)), value=value, kind=kind))

    stored_preferences = preferences
    if stored_preferences is None:
        stored_preferences = getattr(profile, "preferences", None)
    if stored_preferences is None:
        # ORM UserProfile exposes the one-to-one relation as ``career_preference``;
        # read-model profiles expose the copied relation as ``preferences``.
        stored_preferences = getattr(profile, "career_preference", None)
    raw_order = getattr(stored_preferences, "priority_order", stored_preferences or ())
    preference_values = tuple(raw_order or ())
    copied_preferences = tuple(
        RoleExplorationPreference(value=CareerPreferencePriority(value), position=index)
        for index, value in enumerate(preference_values, start=1)
    )
    profile_id = getattr(profile, "profile_id", getattr(profile, "id", None))
    return RoleExplorationContext(
        facts=tuple(facts),
        preferences=copied_preferences,
        catalog_profiles=ROLE_PROFILES,
        profile_id=UUID(str(profile_id)) if profile_id is not None else None,
        weekly_hours=getattr(stored_preferences, "weekly_hours", None),
    )


context_from_profile = build_role_exploration_context


@runtime_checkable
class RoleExplorationProvider(Protocol):
    def explore(self, context: RoleExplorationContext) -> RoleExplorationProviderPayload: ...


DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
MAX_OPENAI_TIMEOUT_SECONDS = 120.0
DEFAULT_OPENAI_MAX_RETRIES = 0
MAX_OPENAI_MAX_RETRIES = 2


def _timeout_seconds() -> float:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    if not raw:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = float(raw)
    except ValueError as exc:
        raise RoleExplorationProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > MAX_OPENAI_TIMEOUT_SECONDS:
        raise RoleExplorationProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS is outside the allowed range")
    return value


def _max_retries() -> int:
    raw = os.getenv("OPENAI_MAX_RETRIES", "").strip()
    if not raw:
        return DEFAULT_OPENAI_MAX_RETRIES
    try:
        value = int(raw)
    except ValueError as exc:
        raise RoleExplorationProviderNotConfiguredError("OPENAI_MAX_RETRIES must be an integer") from exc
    if value < 0 or value > MAX_OPENAI_MAX_RETRIES:
        raise RoleExplorationProviderNotConfiguredError("OPENAI_MAX_RETRIES is outside the allowed range")
    return value


def _is_deepseek_endpoint(base_url: str | None) -> bool:
    if not base_url:
        return False
    hostname = (urlparse(base_url).hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


class OpenAIRoleExplorationProvider:
    """Provider using the OpenAI chat-completions JSON-object interface."""

    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise RoleExplorationProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_ROLE_EXPLORATION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self._is_deepseek = _is_deepseek_endpoint(base_url)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            options: dict[str, object] = {
                "api_key": api_key,
                "timeout": _timeout_seconds(),
                "max_retries": _max_retries(),
            }
            if base_url:
                options["base_url"] = base_url
            self.client = OpenAI(**options)
        except RoleExplorationProviderError:
            raise
        except Exception as exc:
            raise RoleExplorationProviderNotConfiguredError("OpenAI provider configuration is invalid") from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "You are a bounded role-exploration assistant. Source facts are copied verbatim from the confirmed "
            "Profile; do not infer, embellish, or normalize facts, proficiency, credentials, or experience. "
            "Return a JSON object with exactly one `items` array containing the six supplied role codes exactly "
            "once. Use only those codes and levels RECOMMENDED, POSSIBLE, or LOW_PRIORITY. Return reasons and "
            "concerns as short bounded explanations grounded in supplied fact UUIDs and preference values. "
            "Return evidence_refs as supplied UUIDs and preference_refs as supplied preference values. "
            "Output no role names, display names, new roles, raw evidence text, profile fields, or mutations. "
            "Do not invent facts, proficiency, credentials, percentages, probabilities, salary, hiring, demand, "
            "company counts, live-market claims, or other market predictions. Output JSON only; no markdown."
        )

    @staticmethod
    def _user_content(context: RoleExplorationContext) -> str:
        catalog = [
            {
                "role_code": profile.role_code.value,
                "display_name": profile.display_name,
                "summary": profile.summary,
                "core_responsibilities": list(profile.core_responsibilities),
                "key_capabilities": list(profile.key_capabilities),
                "coding_intensity": profile.coding_intensity.value,
                "entry_barrier": profile.entry_barrier.value,
                "typical_evidence": list(profile.typical_evidence),
                "career_characteristics": list(profile.career_characteristics),
            }
            for profile in context.catalog_profiles
        ]
        return json.dumps(
            {
                "facts": [{"id": str(fact.id), "kind": fact.kind, "value": fact.value} for fact in context.facts],
                "preferences": [
                    {"position": preference.position, "value": preference.value.value}
                    for preference in context.preferences
                ],
                "weekly_hours": context.weekly_hours,
                "catalog_profiles": catalog,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    def _create_json_completion(self, *, system_prompt: str, user_content: str) -> object:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            "response_format": {"type": "json_object"},
        }
        if self._is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        return self.client.chat.completions.create(**request)

    @staticmethod
    def _response_content(response: object) -> str:
        try:
            content = response.choices[0].message.content  # type: ignore[attr-defined]
        except Exception as exc:
            raise RoleExplorationProviderInvalidResponseError("provider response had no message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RoleExplorationProviderInvalidResponseError("provider response had no JSON content")
        return content

    def explore(self, context: RoleExplorationContext) -> RoleExplorationProviderPayload:
        logger.info(
            "role_exploration_provider_request model=%s deepseek=%s fact_count=%d preference_count=%d catalog_count=%d",
            self.model,
            self._is_deepseek,
            len(context.facts),
            len(context.preferences),
            len(context.catalog_profiles),
        )
        try:
            response = self._create_json_completion(
                system_prompt=self._system_prompt(),
                user_content=self._user_content(context),
            )
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RoleExplorationProviderTimeoutError("role exploration provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise RoleExplorationProviderConnectionError("role exploration provider request failed") from exc
        except Exception as exc:
            name = type(exc).__name__.casefold()
            if "timeout" in name:
                raise RoleExplorationProviderTimeoutError("role exploration provider timed out") from exc
            if "connect" in name or "network" in name or "apierror" in name or "status" in name:
                raise RoleExplorationProviderConnectionError("role exploration provider request failed") from exc
            raise RoleExplorationProviderConnectionError("role exploration provider request failed") from exc

        try:
            data = json.loads(self._response_content(response))
        except (json.JSONDecodeError, RoleExplorationProviderInvalidResponseError) as exc:
            raise RoleExplorationProviderInvalidResponseError("provider response was not valid JSON") from exc
        if not isinstance(data, dict):
            raise RoleExplorationProviderInvalidResponseError("provider response must be a JSON object")
        try:
            payload = RoleExplorationProviderPayload.model_validate(data)
        except ValidationError as exc:
            raise RoleExplorationProviderInvalidResponseError("provider JSON did not match the role contract") from exc
        logger.info("role_exploration_provider_success item_count=%d", len(payload.items))
        return payload


_role_exploration_provider: RoleExplorationProvider | None = None


def set_role_exploration_provider(provider: RoleExplorationProvider | None) -> None:
    global _role_exploration_provider
    _role_exploration_provider = provider


def get_role_exploration_provider() -> RoleExplorationProvider:
    if _role_exploration_provider is not None:
        return _role_exploration_provider
    return OpenAIRoleExplorationProvider()
