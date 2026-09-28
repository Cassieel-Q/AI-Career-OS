from __future__ import annotations

import json
import os
from typing import Any, Protocol
from urllib.parse import urlparse
from uuid import UUID

import httpx
from pydantic import ValidationError

from .proof_schemas import InterviewGapType, InterviewResponsePayload


class InterviewProviderError(RuntimeError):
    pass


class InterviewProviderNotConfiguredError(InterviewProviderError):
    pass


class InterviewProviderTimeoutError(InterviewProviderError):
    pass


class InterviewProviderConnectionError(InterviewProviderError):
    pass


class InterviewProviderInvalidResponseError(InterviewProviderError):
    def __init__(self, message: str = "interview provider returned invalid structured output", *, reason: str = "schema_validation") -> None:
        super().__init__(message)
        self.reason = reason


class InterviewProvider(Protocol):
    def ask(self, *, target_job: dict[str, object], claim: dict[str, object], evidence: list[dict[str, object]], skills: list[dict[str, object]], turns: list[dict[str, object]], answer: str | None) -> InterviewResponsePayload: ...


def _is_deepseek(base_url: str | None) -> bool:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


class OpenAIInterviewProvider:
    def __init__(self, *, client: Any | None = None) -> None:
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise InterviewProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_INTERVIEW_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = _is_deepseek(base_url)
        if client is not None:
            self.client = client
            return
        try:
            from openai import OpenAI

            # Interview turns are interactive. Keep the default provider wait
            # short enough that the deterministic Chinese fallback can keep
            # the user moving; deployments can raise it explicitly.
            timeout = os.getenv("OPENAI_INTERVIEW_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "15"
            options: dict[str, object] = {"api_key": api_key, "timeout": float(timeout), "max_retries": int(os.getenv("OPENAI_MAX_RETRIES", "0"))}
            if base_url:
                options["base_url"] = base_url
            self.client = OpenAI(**options)
        except Exception as exc:
            raise InterviewProviderNotConfiguredError("interview provider configuration is invalid") from exc

    @staticmethod
    def _system_prompt() -> str:
        return (
            "Run a claim-specific text interview. Use only the supplied target JD, the latest confirmed final_resume bullets "
            "(prefer those bullets when choosing what to ask), resume claim, Profile evidence, curated skill pack, interview pack topics, "
            "and bounded interview_intel question patterns from real curated company reports, "
            "and prior turns. Ask one concrete question at a time and return JSON only with "
            "question, skill_id, followup_dimensions, and evaluation. Evaluation must include a simple integer score 0-10 "
            "when an answer is present, plus 1-2 strong_points, 1-2 weak_points, a concise recommended_next_action, "
            "and reference_answer showing a better concise answer grounded in supplied facts. "
            "Use Simplified Chinese for every question, feedback, suggested answer, and next action. "
            "Do not invent user outcomes or numbers. When interview_intel is present, prefer its matching question patterns and focus signals; do not present source IDs as user-facing text. "
            "After enough turns, set question and skill_id to null and classify one gap type: KNOWLEDGE_GAP, "
            "PROJECT_GAP, EVIDENCE_GAP, or ARTICULATION_GAP. Keep evidence_refs to supplied UUIDs and never add keys."
        )

    @staticmethod
    def _as_str_list(value: object, *, max_items: int = 8, max_len: int = 300) -> list[str]:
        if value is None:
            return []
        if isinstance(value, str):
            text = value.strip()
            return [text[:max_len]] if text else []
        if not isinstance(value, list):
            return []
        out: list[str] = []
        for item in value:
            if isinstance(item, str) and item.strip():
                out.append(item.strip()[:max_len])
            elif item is not None:
                text = str(item).strip()
                if text:
                    out.append(text[:max_len])
            if len(out) >= max_items:
                break
        return out

    @staticmethod
    def _as_uuid_list(value: object, *, max_items: int = 12) -> list[str]:
        if value is None:
            return []
        raw = value if isinstance(value, list) else [value]
        out: list[str] = []
        for item in raw:
            try:
                out.append(str(UUID(str(item).strip())))
            except Exception:
                continue
            if len(out) >= max_items:
                break
        return out

    @classmethod
    def _normalize_gap_type(cls, value: object) -> str | None:
        if value is None:
            return None
        raw = str(value).strip().upper().replace(" ", "_").replace("-", "_")
        if not raw:
            return None
        aliases = {
            "KNOWLEDGE": "KNOWLEDGE_GAP",
            "KNOWLEDGE_GAP": "KNOWLEDGE_GAP",
            "PROJECT": "PROJECT_GAP",
            "PROJECT_GAP": "PROJECT_GAP",
            "EVIDENCE": "EVIDENCE_GAP",
            "EVIDENCE_GAP": "EVIDENCE_GAP",
            "ARTICULATION": "ARTICULATION_GAP",
            "ARTICULATION_GAP": "ARTICULATION_GAP",
        }
        mapped = aliases.get(raw)
        if mapped is None:
            try:
                return InterviewGapType(raw).value
            except Exception:
                return None
        return mapped

    @classmethod
    def _normalize_evaluation(cls, value: object) -> dict[str, object]:
        """Soft-normalize LLM evaluation shapes (mirrors claim_provider soft path)."""
        label_defaults = {
            "OPENING": "开场轮次，尚未形成完整评价",
            "PASS": "本轮表现可接受，继续追问",
            "FAIL": "本轮回答偏弱，需继续澄清",
            "CONTINUE": "继续追问以收集更多证据",
            "INCOMPLETE": "评价信息不完整，已做结构化归一",
        }
        if isinstance(value, str):
            label = value.strip()
            key = label.upper().replace(" ", "_").replace("-", "_")
            why = label_defaults.get(key) or (f"模型返回了简短评价标签：{label}" if label else "模型返回了非结构化评价，已做归一")
            return {
                "score": None,
                "reference_answer": None,
                "strong_points": [],
                "weak_points": [],
                "gap_type": None,
                "why": why[:600],
                "evidence_refs": [],
                "recommended_next_action": None,
            }
        if not isinstance(value, dict):
            return {
                "score": None,
                "reference_answer": None,
                "strong_points": [],
                "weak_points": [],
                "gap_type": None,
                "why": "模型未返回结构化评价，已用空评价占位",
                "evidence_refs": [],
                "recommended_next_action": None,
            }

        score_raw = value.get("score") or value.get("rating")
        try:
            score = max(0, min(10, int(float(score_raw)))) if score_raw is not None else None
        except (TypeError, ValueError):
            score = None
        why_raw = value.get("why") or value.get("reason") or value.get("summary") or value.get("note")
        if isinstance(why_raw, str):
            why = why_raw.strip()[:600] or None
        else:
            why = None

        next_raw = value.get("recommended_next_action") or value.get("next_action") or value.get("recommendation")
        if isinstance(next_raw, str):
            recommended = next_raw.strip()[:600] or None
        else:
            recommended = None

        return {
            "score": score,
            "reference_answer": str(value.get("reference_answer") or value.get("sample_answer") or "").strip()[:1200] or None,
            "strong_points": cls._as_str_list(value.get("strong_points") or value.get("strengths"), max_items=8, max_len=300),
            "weak_points": cls._as_str_list(value.get("weak_points") or value.get("weaknesses"), max_items=8, max_len=300),
            "gap_type": cls._normalize_gap_type(value.get("gap_type") or value.get("gap")),
            "why": why,
            "evidence_refs": cls._as_uuid_list(value.get("evidence_refs") or value.get("evidence") or []),
            "recommended_next_action": recommended,
        }

    @classmethod
    def _normalize_interview_payload(cls, data: object) -> dict[str, object]:
        if not isinstance(data, dict):
            raise InterviewProviderInvalidResponseError(reason="response_shape")

        question = data.get("question")
        if isinstance(question, str):
            question = question.strip()[:1_000] or None
        elif question is not None:
            text = str(question).strip()
            question = text[:1_000] if text else None

        skill_id = data.get("skill_id")
        if isinstance(skill_id, str):
            skill_id = skill_id.strip()[:64] or None
        elif skill_id is not None:
            text = str(skill_id).strip()
            skill_id = text[:64] if text else None

        followups = cls._as_str_list(
            data.get("followup_dimensions") or data.get("followups") or data.get("dimensions"),
            max_items=8,
            max_len=64,
        )

        evaluation = data.get("evaluation")
        if evaluation is None and any(key in data for key in ("score", "rating", "strong_points", "weak_points", "gap_type", "why")):
            evaluation = {
                "strong_points": data.get("strong_points"),
                "weak_points": data.get("weak_points"),
                "score": data.get("score") or data.get("rating"),
                "reference_answer": data.get("reference_answer") or data.get("sample_answer"),
                "gap_type": data.get("gap_type"),
                "why": data.get("why"),
                "evidence_refs": data.get("evidence_refs"),
                "recommended_next_action": data.get("recommended_next_action"),
            }

        return {
            "question": question,
            "skill_id": skill_id,
            "followup_dimensions": followups,
            "evaluation": cls._normalize_evaluation(evaluation),
        }

    def ask(self, *, target_job: dict[str, object], claim: dict[str, object], evidence: list[dict[str, object]], skills: list[dict[str, object]], turns: list[dict[str, object]], answer: str | None) -> InterviewResponsePayload:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._system_prompt()},
                {"role": "user", "content": json.dumps({"target_job": target_job, "claim": claim, "evidence": evidence, "skills": skills, "turns": turns, "answer": answer}, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            response = self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise InterviewProviderTimeoutError("interview provider timed out") from exc
        except (ConnectionError, httpx.RequestError, httpx.HTTPStatusError) as exc:
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        except Exception as exc:
            if "timeout" in type(exc).__name__.casefold():
                raise InterviewProviderTimeoutError("interview provider timed out") from exc
            raise InterviewProviderConnectionError("interview provider request failed") from exc
        try:
            content = response.choices[0].message.content
        except Exception as exc:
            raise InterviewProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise InterviewProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise InterviewProviderInvalidResponseError(reason="json_decode") from exc
        try:
            normalized = self._normalize_interview_payload(data)
            return InterviewResponsePayload.model_validate(normalized)
        except InterviewProviderInvalidResponseError:
            raise
        except (ValidationError, TypeError, ValueError) as exc:
            raise InterviewProviderInvalidResponseError(reason="schema_validation") from exc


_provider: InterviewProvider | None = None


def set_interview_provider(provider: InterviewProvider | None) -> None:
    global _provider
    _provider = provider


def get_interview_provider() -> InterviewProvider:
    return _provider if _provider is not None else OpenAIInterviewProvider()
