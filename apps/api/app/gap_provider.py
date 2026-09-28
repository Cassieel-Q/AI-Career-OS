from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .gap_schemas import GapProposalPayload


class GapProviderError(RuntimeError):
    pass


class GapProviderNotConfiguredError(GapProviderError):
    pass


class GapProviderTimeoutError(GapProviderError):
    pass


class GapProviderConnectionError(GapProviderError):
    pass


class GapProviderUpstreamError(GapProviderConnectionError):
    """The upstream API rejected or failed the request with a status response."""

    def __init__(
        self,
        message: str = "gap analysis provider returned an upstream error",
        *,
        status_code: int | None = None,
        provider_code: str | None = None,
        provider_type: str | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.provider_code = provider_code
        self.provider_type = provider_type


class GapProviderInvalidResponseError(GapProviderError):
    def __init__(
        self,
        message: str = "gap analysis provider returned invalid structured output",
        *,
        reason: str = "schema_validation",
    ) -> None:
        super().__init__(message)
        self.reason = reason


class GapAnalysisProvider(Protocol):
    def compare(self, *, requirements: list[dict], profile_facts: list[dict]) -> GapProposalPayload: ...


class OpenAIGapAnalysisProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise GapProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = (urlparse(base_url or "").hostname or "").casefold().endswith("deepseek.com")
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            self.client = OpenAI(
                api_key=api_key,
                base_url=base_url,
                timeout=float(os.getenv("OPENAI_TIMEOUT_SECONDS", "30")),
                max_retries=int(os.getenv("OPENAI_MAX_RETRIES", "0")),
            )
        except Exception as exc:
            raise GapProviderNotConfiguredError("OpenAI provider configuration is invalid") from exc

    def compare(self, *, requirements: list[dict], profile_facts: list[dict]) -> GapProposalPayload:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Compare each supplied capability cluster with only the supplied confirmed Profile facts. "
                        "Return a JSON object with one item per supplied capability using its id as requirement_id: "
                        "{items:[{requirement_id,state,severity,proximity,feasibility,rationale,evidence_refs}]}. "
                        "Allowed states are MATCHED, PARTIAL, MISSING, UNCERTAIN. "
                        "severity, proximity, and feasibility must each be exactly LOW, MEDIUM, or HIGH in uppercase. "
                        "Do not infer proficiency or add facts. "
                        "evidence_refs must contain only supplied Profile fact UUIDs."
                    ),
                },
                {"role": "user", "content": json.dumps({"requirements": requirements, "profile_facts": profile_facts}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise GapProviderTimeoutError("gap analysis provider timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError, ConnectionError) as exc:
            raise GapProviderConnectionError("gap analysis provider request failed") from exc
        except Exception as exc:
            if any(base.__name__ == "APIStatusError" for base in type(exc).__mro__):
                status_code = getattr(exc, "status_code", None)
                if not isinstance(status_code, int):
                    status_code = getattr(getattr(exc, "response", None), "status_code", None)
                body = getattr(exc, "body", None)
                details = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body
                if not isinstance(details, dict):
                    details = {}
                raise GapProviderUpstreamError(
                    status_code=status_code if isinstance(status_code, int) else None,
                    provider_code=details.get("code") if isinstance(details.get("code"), str) else None,
                    provider_type=details.get("type") if isinstance(details.get("type"), str) else None,
                ) from exc
            raise GapProviderConnectionError("gap analysis provider request failed") from exc

        try:
            content = response.choices[0].message.content
        except (AttributeError, IndexError, TypeError) as exc:
            raise GapProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise GapProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise GapProviderInvalidResponseError(reason="json_decode") from exc
        try:
            return GapProposalPayload.model_validate(data)
        except (ValidationError, TypeError, ValueError) as exc:
            raise GapProviderInvalidResponseError(reason="schema_validation") from exc


_provider: GapAnalysisProvider | None = None


def set_gap_analysis_provider(provider: GapAnalysisProvider | None) -> None:
    global _provider
    _provider = provider


def get_gap_analysis_provider() -> GapAnalysisProvider:
    return _provider if _provider is not None else OpenAIGapAnalysisProvider()
