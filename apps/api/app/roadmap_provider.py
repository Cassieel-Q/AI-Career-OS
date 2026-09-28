from __future__ import annotations

import json
import math
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .roadmap_schemas import RoadmapProposal


ROADMAP_DEFAULT_TIMEOUT_SECONDS = 45.0
ROADMAP_MAX_TIMEOUT_SECONDS = 120.0


def roadmap_timeout_seconds() -> float:
    override = os.getenv("ROADMAP_TIMEOUT_SECONDS", "").strip()
    raw = override or os.getenv("OPENAI_TIMEOUT_SECONDS", "30").strip() or "30"
    try:
        value = float(raw)
    except ValueError as exc:
        raise ValueError("ROADMAP_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > ROADMAP_MAX_TIMEOUT_SECONDS:
        raise ValueError(
            f"ROADMAP_TIMEOUT_SECONDS must be greater than 0 and no more than {ROADMAP_MAX_TIMEOUT_SECONDS:g}"
        )
    return value if override else max(value, ROADMAP_DEFAULT_TIMEOUT_SECONDS)


class RoadmapProviderError(RuntimeError):
    code = "provider_error"


class RoadmapProviderNotConfiguredError(RoadmapProviderError):
    pass


class RoadmapProviderTimeoutError(RoadmapProviderError):
    pass


class RoadmapProviderConnectionError(RoadmapProviderError):
    pass


class RoadmapProviderInvalidResponseError(RoadmapProviderError):
    code = "invalid_response"

    def __init__(
        self,
        message: str = "roadmap provider returned invalid structured output",
        *,
        reason: str = "schema_validation",
        validation_errors: list[dict[str, object]] | None = None,
    ) -> None:
        super().__init__(message)
        self.reason = reason
        self.validation_errors = validation_errors or []


class RoadmapProviderAuthenticationError(RoadmapProviderError):
    code = "authentication"


class RoadmapProvider(Protocol):
    def plan(self, *, target_role: str, weekly_hours: int, priorities: list[dict], remaining_context: dict | None = None) -> RoadmapProposal: ...


class OpenAIRoadmapProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise RoadmapProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = (urlparse(base_url or "").hostname or "").casefold().endswith("deepseek.com")
        try:
            self.timeout_seconds = roadmap_timeout_seconds()
        except ValueError as exc:
            raise RoadmapProviderNotConfiguredError("Roadmap provider timeout configuration is invalid") from exc
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=self.timeout_seconds,
                max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "0")),
            )
        except Exception as exc:
            raise RoadmapProviderNotConfiguredError("OpenAI provider configuration is invalid") from exc

    def plan(self, *, target_role: str, weekly_hours: int, priorities: list[dict], remaining_context: dict | None = None) -> RoadmapProposal:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Create a four-week actionable learning and job-search roadmap from the supplied capability priorities. "
                        "Return JSON only. The top-level object must contain exactly one key, weeks. "
                        "Return exactly four week objects in order with week_number values 1, 2, 3, and 4. "
                        "Do not wrap a week object in another week key. Each week object must contain exactly these keys: "
                        "week_number, objective, focus_gap_ids, measurable_outcome, tasks. "
                        "Each task object must contain exactly these keys: title, objective, estimated_minutes, related_gap_id, "
                        "completion_criteria. week_number and estimated_minutes must be integers; estimated_minutes must be an integer from 1 to 600. "
                        "Copy related_gap_id and focus_gap_ids exactly from the supplied confirmed priority gap_id values; "
                        "do not invent gap IDs. Use only supplied capability names, atomic requirements, and Profile evidence. "
                        "Respect weekly_hours. Do not include a status field; the application assigns the uppercase TODO status after persistence. "
                        "Do not add markdown, commentary, extra keys, or vague tasks such as Learn Python."
                    ),
                },
                {"role": "user", "content": json.dumps({"target_role": target_role, "weekly_hours": weekly_hours, "priorities": priorities, "remaining_context": remaining_context}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
            content = response.choices[0].message.content
            if not isinstance(content, str) or not content.strip():
                raise RoadmapProviderInvalidResponseError(reason="empty_response")
            try:
                data = json.loads(content)
            except json.JSONDecodeError as exc:
                raise RoadmapProviderInvalidResponseError(reason="json_decode") from exc
            try:
                return RoadmapProposal.model_validate(data)
            except ValidationError as exc:
                safe_errors = [
                    {"loc": list(error.get("loc", ())), "type": str(error.get("type", "validation_error"))}
                    for error in exc.errors()
                ]
                raise RoadmapProviderInvalidResponseError(
                    reason="schema_validation",
                    validation_errors=safe_errors,
                ) from exc
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise RoadmapProviderTimeoutError("roadmap provider timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError, ConnectionError) as exc:
            raise RoadmapProviderConnectionError("roadmap provider request failed") from exc
        except RoadmapProviderInvalidResponseError:
            raise
        except (IndexError, TypeError, AttributeError, ValueError) as exc:
            raise RoadmapProviderInvalidResponseError(reason="response_shape") from exc
        except Exception as exc:
            name = type(exc).__name__.casefold()
            if "auth" in name or "permission" in name:
                raise RoadmapProviderAuthenticationError("roadmap provider authentication failed") from exc
            if "timeout" in name:
                raise RoadmapProviderTimeoutError("roadmap provider timed out") from exc
            raise RoadmapProviderConnectionError("roadmap provider request failed") from exc


_provider: RoadmapProvider | None = None


def set_roadmap_provider(provider: RoadmapProvider | None) -> None:
    global _provider
    _provider = provider


def get_roadmap_provider() -> RoadmapProvider:
    return _provider if _provider is not None else OpenAIRoadmapProvider()
