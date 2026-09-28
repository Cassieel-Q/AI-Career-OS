from __future__ import annotations

import json
import logging
import math
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .jd_analysis_schemas import JdExtractionPayload

logger = logging.getLogger(__name__)


class JDAnalysisProviderError(RuntimeError):
    pass


class JDAnalysisProviderNotConfiguredError(JDAnalysisProviderError):
    pass


class JDAnalysisProviderTimeoutError(JDAnalysisProviderError):
    pass


class JDAnalysisProviderConnectionError(JDAnalysisProviderError):
    pass


class JDAnalysisProviderInvalidResponseError(JDAnalysisProviderError):
    pass


class JDAnalysisProvider(Protocol):
    def analyze(self, *, target_role: str, job_descriptions: list[dict[str, str | None]]) -> JdExtractionPayload: ...


def _timeout_seconds() -> float:
    raw = os.getenv("OPENAI_TIMEOUT_SECONDS", "30").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise JDAnalysisProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > 120:
        raise JDAnalysisProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS is outside the allowed range")
    return value


def _max_retries() -> int:
    raw = os.getenv("OPENAI_MAX_RETRIES", "0").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise JDAnalysisProviderNotConfiguredError("OPENAI_MAX_RETRIES must be an integer") from exc
    if value < 0 or value > 2:
        raise JDAnalysisProviderNotConfiguredError("OPENAI_MAX_RETRIES is outside the allowed range")
    return value


def _deepseek(base_url: str | None) -> bool:
    host = (urlparse(base_url or "").hostname or "").casefold()
    return host == "deepseek.com" or host.endswith(".deepseek.com")


class OpenAIJDAnalysisProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise JDAnalysisProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = _deepseek(base_url)
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
        except JDAnalysisProviderError:
            raise
        except Exception as exc:
            raise JDAnalysisProviderNotConfiguredError("OpenAI provider configuration is invalid") from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Extract only explicit requirements from the supplied job descriptions. Return JSON only with an `items` "
            "array, one object per supplied JD: {jd_id, items:[{name, category, evidence_text}]}. Categories are "
            "SKILL, RESPONSIBILITY, EXPERIENCE, EDUCATION, DOMAIN, COLLABORATION, OTHER. Every evidence_text must "
            "be one contiguous verbatim excerpt from that exact JD. Do not infer salary, hidden preferences, seniority, "
            "frequency, or facts absent from the text. Never merge evidence from different JDs."
        )

    def _request(self, content: str) -> object:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": content},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            return self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise JDAnalysisProviderTimeoutError("JD analysis provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise JDAnalysisProviderConnectionError("JD analysis provider request failed") from exc
        except Exception as exc:
            name = type(exc).__name__.casefold()
            if "timeout" in name:
                raise JDAnalysisProviderTimeoutError("JD analysis provider timed out") from exc
            raise JDAnalysisProviderConnectionError("JD analysis provider request failed") from exc

    @staticmethod
    def _content(response: object) -> str:
        try:
            content = response.choices[0].message.content  # type: ignore[attr-defined]
        except Exception as exc:
            raise JDAnalysisProviderInvalidResponseError("JD analysis response had no message content") from exc
        if not isinstance(content, str) or not content.strip():
            raise JDAnalysisProviderInvalidResponseError("JD analysis response had no JSON content")
        return content

    def analyze(self, *, target_role: str, job_descriptions: list[dict[str, str | None]]) -> JdExtractionPayload:
        payload = json.dumps({"target_role": target_role, "job_descriptions": job_descriptions}, ensure_ascii=False, separators=(",", ":"))
        data = json.loads(self._content(self._request(payload)))
        if not isinstance(data, dict):
            raise JDAnalysisProviderInvalidResponseError("JD analysis response must be an object")
        try:
            return JdExtractionPayload.model_validate(data)
        except (ValidationError, TypeError, ValueError) as exc:
            raise JDAnalysisProviderInvalidResponseError("JD analysis response did not match the contract") from exc


_provider: JDAnalysisProvider | None = None


def set_jd_analysis_provider(provider: JDAnalysisProvider | None) -> None:
    global _provider
    _provider = provider


def get_jd_analysis_provider() -> JDAnalysisProvider:
    return _provider if _provider is not None else OpenAIJDAnalysisProvider()
