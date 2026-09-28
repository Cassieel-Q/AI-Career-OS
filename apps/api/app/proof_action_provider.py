from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib.parse import urlparse

import httpx
from pydantic import ValidationError

from .proof_schemas import ProofActionCreate, ProofGuidanceRead


class ProofActionProviderError(RuntimeError):
    pass


class ProofActionProviderNotConfiguredError(ProofActionProviderError):
    pass


class ProofActionProviderTimeoutError(ProofActionProviderError):
    pass


class ProofActionProviderConnectionError(ProofActionProviderError):
    pass


class ProofActionProviderInvalidResponseError(ProofActionProviderError):
    def __init__(self, message: str = "proof action provider returned invalid structured output", *, reason: str = "schema_validation") -> None:
        super().__init__(message)
        self.reason = reason


class ProofActionProvider(Protocol):
    def plan(self, *, claim: dict[str, object], debrief: dict[str, object], evidence: list[dict[str, object]]) -> ProofActionCreate: ...

    def guidance(self, *, claim: dict[str, object], debrief: dict[str, object], evidence: list[dict[str, object]], action_type: str) -> ProofGuidanceRead: ...


def _is_deepseek(base_url: str | None) -> bool:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


class OpenAIProofActionProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise ProofActionProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_PROOF_ACTION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = _is_deepseek(base_url)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            timeout = os.getenv("OPENAI_PROOF_ACTION_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "12"
            options: dict[str, object] = {"api_key": api_key, "timeout": float(timeout), "max_retries": int(os.getenv("OPENAI_MAX_RETRIES", "0"))}
            if base_url:
                options["base_url"] = base_url
            self.client = OpenAI(**options)
        except Exception as exc:
            raise ProofActionProviderNotConfiguredError("proof action provider configuration is invalid") from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Turn one interview debrief into one to three minimal proof actions. Return JSON only with an actions array. "
            "Each action must produce a reviewable artifact, include why_now, target_claim, one of the four gap types, "
            "estimated_hours, artifact_type, definition_of_done, and expected_evidence. Prefer a dataset, report, demo, "
            "experiment log, GitHub project, or written decision record over generic study advice. Use only supplied claim "
            "and evidence; use supplied interview_intel question patterns when relevant; do not invent results or numbers. Do not add keys or markdown."
        )

    def plan(self, *, claim: dict[str, object], debrief: dict[str, object], evidence: list[dict[str, object]]) -> ProofActionCreate:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps({"claim": claim, "debrief": debrief, "evidence": evidence}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProofActionProviderTimeoutError("proof action provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise ProofActionProviderConnectionError("proof action provider request failed") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.casefold():
                raise ProofActionProviderTimeoutError("proof action provider timed out") from exc
            raise ProofActionProviderConnectionError("proof action provider request failed") from exc
        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise ProofActionProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise ProofActionProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise ProofActionProviderInvalidResponseError(reason="json_decode") from exc
        try:
            return ProofActionCreate.model_validate(data)
        except (ValidationError, TypeError, ValueError) as exc:
            raise ProofActionProviderInvalidResponseError(reason="schema_validation") from exc

    @staticmethod
    def _guidance_prompt() -> str:
        return (
            "根据一次模拟面试复盘，直接给用户可执行的补强建议，返回 JSON only。"
            "action_type=FACT_QA_NOTES 时只生成 3-5 个中文事实追问，围绕时间、角色、个人动作、决策、结果和可核对来源；"
            "action_type=PROJECT_WRITEUP 时生成项目补齐指南，包含项目背景、个人动作、结果验证、建议学习的知识和可产出物。"
            "优先参考 debrief 中的 interview_intel 面经问题模式；不要要求上传证明、链接或提交材料，不要编造数字或已完成的经历。"
            "字段只能是 title, summary, questions, steps, learning, expected_outputs。所有内容使用简体中文。"
        )

    def guidance(self, *, claim: dict[str, object], debrief: dict[str, object], evidence: list[dict[str, object]], action_type: str) -> ProofGuidanceRead:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._guidance_prompt()},
                {"role": "user", "content": json.dumps({"action_type": action_type, "claim": claim, "debrief": debrief, "evidence": evidence}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise ProofActionProviderTimeoutError("proof guidance provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise ProofActionProviderConnectionError("proof guidance provider request failed") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.casefold():
                raise ProofActionProviderTimeoutError("proof guidance provider timed out") from exc
            raise ProofActionProviderConnectionError("proof guidance provider request failed") from exc
        try:
            content = response.choices[0].message.content
            data = json.loads(content) if isinstance(content, str) else None
            if not isinstance(data, dict):
                raise ValueError("response_shape")
            return ProofGuidanceRead.model_validate({
                "claim_id": claim["id"],
                "action_type": action_type,
                "title": data.get("title") or ("事实追问" if action_type == "FACT_QA_NOTES" else "项目补齐指南"),
                "summary": data.get("summary") or "请根据下面的建议补充可核对的事实。",
                "questions": data.get("questions") or [],
                "steps": data.get("steps") or [],
                "learning": data.get("learning") or [],
                "expected_outputs": data.get("expected_outputs") or [],
                "generated_by": "llm",
            })
        except (IndexError, KeyError, json.JSONDecodeError, ValidationError, TypeError, ValueError) as exc:
            raise ProofActionProviderInvalidResponseError(reason="schema_validation") from exc


_provider: ProofActionProvider | None = None


def set_proof_action_provider(provider: ProofActionProvider | None) -> None:
    global _provider
    _provider = provider


def get_proof_action_provider() -> ProofActionProvider:
    return _provider if _provider is not None else OpenAIProofActionProvider()
