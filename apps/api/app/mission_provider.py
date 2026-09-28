from __future__ import annotations

import json
import re
import math
import os
from typing import Any, Protocol, TypeVar
from urllib.parse import urlparse

import httpx
from pydantic import BaseModel, ValidationError

import logging
import time

from .mission_schemas import (
    ExperienceSelectionPayload,
    InterviewPackPayload,
    JobExtractionPayload,
    RedTeamPayload,
    ResumeStrategyPayload,
    TargetResumeGenerationResult,
    TargetResumePayload,
    WhatMattersPayload,
)

logger = logging.getLogger("career_os.target_resume")
# Ensure visible under uvicorn default config (root often WARNING).
if not logger.handlers:
    _uv = logging.getLogger("uvicorn.error")
    logger.setLevel(logging.INFO)
    logger.propagate = True
    if _uv.handlers:
        for _h in _uv.handlers:
            logger.addHandler(_h)
    else:
        _sh = logging.StreamHandler()
        _sh.setLevel(logging.INFO)
        logger.addHandler(_sh)



class MissionProviderError(RuntimeError):
    pass


class MissionProviderNotConfiguredError(MissionProviderError):
    pass


class MissionProviderTimeoutError(MissionProviderError):
    pass


class MissionProviderConnectionError(MissionProviderError):
    pass


class MissionProviderUpstreamError(MissionProviderConnectionError):
    def __init__(self, message: str = "mission provider returned an upstream error", *, status_code: int | None = None, provider_code: str | None = None, provider_type: str | None = None):
        super().__init__(message)
        self.status_code = status_code
        self.provider_code = provider_code
        self.provider_type = provider_type


class MissionProviderInvalidResponseError(MissionProviderError):
    def __init__(self, message: str = "mission provider returned invalid structured output", *, reason: str = "schema_validation", validation_errors: list[dict[str, object]] | None = None):
        super().__init__(message)
        self.reason = reason
        self.validation_errors = validation_errors or []


class MissionProvider(Protocol):

    def parse_jd(self, raw_text: str) -> JobExtractionPayload: ...

    def build_what_matters(self, *, raw_text: str, extraction: JobExtractionPayload, interview_intel: list[dict[str, object]]) -> WhatMattersPayload: ...

    def select_experiences(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload) -> ExperienceSelectionPayload: ...

    def build_resume_strategy(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload, selections: ExperienceSelectionPayload) -> ResumeStrategyPayload: ...

    def build_target_resume(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, strategy: ResumeStrategyPayload, version: int, what_matters: WhatMattersPayload | None = None, selections: ExperienceSelectionPayload | None = None, interview_intel: list[dict[str, object]] | None = None, raw_jd: str | None = None, mission_id: str | None = None) -> TargetResumePayload: ...

    def red_team(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload, target_resume: TargetResumePayload) -> RedTeamPayload: ...

    def build_interview_pack(self, *, extraction: JobExtractionPayload, what_matters: WhatMattersPayload, interview_intel: list[dict[str, object]], target_resume: TargetResumePayload, red_team: RedTeamPayload) -> InterviewPackPayload: ...


_MODEL_T = TypeVar("_MODEL_T", bound=BaseModel)


def _is_deepseek(base_url: str | None) -> bool:
    hostname = (urlparse(base_url or "").hostname or "").casefold()
    return hostname == "deepseek.com" or hostname.endswith(".deepseek.com")


def _timeout_seconds() -> float:
    raw = (os.getenv("OPENAI_MISSION_TIMEOUT_SECONDS") or os.getenv("OPENAI_TIMEOUT_SECONDS") or "15").strip()
    try:
        value = float(raw)
    except ValueError as exc:
        raise MissionProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS must be a number") from exc
    if not math.isfinite(value) or value <= 0 or value > 120:
        raise MissionProviderNotConfiguredError("OPENAI_TIMEOUT_SECONDS is outside the allowed range")
    return value


def _max_retries() -> int:
    raw = os.getenv("OPENAI_MAX_RETRIES", "0").strip()
    try:
        value = int(raw)
    except ValueError as exc:
        raise MissionProviderNotConfiguredError("OPENAI_MAX_RETRIES must be an integer") from exc
    if value < 0 or value > 2:
        raise MissionProviderNotConfiguredError("OPENAI_MAX_RETRIES is outside the allowed range")
    return value


class OpenAIMissionProvider:
    def __init__(self, *, client: Any | None = None):
        api_key = os.getenv("OPENAI_API_KEY", "").strip()
        if not api_key and client is None:
            raise MissionProviderNotConfiguredError("OPENAI_API_KEY is not configured")
        base_url = os.getenv("OPENAI_BASE_URL")
        self.model = os.getenv("OPENAI_MISSION_MODEL") or os.getenv("OPENAI_MODEL") or "gpt-4o-mini"
        self.is_deepseek = _is_deepseek(base_url)
        if client is not None:
            self.client = client
        else:
            try:
                from openai import OpenAI

                options: dict[str, object] = {"api_key": api_key, "timeout": _timeout_seconds(), "max_retries": _max_retries()}
                if base_url:
                    options["base_url"] = base_url
                self.client = OpenAI(**options)
            except MissionProviderError:
                raise
            except Exception as exc:
                raise MissionProviderNotConfiguredError("mission provider configuration is invalid") from exc

    @staticmethod
    def _prompt(operation: str) -> str:
        base = (
            f"Perform the {operation} operation for one Job Mission. Use only supplied JD, Profile evidence, resume_skills, interview_intel, "
                "resume, and curated intel. Never invent a company, requirement, number, outcome, or tool. "
                "When the JD does not identify a company or seniority, set those identity fields to UNKNOWN. "
            "Do not set positioning_statement or narrative fields to UNKNOWN. Every conclusion must carry "
            "an evidence ref copied from the supplied input. Return one JSON object with ONLY the output schema fields "
            "for this operation. Do not echo the input payload. Do not wrap with type/json_object or meta keys. "
            "No markdown and no extra keys. "
            "Write all user-facing narrative text in Simplified Chinese "
            "(topic, why, question_patterns, evidence_expected, summaries, findings, reasons, next steps). "
            "Keep schema field names and enum/code values unchanged."
        )
        if "interview pack" in operation.casefold():
            base += (
                " Interview-pack rules: (1) Prefer questions and themes from interview_intel "
                "(uploaded Nowcoder/Niuke or company interview intel) when present and relevant. "
                "(2) If company in JD is UNKNOWN or does not match intel company, still use intel items "
                "that match role/skills, then fill remaining slots with high-frequency questions "
                "grounded in what_matters + target_resume (do not invent employers or metrics). "
                "(3) topic/why/question_patterns/evidence_expected must be Simplified Chinese. "
                "(4) Each topic MUST have DISTINCT question_patterns shaped for that capability/focus — "
                "BAN identical copy-paste templates that only swap the capability name "
                "(never reuse「哪个近期项目最能证明你的「X」？」across topics). "
                "(5) evidence_expected (aka knowledge_to_study) MUST be 2-4 concrete Simplified Chinese "
                "bullets per topic: 面试高频问法、该准备的概念、可用证据方向; never empty; "
                "never the literal placeholder「(待补充：优先牛客/该公司面经要点)」."
            )
        op_l = operation.casefold()
        if "target resume" in op_l or "resume optimization" in op_l:
            return (
                "You are CareerOS Resume Optimization. Output JSON only. "
                "Write an evidence-grounded Chinese one-page AI PM / intern Target Resume for ONE Job Mission. "
                "Never invent metrics, users, tools, headcount, or leadership claims. When a requested JD capability is not covered by the source resume, add one or two concrete JD-specific synthetic project drafts; for an intelligent-hardware role prefer product definition, prototype integration, test metrics, and a PRD/demo deliverable. These are project ideas for the candidate to complete and edit, not claims about prior employment. "
                "Priority: JD relevance > Evidence strength > Strategy > Resume Skills > wording. "
                "Master Resume must not be modified—only propose grounded rewrites. "
                "Preserve SOURCE_RESUME section order and basic hierarchy exactly when section_order is supplied; "
                "do not invent a new Summary/摘要 section or a new resume schema. "
                "Template: A basic info (no invent) B optional 1-line positioning C education factual "
                "D 2-4 most relevant experiences with 2-4 bullets each using action+method+result "
                "E skills from evidence F optional awards only if valuable. "
                "Return only the 3-4 highest-value rewrite suggestions; do not produce a long audit report. "
                "Do NOT create a standalone Summary/摘要 block; positioning_summary is a one-line internal note only. "
                "Every bullet must include grounding_status: SUPPORTED | NEEDS_CONFIRMATION | UNSUPPORTED. "
                "Any proposed fact, metric, tool, responsibility, or result not explicitly supported by SOURCE_RESUME "
                "must be NEEDS_CONFIRMATION and clearly flagged, except synthetic project drafts which must have source_experience_id=null, display_name prefixed with 项目草案, and risk_flags containing SYNTHETIC_PROJECT. "
                "Use SOURCE_RESUME / GLOBAL_EVIDENCE / CONFIRMED_EXPERIENCE_DECISIONS for real experiences; synthetic projects may be derived from the JD capability gap but must be concrete, JD-specific, and must not claim a real employer or unverified numeric result. "
                "Apply APPLICABLE_RESUME_SKILLS. "
                "Use COMPANY_INTERVIEW_CONTEXT focus and real question patterns to prioritize experiences that can survive target-company follow-up questions, and to make each rewrite interview-ready; never copy questions verbatim into resume bullets. "
                "Return JSON with keys: positioning_summary, section_order, experiences"
                "[{source_experience_id, display_name, role_in_resume, include, bullets"
                "[{original_text, suggested_text, why_changed, target_capabilities, jd_evidence_refs, "
                "evidence_refs, resume_skill_refs, grounding_status, risk_flags}]}], skills, excluded_suggestions."
            )
        return base

    def _request(self, *, operation: str, payload: dict[str, object]) -> object:
        request: dict[str, object] = {
            "model": self.model,
            "messages": [
                {"role": "system", "content": self._prompt(operation)},
                {"role": "user", "content": json.dumps(payload, ensure_ascii=False, separators=(",", ":"))},
            ],
            "response_format": {"type": "json_object"},
        }
        if self.is_deepseek:
            request["extra_body"] = {"thinking": {"type": "disabled"}}
        try:
            return self.client.chat.completions.create(**request)
        except (TimeoutError, httpx.TimeoutException) as exc:
            raise MissionProviderTimeoutError("mission provider timed out") from exc
        except (httpx.RequestError, httpx.HTTPStatusError, ConnectionError) as exc:
            raise MissionProviderConnectionError("mission provider request failed") from exc
        except Exception as exc:
            if any(base.__name__ == "APIStatusError" for base in type(exc).__mro__):
                status_code = getattr(exc, "status_code", None)
                body = getattr(exc, "body", None)
                details = body.get("error") if isinstance(body, dict) and isinstance(body.get("error"), dict) else body
                if not isinstance(details, dict):
                    details = {}
                raise MissionProviderUpstreamError(
                    status_code=status_code if isinstance(status_code, int) else None,
                    provider_code=details.get("code") if isinstance(details.get("code"), str) else None,
                    provider_type=details.get("type") if isinstance(details.get("type"), str) else None,
                ) from exc
            if "timeout" in type(exc).__name__.casefold():
                raise MissionProviderTimeoutError("mission provider timed out") from exc
            raise MissionProviderConnectionError("mission provider request failed") from exc


    @staticmethod
    def _unwrap_payload(data: dict, model_type: type) -> dict:
        name = getattr(model_type, "__name__", "")
        unwrap_keys = {
            "ResumeStrategyPayload": ("strategy", "resume_strategy", "result", "data", "output", "payload"),
            "TargetResumePayload": ("target_resume", "resume", "result", "data", "output", "payload"),
            "TargetResumeGenerationResult": ("target_resume", "resume", "result", "data", "output", "payload", "generation"),
            "WhatMattersPayload": ("what_matters", "result", "data", "output", "payload"),
            "RedTeamPayload": ("red_team", "findings_payload", "result", "data", "output", "payload"),
            "InterviewPackPayload": ("interview_pack", "pack", "result", "data", "output", "payload"),
            "JobExtractionPayload": ("extraction", "parsed_jd", "result", "data", "output", "payload"),
            "ExperienceSelectionPayload": ("selections_payload", "result", "data", "output", "payload"),
        }
        current = data
        for key in unwrap_keys.get(name, ()):
            nested = current.get(key) if isinstance(current, dict) else None
            if isinstance(nested, dict) and nested:
                current = nested
                break
        return current if isinstance(current, dict) else data

    @staticmethod
    def _uuid_strings(values: object) -> list[str]:
        from uuid import UUID

        out: list[str] = []
        if not isinstance(values, list):
            return out
        for value in values:
            try:
                out.append(str(UUID(str(value))))
            except Exception:
                continue
        return out


    @staticmethod
    def _maybe_split_csv(value: object) -> object:
        if isinstance(value, str) and any(sep in value for sep in (",", "，", ";", "；")):
            buf = value
            for sep in ("，", "；", ";", ","):
                buf = buf.replace(sep, ",")
            return [part.strip() for part in buf.split(",") if part.strip()]
        return value

    @staticmethod
    def _string_list(value: object, *, default: list[str] | None = None, max_items: int = 20) -> list[str]:
        if isinstance(value, str):
            text = value.strip()
            return [text] if text else list(default or [])
        if isinstance(value, list):
            out: list[str] = []
            for item in value:
                if isinstance(item, str) and item.strip():
                    out.append(item.strip())
                elif item is not None and not isinstance(item, (dict, list)):
                    text = str(item).strip()
                    if text:
                        out.append(text)
            return out[:max_items]
        return list(default or [])

    @staticmethod
    def _normalize_resume_strategy(data: dict) -> dict:
        positioning = data.get("positioning_statement") or data.get("positioning") or data.get("candidate_story") or data.get("story")
        if not isinstance(positioning, str):
            positioning = ""
        positioning = OpenAIMissionProvider._strip_evidence_dump(positioning.strip())
        if positioning.upper() in {"", "UNKNOWN", "N/A", "NONE", "NULL"}:
            company = str(data.get("company") or "").strip()
            role = str(data.get("role") or "").strip()
            if company and role and company.upper() != "UNKNOWN" and role.upper() != "UNKNOWN":
                positioning = f"For {company} · {role}, lead with the confirmed experiences that best prove the role's required capabilities, without inventing unproven outcomes."
            else:
                positioning = "Lead with the confirmed experiences that best prove this role's required capabilities, without inventing unproven outcomes."

        order = data.get("recommended_experience_order") or data.get("experience_order") or []
        order_ids = OpenAIMissionProvider._uuid_strings(order)

        guidance_raw = data.get("experience_guidance") or data.get("guidance") or []
        guidance: list[dict] = []
        placeholder_guidance = "support the target role narrative with confirmed evidence only."

        def _guidance_text(value: object, experience_id: object) -> str:
            text = str(value or "").strip()
            if not text or text.casefold() == placeholder_guidance:
                label = str(experience_id or "这段经历").strip() or "这段经历"
                return f"围绕{label}的已确认事实组织与岗位相关的简历表述，避免添加未经证实的结果。"
            return text

        if isinstance(guidance_raw, dict):
            for exp_id, value in guidance_raw.items():
                if isinstance(value, str):
                    text = _guidance_text(value, exp_id)
                    guidance.append({
                        "experience_id": str(exp_id),
                        "role_in_story": text[:600],
                        "what_to_highlight": [],
                        "what_to_avoid": ["Do not invent metrics, tools, or outcomes not present in profile evidence"],
                        "target_capabilities": [],
                        "evidence_refs": [],
                        "interview_risk_notes": [],
                    })
                elif isinstance(value, dict):
                    role_text = _guidance_text(value.get("role_in_story") or value.get("role") or value.get("guidance") or value.get("why"), value.get("experience_id") or exp_id)
                    guidance.append({
                        "experience_id": str(value.get("experience_id") or exp_id),
                        "role_in_story": role_text[:600],
                        "what_to_highlight": OpenAIMissionProvider._string_list(value.get("what_to_highlight")),
                        "what_to_avoid": OpenAIMissionProvider._string_list(value.get("what_to_avoid"), default=["Do not invent metrics, tools, or outcomes not present in profile evidence"]),
                        "target_capabilities": OpenAIMissionProvider._string_list(value.get("target_capabilities") or value.get("related_capabilities")),
                        "evidence_refs": OpenAIMissionProvider._uuid_strings(value.get("evidence_refs") or value.get("supporting_evidence_refs") or []),
                        "interview_risk_notes": OpenAIMissionProvider._string_list(value.get("interview_risk_notes")),
                    })
        elif isinstance(guidance_raw, list):
            for item in guidance_raw:
                if not isinstance(item, dict):
                    continue
                exp_id = item.get("experience_id") or item.get("experience_ref") or item.get("id")
                if not exp_id:
                    continue
                role_text = _guidance_text(item.get("role_in_story") or item.get("role") or item.get("guidance") or item.get("why"), exp_id)
                guidance.append({
                    "experience_id": str(exp_id),
                    "role_in_story": role_text[:600],
                    "what_to_highlight": OpenAIMissionProvider._string_list(item.get("what_to_highlight")),
                    "what_to_avoid": OpenAIMissionProvider._string_list(item.get("what_to_avoid"), default=["Do not invent metrics, tools, or outcomes not present in profile evidence"]),
                    "target_capabilities": OpenAIMissionProvider._string_list(item.get("target_capabilities") or item.get("related_capabilities")),
                    "evidence_refs": OpenAIMissionProvider._uuid_strings(item.get("evidence_refs") or item.get("supporting_evidence_refs") or []),
                    "interview_risk_notes": OpenAIMissionProvider._string_list(item.get("interview_risk_notes")),
                })

        deduped_guidance: list[dict] = []
        seen_guidance: set[str] = set()
        for item in guidance:
            key = str(item.get("experience_id") or "").strip()
            if not key or key in seen_guidance:
                continue
            seen_guidance.add(key)
            deduped_guidance.append(item)
        guidance = deduped_guidance
        if not order_ids and guidance:
            order_ids = [str(item["experience_id"]) for item in guidance]

        return {
            "positioning_statement": OpenAIMissionProvider._strip_evidence_dump(positioning)[:600],
            "recommended_experience_order": order_ids[:20],
            "experience_guidance": guidance[:20],
        }

    @staticmethod
    def _normalize_grounding(value: object) -> str:
        raw = str(value or "SUPPORTED").strip().upper().replace(" ", "_")
        if raw in {"SUPPORTED", "NEEDS_CONFIRMATION", "UNSUPPORTED"}:
            return raw
        low = raw.casefold()
        if "confirm" in low:
            return "NEEDS_CONFIRMATION"
        if "unsupport" in low or "invent" in low:
            return "UNSUPPORTED"
        return "SUPPORTED"

    @staticmethod
    def _normalize_target_resume_generation(data: dict) -> dict:
        experiences_in = data.get("experiences") if isinstance(data.get("experiences"), list) else []
        experiences: list[dict] = []
        for item in experiences_in[:20]:
            if not isinstance(item, dict):
                continue
            source_id = item.get("source_experience_id") or item.get("experience_id")
            bullets_raw = item.get("bullets") if isinstance(item.get("bullets"), list) else []
            bullets: list[dict] = []
            seen_bullets: set[tuple[str, str]] = set()
            for bullet in bullets_raw[:20]:
                if not isinstance(bullet, dict):
                    continue
                original = str(bullet.get("original_text") or bullet.get("original") or "").strip()
                suggested = str(bullet.get("suggested_text") or bullet.get("suggested") or original).strip()
                why = OpenAIMissionProvider._strip_evidence_dump(
                    str(bullet.get("why_changed") or bullet.get("reason") or "Aligned to JD with confirmed evidence.")
                )[:1000]
                if not original or not suggested:
                    continue
                bullet_key = (" ".join(original.casefold().split()), " ".join(suggested.casefold().split()))
                if bullet_key in seen_bullets:
                    continue
                seen_bullets.add(bullet_key)
                bullets.append({
                    "original_text": original[:2000],
                    "suggested_text": suggested[:2000],
                    "why_changed": why or "Aligned to JD with confirmed evidence.",
                    "target_capabilities": OpenAIMissionProvider._string_list(bullet.get("target_capabilities")),
                    "jd_evidence_refs": OpenAIMissionProvider._string_list(
                        bullet.get("jd_evidence_refs") or bullet.get("jd_refs")
                    ),
                    "evidence_refs": OpenAIMissionProvider._uuid_strings(
                        bullet.get("evidence_refs") or ([source_id] if source_id else [])
                    ),
                    "resume_skill_refs": OpenAIMissionProvider._string_list(
                        bullet.get("resume_skill_refs") or bullet.get("skill_refs")
                    ),
                    "grounding_status": OpenAIMissionProvider._normalize_grounding(bullet.get("grounding_status")),
                    "risk_flags": OpenAIMissionProvider._string_list(bullet.get("risk_flags")),
                })
            display = str(item.get("display_name") or item.get("title") or item.get("name") or "Experience").strip()[:255]
            experiences.append({
                "source_experience_id": str(source_id) if source_id else None,
                "display_name": display or "Experience",
                "role_in_resume": OpenAIMissionProvider._strip_evidence_dump(
                    str(item.get("role_in_resume") or item.get("role_in_story") or "")
                )[:600],
                "include": bool(item.get("include", True)),
                "bullets": bullets,
            })
        positioning = data.get("positioning_summary") or data.get("positioning_statement") or ""
        positioning = OpenAIMissionProvider._strip_evidence_dump(str(positioning))[:600]
        section_order = OpenAIMissionProvider._string_list(
            data.get("section_order") or ["basic", "positioning", "education", "experience", "skills"]
        )
        return {
            "positioning_summary": positioning,
            "section_order": section_order[:20],
            "experiences": experiences,
            "skills": OpenAIMissionProvider._string_list(data.get("skills"), max_items=40),
            "excluded_suggestions": OpenAIMissionProvider._string_list(data.get("excluded_suggestions"), max_items=40),
        }

    @staticmethod
    def _generation_to_target_payload(result: "TargetResumeGenerationResult", *, strategy: ResumeStrategyPayload) -> TargetResumePayload:
        bullets: list[dict] = []
        order: list[str] = []
        synthetic_blocks = 0
        for block in result.experiences:
            if not block.include:
                continue
            exp_id = str(block.source_experience_id) if block.source_experience_id else None
            if exp_id is None:
                synthetic_blocks += 1
                if synthetic_blocks > 2:
                    continue
            if exp_id and exp_id not in order:
                order.append(exp_id)
            for bullet in block.bullets:
                status = bullet.grounding_status.value if hasattr(bullet.grounding_status, "value") else str(bullet.grounding_status)
                risk_flags = list(bullet.risk_flags)[:20]
                if exp_id is None and "SYNTHETIC_PROJECT" not in risk_flags:
                    risk_flags = ["SYNTHETIC_PROJECT", *risk_flags][:20]
                bullets.append({
                    "source_experience_id": exp_id,
                    "original_text": bullet.original_text[:2000],
                    "suggested_text": bullet.suggested_text[:2000],
                    "final_text": None,
                    "reason": bullet.why_changed[:1000],
                    "jd_refs": list(bullet.jd_evidence_refs)[:30],
                    "evidence_refs": [str(v) for v in bullet.evidence_refs][:30],
                    "resume_skill_refs": list(bullet.resume_skill_refs)[:20],
                    "risk_flags": risk_flags,
                    "target_capabilities": list(bullet.target_capabilities)[:20],
                    "grounding_status": status,
                })
        if not order:
            order = [str(v) for v in strategy.recommended_experience_order]
        positioning = (result.positioning_summary or strategy.positioning_statement or "Evidence-grounded target resume").strip()
        return TargetResumePayload.model_validate({
            "positioning_statement": positioning[:600] or "Evidence-grounded target resume",
            "recommended_experience_order": order[:20],
            "bullets": bullets[:80],
            "section_order": list(result.section_order)[:20],
            "skills": list(result.skills)[:40],
            "excluded_suggestions": list(result.excluded_suggestions)[:40],
        })


    def _normalize_target_resume(data: dict) -> dict:
        positioning = data.get("positioning_statement") or data.get("positioning") or data.get("candidate_story")
        if not isinstance(positioning, str) or positioning.strip().upper() in {"", "UNKNOWN", "N/A", "NONE", "NULL"}:
            positioning = OpenAIMissionProvider._strip_evidence_dump(str(positioning)) if isinstance(positioning, str) else "Target this role with confirmed experiences only; do not invent unproven outcomes."
        if not isinstance(positioning, str) or positioning.strip().upper() in {"", "UNKNOWN", "N/A", "NONE", "NULL"}:
            positioning = "Target this role with confirmed experiences only; do not invent unproven outcomes."
        order = OpenAIMissionProvider._uuid_strings(data.get("recommended_experience_order") or data.get("experience_order") or [])
        bullets_raw = data.get("bullets") or data.get("resume_bullets") or data.get("suggestions") or data.get("items") or []
        if isinstance(bullets_raw, dict):
            bullets_raw = list(bullets_raw.values())
        bullets: list[dict] = []
        if isinstance(bullets_raw, list):
            for item in bullets_raw:
                if not isinstance(item, dict):
                    continue
                original = str(item.get("original_text") or item.get("original") or item.get("source_text") or "").strip()
                suggested = str(item.get("suggested_text") or item.get("suggested") or item.get("revised_text") or item.get("text") or "").strip()
                if not suggested and not original:
                    continue
                if not original:
                    original = suggested
                if not suggested:
                    suggested = original
                reason = str(item.get("reason") or item.get("why") or "Aligned to the target role using confirmed experience evidence.").strip()
                source_id = item.get("source_experience_id") or item.get("experience_id") or item.get("source_id")
                bullets.append({
                    "source_experience_id": str(source_id) if source_id else None,
                    "original_text": original[:2000],
                    "suggested_text": suggested[:2000],
                    "final_text": (str(item["final_text"]).strip()[:2000] if item.get("final_text") else None),
                    "reason": reason[:1000] or "Aligned to the target role using confirmed experience evidence.",
                    "jd_refs": [str(x) for x in (item.get("jd_refs") or item.get("requirement_refs") or [])][:30],
                    "evidence_refs": OpenAIMissionProvider._uuid_strings(item.get("evidence_refs") or item.get("supporting_evidence_refs") or ([source_id] if source_id else [])),
                    "resume_skill_refs": OpenAIMissionProvider._string_list(item.get("resume_skill_refs") or item.get("skill_refs")),
                    "risk_flags": OpenAIMissionProvider._string_list(item.get("risk_flags")),
                })
        # Derive bullets from experience_guidance when model forgot bullets
        if not bullets:
            guidance = data.get("experience_guidance") or []
            if isinstance(guidance, list):
                for item in guidance:
                    if not isinstance(item, dict):
                        continue
                    exp_id = item.get("experience_id")
                    role = str(item.get("role_in_story") or "").strip()
                    highlights = OpenAIMissionProvider._string_list(item.get("what_to_highlight"))
                    suggested = (highlights[0] if highlights else role) or "Keep this confirmed experience concise and role-relevant."
                    if not exp_id or not suggested:
                        continue
                    bullets.append({
                        "source_experience_id": str(exp_id),
                        "original_text": suggested[:2000],
                        "suggested_text": suggested[:2000],
                        "final_text": None,
                        "reason": (role or "Grounded from resume strategy guidance.")[:1000],
                        "jd_refs": [],
                        "evidence_refs": OpenAIMissionProvider._uuid_strings(item.get("evidence_refs") or [exp_id]),
                        "resume_skill_refs": [],
                        "risk_flags": OpenAIMissionProvider._string_list(item.get("interview_risk_notes"))[:5],
                    })
                    if exp_id and str(exp_id) not in order:
                        order.append(str(exp_id))
        return {
            "positioning_statement": OpenAIMissionProvider._strip_evidence_dump(positioning)[:600],
            "recommended_experience_order": order[:20],
            "bullets": bullets[:80],
        }




    @staticmethod
    def _align_experience_why(decision: str, why: str, label: str = "这段经历") -> str:
        """Keep decision and Chinese why copy consistent (OMIT must not say 建议保留)."""
        cleaned = (why or "").strip()
        decision = (decision or "KEEP_AND_HIGHLIGHT").strip().upper()
        label = (label or "这段经历").strip() or "这段经历"
        keep_tone = bool(re.search(r"建议保留|建议突出|重点展示|写进核心|保留并突出", cleaned))
        omit_tone = bool(re.search(r"暂不放入|不放入|不展示|建议排除|关联较弱", cleaned))
        if decision == "OMIT":
            if not cleaned or keep_tone:
                return f"与当前岗位关联较弱，这份岗位简历暂不放入「{label}」（不会删除原简历）。"
            return cleaned
        if decision == "DEEMPHASIZE":
            if not cleaned or omit_tone or (keep_tone and re.search(r"重点展示|保留并突出", cleaned)):
                return f"与岗位有一定关联，但「{label}」在这份简历里弱化处理即可。"
            return cleaned
        if omit_tone or not cleaned:
            if decision == "KEEP_AND_HIGHLIGHT":
                return f"与目标岗位相关，建议重点展示「{label}」中可验证的成果与职责。"
            return f"与目标岗位相关，建议保留「{label}」。"
        return cleaned

    @staticmethod
    def _strip_evidence_dump(text: str) -> str:
        """Remove Evidence dumps / dogfood-req / UUIDs from user-visible narrative fields."""
        import re as _re

        if not text:
            return text
        cleaned = str(text)
        cleaned = _re.sub(
            r"(?:\n|\r|\s)*Evidence\s*:\s*.*$",
            "",
            cleaned,
            flags=_re.IGNORECASE | _re.DOTALL,
        )
        cleaned = _re.sub(
            r"(?:\n|\r|\s)*(?:证据|依据)\s*[：:]\s*.*$",
            "",
            cleaned,
            flags=_re.IGNORECASE | _re.DOTALL,
        )
        # Parenthetical evidence / UUID refs: (5ab91894-...) or （uuid）
        cleaned = _re.sub(
            r"[（(]\s*(?:dogfood-req-[\w-]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\s*[）)]",
            "",
            cleaned,
        )
        # Bare UUID / dogfood tokens anywhere in narrative
        cleaned = _re.sub(
            r"\b(?:dogfood-req-[\w-]+|[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12})\b",
            "",
            cleaned,
        )
        cleaned = _re.sub(r"[ \t]{2,}", " ", cleaned)
        cleaned = _re.sub(r" ?([，。；、,.])", r"\1", cleaned)
        return cleaned.strip(" ,;，；、")

    @staticmethod
    def _normalize_red_team(data: dict) -> dict:
        findings_raw = data.get("findings") or data.get("issues") or data.get("risks") or data.get("items") or []
        if isinstance(findings_raw, dict):
            findings_raw = list(findings_raw.values())
        findings: list[dict] = []
        if isinstance(findings_raw, list):
            for item in findings_raw:
                if isinstance(item, str) and item.strip():
                    claim = OpenAIMissionProvider._strip_evidence_dump(item.strip())[:1000]
                    findings.append({
                        "claim": claim or "Resume claim needs interview defense",
                        "jd_relevance": "Linked to a target-resume claim that interviewers are likely to probe.",
                        "evidence_strength": "Needs stronger concrete evidence before interview.",
                        "company_interview_trigger": "Interviewers often challenge scope, ownership, and measurable impact.",
                        "attack_dimensions": ["evidence", "ownership"],
                        "likely_followups": ["Can you walk through a concrete example?", "What was your personal contribution?"],
                        "risk_level": "MEDIUM",
                        "why": "Claim may invite follow-up without enough grounded detail.",
                        "recommended_next_step": "Add a specific example with your role, action, and outcome.",
                        "evidence_refs": [],
                    })
                    continue
                if not isinstance(item, dict):
                    continue
                claim = str(item.get("claim") or item.get("statement") or item.get("text") or item.get("bullet") or "").strip()
                claim = OpenAIMissionProvider._strip_evidence_dump(claim)[:1000]
                if not claim:
                    continue
                why = OpenAIMissionProvider._strip_evidence_dump(str(item.get("why") or item.get("reason") or "Interviewers may press on this claim.").strip())[:1000]
                risk = str(item.get("risk_level") or item.get("severity") or item.get("level") or "MEDIUM").strip().upper()
                if risk not in {"LOW", "MEDIUM", "HIGH", "CRITICAL"}:
                    risk = "MEDIUM"
                followups = OpenAIMissionProvider._string_list(
                    item.get("likely_followups") or item.get("followups") or item.get("likely_questions"),
                    default=["Can you give a concrete example?", "What was your exact role?"],
                )
                next_step = str(item.get("recommended_next_step") or item.get("next_step") or item.get("recommendation") or "Strengthen this claim with concrete evidence before interviews.").strip()[:1000]
                findings.append({
                    "claim": claim,
                    "jd_relevance": str(item.get("jd_relevance") or item.get("jd_fit") or "Relevant to the target role requirements.")[:1000],
                    "evidence_strength": str(item.get("evidence_strength") or item.get("evidence") or "Evidence may be thin or hard to defend live.")[:1000],
                    "company_interview_trigger": str(item.get("company_interview_trigger") or item.get("trigger") or "Likely probed during behavioral / deep-dive rounds.")[:1000],
                    "attack_dimensions": OpenAIMissionProvider._string_list(item.get("attack_dimensions") or item.get("dimensions"), default=["evidence"])[:5],
                    "likely_followups": followups[:20],
                    "risk_level": risk[:24],
                    "why": why or "Interviewers may press on this claim.",
                    "recommended_next_step": next_step or "Add a concrete example with ownership and outcome.",
                    "evidence_refs": OpenAIMissionProvider._uuid_strings(item.get("evidence_refs") or item.get("supporting_evidence_refs") or []),
                    "claim_id": item.get("claim_id"),
                })
        return {"findings": findings[:80]}

    @staticmethod
    def _red_team_fallback(target_resume: TargetResumePayload) -> RedTeamPayload:
        findings = []
        for bullet in target_resume.bullets[:12]:
            text = (bullet.final_text or bullet.suggested_text or bullet.original_text or "").strip()
            if not text:
                continue
            flags = [str(flag).upper() for flag in (bullet.risk_flags or [])]
            risk = "HIGH" if any(token in " ".join(flags) for token in ("HIGH", "CRITICAL", "UNVERIFIED", "INFLATED", "WEAK")) else "MEDIUM"
            findings.append({
                "claim": OpenAIMissionProvider._strip_evidence_dump(text)[:1000],
                "jd_relevance": "This target-resume bullet is likely to be tested against the JD in interview.",
                "evidence_strength": "Heuristic fallback: treat as needing stronger interview-ready evidence.",
                "company_interview_trigger": "Interviewers often ask for ownership, constraints, and measurable results.",
                "attack_dimensions": ["evidence", "ownership", "impact"][:5],
                "likely_followups": [
                    "Can you walk me through a concrete example behind this bullet?",
                    "其中你个人贡献和团队贡献分别是什么？",
                    "How do you know the outcome was caused by your work?",
                ],
                "risk_level": risk,
                "why": "Without a concrete story, interviewers can challenge scope, ownership, or impact on this bullet.",
                "recommended_next_step": "Prepare a short STAR example and keep only claims you can defend with real evidence.",
                "evidence_refs": OpenAIMissionProvider._uuid_strings(list(bullet.evidence_refs or [])),
            })
        if not findings:
            findings.append({
                "claim": OpenAIMissionProvider._strip_evidence_dump(target_resume.positioning_statement or "（未填写定位）")[:1000],
                "jd_relevance": "Positioning statement will frame the interview narrative.",
                "evidence_strength": "Needs supporting bullets with concrete evidence.",
                "company_interview_trigger": "Opening narrative is often challenged for proof.",
                "attack_dimensions": ["evidence"],
                "likely_followups": ["What is the strongest proof point behind this positioning?"],
                "risk_level": "MEDIUM",
                "why": "Positioning without defensibility creates interview risk.",
                "recommended_next_step": "Attach at least one concrete proof story to the positioning.",
                "evidence_refs": [],
            })
        return RedTeamPayload.model_validate({"findings": findings})


    @staticmethod
    def _normalize_jd_requirement(item: object, *, idx: int, default_category: str = "must_have") -> dict | None:
        if isinstance(item, str):
            text = item.strip()
            if not text:
                return None
            return {
                "id": f"req-{idx+1}",
                "text": text[:1000],
                "category": default_category[:64],
                "evidence_text": text[:1000],
            }
        if not isinstance(item, dict):
            return None
        text = str(
            item.get("text")
            or item.get("requirement")
            or item.get("content")
            or item.get("name")
            or ""
        ).strip()
        if not text:
            return None
        evidence = str(
            item.get("evidence_text")
            or item.get("evidence")
            or item.get("source")
            or item.get("quote")
            or text
        ).strip()[:1000]
        category = str(item.get("category") or item.get("type") or default_category).strip() or default_category
        req_id = str(item.get("id") or item.get("requirement_id") or item.get("ref") or f"req-{idx+1}").strip()
        if not req_id:
            req_id = f"req-{idx+1}"
        return {
            "id": req_id[:96],
            "text": text[:1000],
            "category": category[:64],
            "evidence_text": evidence or text[:1000],
        }

    @staticmethod
    def _normalize_job_extraction(data: dict) -> dict:
        def _s(value: object, default: str = "UNKNOWN") -> str:
            if value is None:
                return default
            text = str(value).strip()
            return text if text else default

        from .jd_identity_normalize import normalize_location, normalize_seniority

        company = _s(data.get("company") or data.get("employer") or data.get("org"), "UNKNOWN")
        role = _s(data.get("role") or data.get("title") or data.get("position"), "UNKNOWN")
        role_family = _s(data.get("role_family") or data.get("family") or data.get("track"), "UNKNOWN")
        seniority = normalize_seniority(data.get("seniority") or data.get("level") or data.get("grade"))
        location_raw = data.get("location")
        location = None
        if isinstance(location_raw, str) and location_raw.strip():
            location = location_raw.strip()[:255]
        elif location_raw is not None and not isinstance(location_raw, (dict, list)):
            text = str(location_raw).strip()
            location = text[:255] if text else None
        location = normalize_location(location)

        requirements_raw = data.get("requirements") or data.get("must_have") or data.get("required") or []
        preferred_raw = data.get("preferred_requirements") or data.get("preferred") or data.get("nice_to_have") or []
        if isinstance(requirements_raw, dict):
            requirements_raw = list(requirements_raw.values())
        if isinstance(preferred_raw, dict):
            preferred_raw = list(preferred_raw.values())
        requirements: list[dict] = []
        if isinstance(requirements_raw, list):
            for idx, item in enumerate(requirements_raw[:80]):
                row = OpenAIMissionProvider._normalize_jd_requirement(item, idx=idx, default_category="must_have")
                if row:
                    requirements.append(row)
        preferred: list[dict] = []
        if isinstance(preferred_raw, list):
            for idx, item in enumerate(preferred_raw[:50]):
                row = OpenAIMissionProvider._normalize_jd_requirement(item, idx=idx, default_category="preferred")
                if row:
                    preferred.append(row)

        return {
            "company": company[:255],
            "role": role[:255],
            "role_family": role_family[:64],
            "seniority": seniority[:64],
            "location": location,
            "responsibilities": OpenAIMissionProvider._string_list(data.get("responsibilities") or data.get("duties"), max_items=60),
            "requirements": requirements,
            "preferred_requirements": preferred,
            "capabilities": OpenAIMissionProvider._string_list(
                OpenAIMissionProvider._maybe_split_csv(data.get("capabilities") or data.get("skills")),
                max_items=60,
            ),
            "keywords": OpenAIMissionProvider._string_list(
                OpenAIMissionProvider._maybe_split_csv(data.get("keywords") or data.get("tags")),
                max_items=100,
            ),
        }

    @staticmethod
    def _normalize_what_matters(data: dict) -> dict:
        caps_raw = (
            data.get("core_capabilities")
            or data.get("core_competencies")
            or data.get("key_capabilities")
            or data.get("capabilities")
            or data.get("core")
            or []
        )
        if isinstance(caps_raw, dict):
            caps_raw = list(caps_raw.values())
        core: list[dict] = []
        if isinstance(caps_raw, list):
            for item in caps_raw[:30]:
                if isinstance(item, str) and item.strip():
                    core.append({"name": item.strip()[:255], "why": "Grounded from JD analysis.", "evidence_refs": []})
                    continue
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name") or item.get("capability") or item.get("text") or "").strip()
                if not name:
                    continue
                why = str(item.get("why") or item.get("reason") or "Grounded from JD analysis.").strip() or "Grounded from JD analysis."
                refs = item.get("evidence_refs") or item.get("jd_refs") or []
                if isinstance(refs, str):
                    refs = [refs]
                core.append({
                    "name": name[:255],
                    "why": why[:1000],
                    "evidence_refs": [str(x) for x in (refs or []) if str(x).strip()][:20],
                })

        high_raw = data.get("high_importance_requirements") or data.get("key_requirements") or data.get("must_have_insights") or []
        if isinstance(high_raw, dict):
            high_raw = list(high_raw.values())
        high: list[dict] = []
        if isinstance(high_raw, list):
            for item in high_raw[:50]:
                if isinstance(item, str) and item.strip():
                    high.append({"text": item.strip()[:1000], "importance": "HIGH", "evidence_refs": []})
                    continue
                if not isinstance(item, dict):
                    continue
                text = str(item.get("text") or item.get("requirement") or item.get("name") or "").strip()
                if not text:
                    continue
                importance = str(item.get("importance") or item.get("priority") or "HIGH").strip().upper() or "HIGH"
                refs = item.get("evidence_refs") or item.get("jd_refs") or []
                if isinstance(refs, str):
                    refs = [refs]
                high.append({
                    "text": text[:1000],
                    "importance": importance,
                    "evidence_refs": [str(x) for x in (refs or []) if str(x).strip()][:20],
                })

        jd_refs = data.get("jd_evidence_refs") or data.get("evidence_refs") or []
        if isinstance(jd_refs, str):
            jd_refs = [jd_refs]
        if not isinstance(jd_refs, list):
            jd_refs = []
        jd_evidence_refs = [str(x) for x in jd_refs if str(x).strip()][:80]
        # Keep grounding validator happy: every nested evidence_ref must be listed.
        for item in [*core, *high]:
            for ref in item.get("evidence_refs") or []:
                if ref not in jd_evidence_refs:
                    jd_evidence_refs.append(ref)
        jd_evidence_refs = jd_evidence_refs[:80]

        conf = data.get("confidence")
        try:
            confidence = float(conf) if conf is not None else 0.55
        except (TypeError, ValueError):
            confidence = 0.55
        confidence = max(0.0, min(1.0, confidence))

        return {
            "core_capabilities": core,
            "high_importance_requirements": high,
            "evidence_expected": OpenAIMissionProvider._string_list(data.get("evidence_expected"), max_items=30),
            "likely_success_signals": OpenAIMissionProvider._string_list(data.get("likely_success_signals") or data.get("success_signals"), max_items=30),
            "bonus_capabilities": OpenAIMissionProvider._string_list(data.get("bonus_capabilities") or data.get("bonus"), max_items=30),
            "potential_interview_focus": OpenAIMissionProvider._string_list(
                data.get("potential_interview_focus")
                or data.get("interview_focus_areas")
                or data.get("interview_focus")
                or data.get("focus_areas"),
                max_items=30,
            ),
            "confidence": confidence,
            "jd_evidence_refs": jd_evidence_refs,
        }


    def _normalize_for_model(data: dict, model_type: type) -> dict:
        name = getattr(model_type, "__name__", "")
        data = OpenAIMissionProvider._unwrap_payload(data, model_type)
        if name == "ExperienceSelectionPayload":
            selections: list[dict] = []
            seen: set[str] = set()
            raw_list = data.get("selections") if isinstance(data.get("selections"), list) else None
            if raw_list is not None:
                for item in raw_list:
                    if not isinstance(item, dict):
                        continue
                    exp_id = item.get("experience_id") or item.get("experience_ref") or item.get("id")
                    if not exp_id or str(exp_id) in seen:
                        continue
                    seen.add(str(exp_id))
                    decision = str(item.get("decision") or "KEEP_AND_HIGHLIGHT")
                    if decision not in {"KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"}:
                        decision = "KEEP_AND_HIGHLIGHT"
                    why = OpenAIMissionProvider._strip_evidence_dump(
                        str(item.get("why") or item.get("reason") or "")
                    )[:1000]
                    why = OpenAIMissionProvider._align_experience_why(decision, why)[:1000]
                    refs = OpenAIMissionProvider._uuid_strings(
                        item.get("supporting_evidence_refs") or item.get("evidence_refs") or []
                    )
                    try:
                        confidence = float(item.get("confidence") or data.get("confidence") or 0.7)
                    except (TypeError, ValueError):
                        confidence = 0.7
                    selections.append({
                        "experience_id": str(exp_id),
                        "decision": decision,
                        "why": why,
                        "related_capabilities": list(item.get("related_capabilities") or item.get("capabilities") or [])[:20],
                        "supporting_evidence_refs": refs[:20],
                        "confidence": max(0.0, min(1.0, confidence)),
                    })
                return {"selections": selections}
            for item in data.get("selected_experiences") or []:
                if not isinstance(item, dict):
                    continue
                exp_id = item.get("experience_id") or item.get("experience_ref") or item.get("id")
                if not exp_id:
                    continue
                seen.add(str(exp_id))
                decision = str(item.get("decision") or "KEEP_AND_HIGHLIGHT")
                if decision not in {"KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"}:
                    decision = "KEEP_AND_HIGHLIGHT"
                selections.append({
                    "experience_id": str(exp_id),
                    "decision": decision,
                    "why": str(item.get("why") or item.get("reason") or "Selected for target role coverage"),
                    "related_capabilities": list(item.get("related_capabilities") or item.get("capabilities") or []),
                    "supporting_evidence_refs": list(item.get("supporting_evidence_refs") or item.get("evidence_refs") or []),
                    "confidence": float(item.get("confidence") or data.get("confidence") or 0.7),
                })
            for item in data.get("excluded_experiences") or []:
                if isinstance(item, str):
                    exp_id, why, decision = item, "Excluded for this mission", "OMIT"
                elif isinstance(item, dict):
                    exp_id = item.get("experience_id") or item.get("experience_ref") or item.get("id")
                    why = str(item.get("why") or item.get("reason") or "Excluded for this mission")
                    decision = str(item.get("decision") or "OMIT")
                else:
                    continue
                if not exp_id or str(exp_id) in seen:
                    continue
                seen.add(str(exp_id))
                if decision not in {"KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"}:
                    decision = "OMIT"
                selections.append({
                    "experience_id": str(exp_id),
                    "decision": decision,
                    "why": why,
                    "related_capabilities": [],
                    "supporting_evidence_refs": [],
                    "confidence": float(data.get("confidence") or 0.6),
                })
            return {"selections": selections}
        if name == "ResumeStrategyPayload":
            return OpenAIMissionProvider._normalize_resume_strategy(data)
        if name == "TargetResumeGenerationResult":
            return OpenAIMissionProvider._normalize_target_resume_generation(data)
        if name == "TargetResumePayload":
            return OpenAIMissionProvider._normalize_target_resume(data)
        if name == "RedTeamPayload":
            return OpenAIMissionProvider._normalize_red_team(data)
        if name == "JobExtractionPayload":
            return OpenAIMissionProvider._normalize_job_extraction(data)
        if name == "WhatMattersPayload":
            return OpenAIMissionProvider._normalize_what_matters(data)
        fields = getattr(model_type, "model_fields", None)
        if isinstance(fields, dict) and fields:
            return {key: data[key] for key in fields if key in data}
        return data

    @staticmethod
    def _parse(response: object, model_type: type[_MODEL_T]) -> _MODEL_T:
        try:
            content = response.choices[0].message.content  # type: ignore[attr-defined]
        except Exception as exc:
            raise MissionProviderInvalidResponseError(reason="response_shape") from exc
        if not isinstance(content, str) or not content.strip():
            raise MissionProviderInvalidResponseError(reason="empty_response")
        try:
            data = json.loads(content)
        except json.JSONDecodeError as exc:
            raise MissionProviderInvalidResponseError(reason="json_decode") from exc
        if not isinstance(data, dict):
            raise MissionProviderInvalidResponseError(reason="response_shape")
        # DeepSeek / some gateways occasionally echo response_format instead of content.
        if set(data.keys()) <= {"type", "json_object"} or data == {"type": "json_object"}:
            raise MissionProviderInvalidResponseError(reason="empty_response")
        try:
            normalized = OpenAIMissionProvider._normalize_for_model(data, model_type)
            return model_type.model_validate(normalized)
        except (ValidationError, TypeError, ValueError) as exc:
            safe_errors = [{"loc": list(error.get("loc", ())), "type": str(error.get("type", "validation_error"))} for error in getattr(exc, "errors", lambda: [])()]
            raise MissionProviderInvalidResponseError(reason="schema_validation", validation_errors=safe_errors) from exc

    def _call(self, operation: str, payload: dict[str, object], model_type: type[_MODEL_T]) -> _MODEL_T:
        return self._parse(self._request(operation=operation, payload=payload), model_type)

    @staticmethod
    def _resume_skills() -> list[dict[str, object]]:
        try:
            from .resume_intelligence import resume_skill_records

            return resume_skill_records()
        except Exception:
            return []

    @staticmethod
    def _interview_intel_for(extraction: JobExtractionPayload) -> list[dict[str, object]]:
        try:
            from .interview_intelligence import InterviewIntelRetriever
            from .mission_intelligence import intel_records

            items = InterviewIntelRetriever().retrieve(
                company=extraction.company,
                role=extraction.role,
                role_family=extraction.role_family,
                competencies=[*extraction.capabilities, *extraction.keywords],
            )
            return intel_records(items)
        except Exception:
            return []

    @staticmethod
    def _bounded_interview_intel_for(extraction: JobExtractionPayload) -> list[dict[str, object]]:
        from .mission_intelligence import bounded_intel_records

        return bounded_intel_records(OpenAIMissionProvider._interview_intel_for(extraction))

    @staticmethod
    def _enrich_job_extraction(raw_text: str, extraction: JobExtractionPayload) -> JobExtractionPayload:
        """Fill company/role/seniority/location from JD text when the model left them UNKNOWN."""
        updates: dict[str, object] = {}
        company = (extraction.company or "").strip()
        if not company or company.upper() == "UNKNOWN":
            inferred_company = OpenAIMissionProvider._infer_company_from_jd(raw_text)
            if inferred_company:
                updates["company"] = inferred_company
        role = (extraction.role or "").strip()
        if not role or role.upper() == "UNKNOWN":
            inferred = OpenAIMissionProvider._infer_role_from_jd(raw_text)
            if inferred:
                updates["role"] = inferred
        location = extraction.location
        if isinstance(location, str) and location.strip().upper() in {"UNKNOWN", "N/A", "NONE", "NULL"}:
            updates["location"] = None
            location = None

        from .jd_identity_normalize import (
            infer_location_from_jd,
            infer_seniority_from_jd,
            normalize_location,
            normalize_seniority,
        )

        seniority = (extraction.seniority or "").strip()
        if not seniority or seniority.upper() == "UNKNOWN":
            inferred_seniority = infer_seniority_from_jd(raw_text)
            if inferred_seniority and inferred_seniority != "UNKNOWN":
                updates["seniority"] = normalize_seniority(inferred_seniority)
        if location is None or (isinstance(location, str) and not str(location).strip()):
            inferred_location = infer_location_from_jd(raw_text)
            if inferred_location:
                updates["location"] = normalize_location(inferred_location)

        if not updates:
            return extraction
        return extraction.model_copy(update=updates)


    @staticmethod
    def _infer_company_from_jd(raw_text: str) -> str | None:
        import re as _re

        body = (raw_text or "").strip()
        if not body:
            return None
        patterns = [
            r"(?:公司|企业|雇主|用人单位|招聘方|Company|Employer|Org(?:anization)?)\s*[：:\-]?\s*([^\n\r]{2,80})",
            r"^\s*[【\[]?\s*([^\n\r【\]】]{2,40}?)\s*[】\]]?\s*(?:招聘|诚聘)",
        ]
        for pattern in patterns:
            match = _re.search(pattern, body, flags=_re.IGNORECASE | _re.MULTILINE)
            if match:
                candidate = _re.split(r"[|｜/·•]", match.group(1).strip())[0].strip(" 　-—|·•【】[]()（）")
                if candidate and candidate.upper() not in {"UNKNOWN", "N/A", "NONE", "NULL"} and len(candidate) >= 2:
                    # Avoid capturing duty/section headers as company.
                    if any(token in candidate for token in ("职责", "资格", "要求", "岗位", "职位", "工作内容")):
                        continue
                    return candidate[:255]
        return None

    @staticmethod
    def _infer_role_from_jd(raw_text: str) -> str | None:
        import re as _re

        body = (raw_text or "").strip()
        if not body:
            return None
        patterns = [
            r"(?:岗位|职位|职衔|招聘岗位|岗位名称|Role|Title)\s*[：:\-]?\s*([^\n\r]{2,80})",
            r"(?:诚聘|招聘)\s*([^\n\r]{2,40})",
        ]
        for pattern in patterns:
            match = _re.search(pattern, body, flags=_re.IGNORECASE)
            if match:
                candidate = _re.split(r"[（(｜|/]", match.group(1).strip())[0].strip(" 　-—|·")
                if candidate and candidate.upper() not in {"UNKNOWN", "N/A"} and len(candidate) >= 2:
                    return candidate[:255]

        # Duty-only JD (no explicit title): synthesize a short role from domain cues.
        productish = any(
            token in body
            for token in (
                "产品经理",
                "Product Manager",
                "产品定义",
                "产品规划",
                "产品线",
                "产品选型",
                "roadmap",
                "Roadmap",
            )
        )
        if productish or "PM" in body:
            if any(token in body for token in ("具身智能", "物理 AI", "物理AI", "智能硬件", "智能相机")):
                if "相机" in body:
                    return "具身智能相机产品经理"
                return "具身智能硬件产品经理"
            if any(token in body for token in ("AI 眼镜", "AI眼镜", "智能眼镜")):
                return "AI眼镜产品经理"
            if "AI" in body or "大模型" in body or "LLM" in body:
                return "AI产品经理"
            if productish:
                return "产品经理"
        return None

    @staticmethod
    def _what_matters_fallback(extraction: JobExtractionPayload) -> WhatMattersPayload:
        reqs = list(extraction.requirements or [])[:8]
        caps_src = list(extraction.capabilities or [])[:8] or [item.text for item in reqs[:5]]
        req_ids = [item.id for item in reqs if getattr(item, "id", None)]
        core = []
        for idx, name in enumerate(caps_src):
            label = str(name).strip()
            if not label:
                continue
            ref = req_ids[idx] if idx < len(req_ids) else (req_ids[0] if req_ids else None)
            core.append({
                "name": label[:255],
                "why": "Derived from JD capabilities/requirements when model What Matters was empty.",
                "evidence_refs": [ref] if ref else [],
            })
        high = []
        for item in reqs[:6]:
            high.append({
                "text": item.text[:1000],
                "importance": "HIGH",
                "evidence_refs": [item.id] if item.id else [],
            })
        refs: list[str] = []
        for row in [*core, *high]:
            for ref in row.get("evidence_refs") or []:
                if ref and ref not in refs:
                    refs.append(ref)
        return WhatMattersPayload.model_validate({
            "core_capabilities": core,
            "high_importance_requirements": high,
            "evidence_expected": [],
            "likely_success_signals": [],
            "bonus_capabilities": list(extraction.keywords or [])[:8],
            "potential_interview_focus": [item.text for item in reqs[:5]],
            "confidence": 0.45 if core or high else 0.0,
            "jd_evidence_refs": refs[:80],
        })

    @staticmethod
    def _sanitize_what_matters_refs(payload: WhatMattersPayload, extraction: JobExtractionPayload) -> WhatMattersPayload:
        allowed = {
            *(item.id for item in (extraction.requirements or []) if getattr(item, "id", None)),
            *(item.id for item in (extraction.preferred_requirements or []) if getattr(item, "id", None)),
        }
        if not allowed:
            core = [item.model_copy(update={"evidence_refs": []}) for item in payload.core_capabilities]
            high = [item.model_copy(update={"evidence_refs": []}) for item in payload.high_importance_requirements]
            return payload.model_copy(update={
                "core_capabilities": core,
                "high_importance_requirements": high,
                "jd_evidence_refs": [],
            })

        def _filter_refs(refs: list[str]) -> list[str]:
            return [ref for ref in refs if ref in allowed][:20]

        core = [item.model_copy(update={"evidence_refs": _filter_refs(list(item.evidence_refs or []))}) for item in payload.core_capabilities]
        high = [item.model_copy(update={"evidence_refs": _filter_refs(list(item.evidence_refs or []))}) for item in payload.high_importance_requirements]
        jd_refs = [ref for ref in (payload.jd_evidence_refs or []) if ref in allowed]
        for item in [*core, *high]:
            for ref in item.evidence_refs:
                if ref not in jd_refs:
                    jd_refs.append(ref)
        return payload.model_copy(update={
            "core_capabilities": core,
            "high_importance_requirements": high,
            "jd_evidence_refs": jd_refs[:80],
        })

    def parse_jd(self, raw_text: str) -> JobExtractionPayload:
        extraction = self._call(
            "extract company, role, role_family, seniority, and JD requirements. Output ONLY company, role, role_family, seniority, location, responsibilities, requirements, preferred_requirements, capabilities, keywords. Each requirement must be an object with id, text, category, evidence_text (evidence_text must be a verbatim substring of the JD). Always infer a concrete role/title from responsibilities when the JD has no explicit title — do NOT set role to UNKNOWN if duties describe the job. Only company, role_family, seniority, or location may be UNKNOWN when truly absent.",
            {"raw_text": raw_text},
            JobExtractionPayload,
        )
        return OpenAIMissionProvider._enrich_job_extraction(raw_text, extraction)

    def build_what_matters(self, *, raw_text: str, extraction: JobExtractionPayload, interview_intel: list[dict[str, object]]) -> WhatMattersPayload:
        from .mission_intelligence import bounded_intel_records

        try:
            payload = self._call(
                "ground What Matters for this JD. Output ONLY core_capabilities, high_importance_requirements, evidence_expected, likely_success_signals, bonus_capabilities, potential_interview_focus, confidence, jd_evidence_refs. core_capabilities items must be objects with name, why, evidence_refs. high_importance_requirements items must be objects with text, importance, evidence_refs. jd_evidence_refs must only copy requirement ids from extraction.requirements / preferred_requirements. Never return meta keys like type/json_object.",
                {"raw_text": raw_text, "extraction": extraction.model_dump(mode="json"), "interview_intel": bounded_intel_records(interview_intel)},
                WhatMattersPayload,
            )
        except MissionProviderInvalidResponseError:
            payload = OpenAIMissionProvider._what_matters_fallback(extraction)
        else:
            if not payload.core_capabilities and not payload.high_importance_requirements:
                payload = OpenAIMissionProvider._what_matters_fallback(extraction)
        return OpenAIMissionProvider._sanitize_what_matters_refs(payload, extraction)

    def select_experiences(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload) -> ExperienceSelectionPayload:
        def _experience_facts() -> list[dict[str, object]]:
            out: list[dict[str, object]] = []
            for fact in profile_facts or []:
                if not isinstance(fact, dict):
                    continue
                kind = str(fact.get("kind") or "").lower()
                if kind and kind not in {"experience", "work", "project"}:
                    continue
                title = str(fact.get("title") or "")
                if any(term in title for term in ("主修课程", "相关课程", "核心课程", "课程学习")):
                    continue
                if not (fact.get("id") or fact.get("experience_id")):
                    continue
                # Skip obvious non-experience kinds even if kind missing
                if kind in {"education", "skill", "certification"}:
                    continue
                if not kind and not (fact.get("title") or fact.get("organization") or fact.get("description")):
                    continue
                out.append(fact)
            if out:
                return out
            # Fallback: any fact with title/organization that is not edu/skill/cert
            for fact in profile_facts or []:
                if not isinstance(fact, dict):
                    continue
                kind = str(fact.get("kind") or "").lower()
                if kind in {"education", "skill", "certification"}:
                    continue
                if fact.get("id") and (fact.get("title") or fact.get("organization")):
                    out.append(fact)
            return out

        def _heuristic() -> ExperienceSelectionPayload:
            selections = []
            seen: set[str] = set()
            for fact in _experience_facts():
                exp_id = str(fact.get("id") or fact.get("experience_id"))
                if not exp_id or exp_id in seen:
                    continue
                seen.add(exp_id)
                decision, why, highlights, confidence = OpenAIMissionProvider._heuristic_experience_decision(
                    fact, extraction=extraction, what_matters=what_matters
                )
                selections.append({
                    "experience_id": exp_id,
                    "decision": decision,
                    "why": why,
                    "related_capabilities": highlights[:5],
                    "supporting_evidence_refs": [],
                    "confidence": confidence,
                })
            return ExperienceSelectionPayload.model_validate({"selections": selections})

        try:
            payload = self._call(
                "select and explain relevant experiences. For every experience, choose exactly one of KEEP_AND_HIGHLIGHT, KEEP, DEEMPHASIZE, or OMIT. Judge relevance to the target role rather than assuming every resume row belongs. Unrelated class duties, student welfare, routine administration, and generic campus service should usually be OMIT or DEEMPHASIZE unless the facts show a direct product/technical result. why and related_capabilities must cite concrete source facts and the target capability in Chinese; never use a repeated template such as 与岗位相关，建议保留并突出. Never invent metrics, tools, ownership, or outcomes, and never include UUIDs or evidence ids in prose.",
                {
                    "profile_facts": profile_facts,
                    "extraction": extraction.model_dump(mode="json"),
                    "what_matters": what_matters.model_dump(mode="json"),
                    "resume_skills": self._resume_skills(),
                    "interview_intel": self._bounded_interview_intel_for(extraction),
                },
                ExperienceSelectionPayload,
            )
        except MissionProviderInvalidResponseError:
            return _heuristic()
        fact_by_id = {
            str(fact.get("id") or fact.get("experience_id")): fact
            for fact in _experience_facts()
            if fact.get("id") or fact.get("experience_id")
        }
        # Scrub + dedupe LLM rows, then enforce a conservative relevance floor
        # for obvious campus/admin entries. This prevents a provider fallback or
        # generic model answer from presenting every resume row as relevant.
        cleaned = []
        seen: set[str] = set()
        for row in payload.selections or []:
            exp_id = str(getattr(row, "experience_id", "") or "")
            if not exp_id or exp_id in seen:
                continue
            seen.add(exp_id)
            decision = getattr(getattr(row, "decision", None), "value", None) or str(getattr(row, "decision", "KEEP_AND_HIGHLIGHT"))
            why = OpenAIMissionProvider._strip_evidence_dump(str(getattr(row, "why", "") or ""))[:1000]
            why = OpenAIMissionProvider._align_experience_why(str(decision), why)[:1000]
            fact = fact_by_id.get(exp_id)
            if fact is not None:
                heuristic_decision, heuristic_why, _highlights, heuristic_confidence = OpenAIMissionProvider._heuristic_experience_decision(
                    fact, extraction=extraction, what_matters=what_matters
                )
                if heuristic_decision == "OMIT":
                    decision = heuristic_decision
                    why = heuristic_why
                elif heuristic_decision == "DEEMPHASIZE" and decision in {"KEEP", "KEEP_AND_HIGHLIGHT"} and heuristic_confidence >= 0.8:
                    decision = heuristic_decision
                    why = heuristic_why
            cleaned.append({
                "experience_id": exp_id,
                "decision": decision,
                "why": why,
                "related_capabilities": list(getattr(row, "related_capabilities", None) or [])[:20],
                "supporting_evidence_refs": OpenAIMissionProvider._uuid_strings(list(getattr(row, "supporting_evidence_refs", None) or []))[:20],
                "confidence": float(getattr(row, "confidence", 0.7) or 0.7),
            })
        if not cleaned:
            return _heuristic()
        return ExperienceSelectionPayload.model_validate({"selections": cleaned})

    @staticmethod
    def _heuristic_experience_decision(
        fact: dict[str, object], *, extraction: JobExtractionPayload, what_matters: WhatMattersPayload
    ) -> tuple[str, str, list[str], float]:
        """Conservative fallback/guardrail for obviously unrelated experiences."""
        title = str(fact.get("title") or "").strip()
        organization = str(fact.get("organization") or "").strip()
        description = str(fact.get("description") or fact.get("evidence_text") or "").strip()
        experience_type = str(fact.get("experience_type") or "").strip().upper()
        blob = " ".join((title, organization, description, experience_type)).casefold()
        work_content = " ".join((title, description)).casefold()
        caps = [str(item.name).strip() for item in (what_matters.core_capabilities or []) if str(item.name).strip()]
        cap_hits = [cap for cap in caps if cap.casefold() in blob]
        campus_terms = ("心理委员", "班委", "学生会", "体育部", "社团", "团支书", "学生干部", "宿舍", "志愿")
        # Awards and generic competition words are not technical evidence by
        # themselves; campus roles must show an actual product/engineering
        # action before they can outrank a project or research experience.
        technical_terms = ("项目", "研究", "实验", "模型", "风机", "算法", "数据", "评测", "产品", "结构", "工程", "系统", "量产", "python", "matlab", "autocad", "supermap", "效率", "设计", "优化", "测试", "发电", "波能", "系泊", "方案")
        admin_terms = ("助理", "运行保障", "行政", "资料整理", "事务")
        is_campus = any(term in blob for term in campus_terms) or experience_type in {"CAMPUS", "STUDENT", "LEADERSHIP", "VOLUNTEER"}
        technical_text = description.casefold() if is_campus else work_content
        has_technical = any(term in technical_text for term in technical_terms) or (bool(cap_hits) and not is_campus)
        is_admin = any(term in blob for term in admin_terms)
        label = title or organization or "这段经历"
        role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"
        if is_campus and not has_technical:
            return "OMIT", f"「{label}」主要是校园事务，与{role}的核心产品/技术职责关联弱，暂不放入本份岗位简历。", [], 0.92
        if is_admin and not has_technical:
            return "DEEMPHASIZE", f"「{label}」可保留为背景，但与{role}的核心能力关联有限，建议弱化篇幅，不作为重点经历。", cap_hits, 0.82
        highlights = cap_hits or ["项目中的个人负责部分", "使用的方法与决策", "可核对的结果或奖项"]
        detail = description[:180] if description else "；".join(highlights)
        return "KEEP_AND_HIGHLIGHT", f"「{label}」包含与{role}相关的可验证内容：{detail}。建议围绕个人动作、方法和结果展开。", highlights, 0.86 if has_technical else 0.62

    def build_resume_strategy(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload, selections: ExperienceSelectionPayload) -> ResumeStrategyPayload:
        eligible = [row for row in selections.selections if str(getattr(row.decision, "value", row.decision)) != "OMIT"]
        eligible_payload = ExperienceSelectionPayload(selections=eligible)
        payload = {"profile_facts": profile_facts, "extraction": extraction.model_dump(mode="json"), "what_matters": what_matters.model_dump(mode="json"), "selections": eligible_payload.model_dump(mode="json"), "resume_skills": self._resume_skills(), "interview_intel": self._bounded_interview_intel_for(extraction)}
        try:
            strategy = self._call(
                "build a grounded resume strategy. Only include experiences whose decision is KEEP_AND_HIGHLIGHT, KEEP, or DEEMPHASIZE; never include OMIT experiences. Each guidance item must use concrete facts from that experience, explain what to highlight, what to avoid, and interview risk notes. Output ONLY positioning_statement, recommended_experience_order, and experience_guidance as a list of objects with experience_id, role_in_story, what_to_highlight, what_to_avoid, target_capabilities, evidence_refs, interview_risk_notes",
                payload,
                ResumeStrategyPayload,
            )
            allowed = {row.experience_id for row in eligible_payload.selections}
            if allowed:
                order = [eid for eid in strategy.recommended_experience_order if eid in allowed]
                guidance = [item for item in strategy.experience_guidance if item.experience_id in allowed]
                fallback_guidance = {
                    item.experience_id: item
                    for item in OpenAIMissionProvider._strategy_fallback(
                        profile_facts=profile_facts,
                        extraction=extraction,
                        what_matters=what_matters,
                        selections=eligible_payload,
                    ).experience_guidance
                }
                # Models sometimes return the guidance envelope but omit the
                # two fields the UI needs. Fill only those missing fields from
                # the evidence-grounded fallback; keep the model's wording
                # when it supplied it.
                guidance = [
                    item.model_copy(update={
                        "what_to_highlight": item.what_to_highlight or fallback_guidance.get(item.experience_id, item).what_to_highlight,
                        "what_to_avoid": item.what_to_avoid or fallback_guidance.get(item.experience_id, item).what_to_avoid,
                    })
                    for item in guidance
                ]
                if not guidance:
                    guidance = list(fallback_guidance.values())
                if not order and guidance:
                    order = [item.experience_id for item in guidance]
                if order or guidance:
                    strategy = strategy.model_copy(
                        update={
                            "recommended_experience_order": order[:20],
                            "experience_guidance": guidance[:20],
                        }
                    )
            return strategy
        except MissionProviderInvalidResponseError:
            return OpenAIMissionProvider._strategy_fallback(
                profile_facts=profile_facts, extraction=extraction, what_matters=what_matters, selections=eligible_payload
            )

    @staticmethod
    def _strategy_fallback(*, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload, selections: ExperienceSelectionPayload) -> ResumeStrategyPayload:
        facts = {str(item.get("id") or item.get("experience_id")): item for item in profile_facts if isinstance(item, dict)}
        caps = [str(item.name).strip() for item in (what_matters.core_capabilities or []) if str(item.name).strip()]
        guidance: list[dict[str, object]] = []
        for row in selections.selections:
            fact = facts.get(str(row.experience_id), {})
            title = str(fact.get("title") or fact.get("organization") or "这段经历").strip()
            description = str(fact.get("description") or fact.get("evidence_text") or "").strip()
            clauses = [part.strip(" ，；;。") for part in re.split(r"[。；;\n]+", description) if part.strip()]
            highlights = (clauses[:3] or list(row.related_capabilities or caps) or ["个人负责的动作与方法", "可核对的结果"])[:5]
            guidance.append({
                "experience_id": str(row.experience_id),
                "role_in_story": f"围绕「{title}」说明个人负责的动作、方法与结果，优先连接目标岗位的{ '、'.join((row.related_capabilities or caps)[:3]) or '核心能力'}。",
                "what_to_highlight": highlights,
                "what_to_avoid": ["不要把团队成果写成个人独立完成", "不要补写原简历没有的数字、工具或结果"],
                "target_capabilities": list(row.related_capabilities or caps)[:5],
                "evidence_refs": OpenAIMissionProvider._uuid_strings(list(row.supporting_evidence_refs or [])),
                "interview_risk_notes": ["准备说明个人贡献、决策依据和结果证据"],
            })
        company = extraction.company if extraction.company and extraction.company != "UNKNOWN" else "目标公司"
        role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"
        return ResumeStrategyPayload.model_validate({
            "positioning_statement": f"面向{company}的{role}，优先展示有真实证据、能说明个人动作和结果的经历。",
            "recommended_experience_order": [str(row.experience_id) for row in selections.selections][:20],
            "experience_guidance": guidance[:20],
        })

    def build_target_resume(
        self,
        *,
        profile_facts: list[dict[str, object]],
        extraction: JobExtractionPayload,
        strategy: ResumeStrategyPayload,
        version: int,
        what_matters: WhatMattersPayload | None = None,
        selections: ExperienceSelectionPayload | None = None,
        interview_intel: list[dict[str, object]] | None = None,
        raw_jd: str | None = None,
        mission_id: str | None = None,
    ) -> TargetResumePayload:
        """Real LLM Target Resume generation with full mission context (no strategy-only copy)."""
        from .resume_intelligence import select_applicable_resume_skills

        applicable_skills = select_applicable_resume_skills(
            role=extraction.role,
            role_family=extraction.role_family,
            company=extraction.company,
            competencies=[*extraction.capabilities, *extraction.keywords],
            min_count=5,
            max_count=12,
        )
        skill_count = len(applicable_skills)
        wm = what_matters.model_dump(mode="json") if what_matters is not None else {}
        sel = selections.model_dump(mode="json") if selections is not None else {"selections": []}
        from .mission_intelligence import bounded_intel_records

        intel = bounded_intel_records(interview_intel if interview_intel is not None else self._interview_intel_for(extraction))
        jd_text = (raw_jd or "").strip()
        if len(jd_text) > 12_000:
            jd_text = jd_text[:12_000]

        user_payload = {
            "TARGET_JOB": {
                "company": extraction.company,
                "role": extraction.role,
                "role_family": extraction.role_family,
                "seniority": extraction.seniority,
                "location": extraction.location,
            },
            "PARSED_ROLE": extraction.model_dump(mode="json"),
            "RAW_JD": jd_text,
            "WHAT_MATTERS": wm,
            "COMPANY_INTERVIEW_CONTEXT": intel,
            "SOURCE_RESUME": profile_facts,
            "CONFIRMED_EXPERIENCE_DECISIONS": sel,
            "RESUME_STRATEGY": strategy.model_dump(mode="json"),
            "GLOBAL_EVIDENCE": profile_facts,
            "APPLICABLE_RESUME_SKILLS": applicable_skills,
            "version": version,
            "mission_id": mission_id,
        }
        operation = (
            "draft a versioned target resume via Resume Optimization. "
            "Use TARGET_JOB, PARSED_ROLE, WHAT_MATTERS, COMPANY_INTERVIEW_CONTEXT, SOURCE_RESUME, "
            "CONFIRMED_EXPERIENCE_DECISIONS, RESUME_STRATEGY, GLOBAL_EVIDENCE, APPLICABLE_RESUME_SKILLS. "
            "For every included experience, preserve the source resume's concrete facts: project or role name, dates, "
            "the candidate's actual actions, methods/tools, measurable result, and awards when present. Rewrite for the "
            "target JD with detailed Chinese bullets; do not collapse a fact-rich project into a generic one-line claim, "
            "do not invent numbers, tools, ownership, or outcomes, and do not add self-evaluation phrases such as 体现/展现/可准备. "
            "If the JD has a material capability gap, add one or two concrete, JD-specific synthetic project drafts (not generic course ideas) with source_experience_id=null. "
            "For a physical-AI or intelligent-hardware product role, prefer a draft covering product definition, sensor/edge-cloud trade-offs, prototype integration, test metrics, and a PRD/demo deliverable. "
            "The display_name MUST start with 项目草案 and risk_flags MUST include SYNTHETIC_PROJECT; keep drafts clearly framed as editable projects to complete, never as prior employment, and never add fabricated numeric results. "
            "Output TargetResumeGenerationResult JSON only."
        )
        started = time.perf_counter()
        try:
            generation = self._call(operation, user_payload, TargetResumeGenerationResult)
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.info(
                "target_resume_provider_call mission_id=%s skill_count=%s latency_ms=%s version=%s experiences=%s",
                mission_id or "-",
                skill_count,
                latency_ms,
                version,
                len(generation.experiences),
            )
            if not generation.experiences or not any(block.bullets for block in generation.experiences if block.include):
                raise MissionProviderInvalidResponseError(reason="empty_response")
            payload = self._generation_to_target_payload(generation, strategy=strategy)
            if not payload.bullets:
                raise MissionProviderInvalidResponseError(reason="empty_response")
            # Keep the portfolio-project fallback explicit when the model
            # overlooks a material JD gap. This is never exported as a fact;
            # it remains a clearly labelled suggestion until the candidate
            # actually completes and confirms it.
            jd_tokens = " ".join([extraction.role, extraction.role_family, *extraction.capabilities, *extraction.keywords]).casefold()
            is_hardware_product = any(token in jd_tokens for token in ("智能硬件", "物理ai", "physical ai", "product", "产品"))
            has_synthetic = any("SYNTHETIC_PROJECT" in {str(flag).upper() for flag in bullet.risk_flags} for bullet in payload.bullets)
            if is_hardware_product and not has_synthetic:
                draft = {
                    "source_experience_id": None,
                    "original_text": "建议补做项目（尚未完成）",
                    "suggested_text": "项目草案：智能硬件 AI 产品验证闭环——完成目标用户与竞品调研，输出端侧/云侧方案和传感器、算力选型对比；制作可交互原型或 Demo，设计测试指标与数据记录表，形成 PRD、技术选型表和测试报告。",
                    "final_text": None,
                    "reason": "目标 JD 强调智能硬件产品定义、软硬件方案取舍和数据驱动验证；该项目用于补齐可展示的作品集证据，完成前不作为既有经历。",
                    "jd_refs": [*extraction.capabilities[:4], *extraction.keywords[:4]],
                    "evidence_refs": [],
                    "resume_skill_refs": [],
                    "risk_flags": ["SYNTHETIC_PROJECT", "GROUNDING:NEEDS_CONFIRMATION"],
                    "target_capabilities": ["智能硬件产品定义", "原型与测试验证", "数据驱动决策"],
                    "grounding_status": "NEEDS_CONFIRMATION",
                }
                payload = TargetResumePayload.model_validate({**payload.model_dump(mode="json"), "bullets": [*payload.model_dump(mode="json")["bullets"], draft]})
            return payload
        except MissionProviderInvalidResponseError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "target_resume_provider_invalid mission_id=%s skill_count=%s latency_ms=%s",
                mission_id or "-",
                skill_count,
                latency_ms,
            )
            raise
        except MissionProviderError:
            latency_ms = int((time.perf_counter() - started) * 1000)
            logger.warning(
                "target_resume_provider_error mission_id=%s skill_count=%s latency_ms=%s",
                mission_id or "-",
                skill_count,
                latency_ms,
            )
            raise

    def red_team(self, *, profile_facts: list[dict[str, object]], extraction: JobExtractionPayload, what_matters: WhatMattersPayload, target_resume: TargetResumePayload) -> RedTeamPayload:
        prompt = (
            "stress-test target resume claims for interview risk. "
            "Do NOT echo evidence IDs, UUIDs, or dogfood-req-* tokens inside claim/why/recommended_next_step text. "
            "Keep evidence_refs as data only (UUID list), never concatenate them into narrative fields."
        )
        payload = {
            "profile_facts": profile_facts,
            "extraction": extraction.model_dump(mode="json"),
            "what_matters": what_matters.model_dump(mode="json"),
            "target_resume": target_resume.model_dump(mode="json"),
            "resume_skills": self._resume_skills(),
            "interview_intel": self._bounded_interview_intel_for(extraction),
        }
        try:
            return self._call(prompt, payload, RedTeamPayload)
        except MissionProviderInvalidResponseError:
            return OpenAIMissionProvider._red_team_fallback(target_resume)

    @staticmethod

    @staticmethod
    def _pack_company_role(extraction: JobExtractionPayload) -> tuple[str, str]:
        company = extraction.company if extraction.company and extraction.company != "UNKNOWN" else "目标公司"
        role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"
        return company, role

    @staticmethod
    def _distinct_topic_questions(
        focus: str,
        *,
        company: str,
        role: str,
        index: int = 0,
        intel_questions: list[str] | None = None,
    ) -> list[str]:
        """Per-topic questions — never the copy-paste「哪个近期项目最能证明你的「X」？」shell."""
        focus = (focus or "").strip() or "本岗匹配"
        label = focus
        # Prefer concrete intel/Niuke questions first.
        out: list[str] = []
        for q in intel_questions or []:
            q = OpenAIMissionProvider._strip_evidence_dump(str(q).strip())
            if q and q not in out and "哪个近期项目最能证明你的" not in q:
                out.append(q)
            if len(out) >= 2:
                return out[:3]

        blob = f"{focus}".casefold()
        name = focus

        def _has(*keys: str) -> bool:
            return any(k.casefold() in blob or k in name for k in keys)

        if _has("评测", "eval", "metric", "指标", "ab", "a/b", "实验"):
            shaped = [
                f"请讲一次你设计或推动「{label}」的完整闭环：指标如何选、样本怎么建、结论如何落地。",
                f"当「{label}」结果不及预期时，你如何拆问题并推动算法/工程/业务一起改？",
            ]
        elif _has("agent", "rag", "prompt", "提示", "llm", "大模型", "gpt", "模型应用"):
            shaped = [
                f"用一个真实案例说明你如何把「{label}」做成可上线方案：选型、边界与取舍。",
                f"若面试官追问「{label}」的失败或返工，你如何讲清原因、你的动作与复用价值？",
            ]
        elif _has("协作", "沟通", "跨团队", "stakeholder", "合作", "对齐"):
            shaped = [
                f"举一次「{label}」里多方目标冲突的经历：你如何对齐{company}式交付节奏并拿到结果？",
                f"面向{role}，你如何用纪要/评审/优先级机制证明「{label}」不是空谈？",
            ]
        elif _has("增长", "转化", "用户", "growth", "retention", "留存"):
            shaped = [
                f"讲一次你用「{label}」拉动关键漏斗的经历：假设、实验、结果与可复用结论。",
                f"如果增长数据好看但体验变差，你如何在「{label}」上做取舍并向业务解释？",
            ]
        elif _has("规划", "路线", "roadmap", "优先级", "落地", "交付"):
            shaped = [
                f"你如何为「{label}」排优先级并推动从原型到上线？请给出时间线与决策依据。",
                f"当资源不够时，你在「{label}」上砍掉了什么、保留了什么？结果如何验证？",
            ]
        elif _has("数据", "分析", "sql", "洞察"):
            shaped = [
                f"用一次「{label}」相关分析说明：问题定义、数据口径、洞察如何变成产品动作。",
                f"别人质疑你的数据结论时，你如何用口径与对照实验守住「{label}」判断？",
            ]
        else:
            # Rotate shapes by index so adjacent capabilities never share one template.
            pool = [
                f"结合{company}·{role}，用一段可核对经历说明你如何体现「{label}」。",
                f"「{label}」中你的个人决策与团队贡献分别是什么？结果怎样验证？",
                f"若对方质疑你的「{label}」深度，你准备用哪条目标简历证据回应？",
                f"你在「{label}」上踩过的最大坑是什么？后来怎么改、如何复用？",
                f"面向{role}，你认为「{label}」最容易被追问的细节是什么？请先完整答一遍。",
                f"请对比两种做法，说明你在「{label}」上为何选了最终方案。",
            ]
            shaped = [pool[index % len(pool)], pool[(index + 2) % len(pool)]]

        for q in shaped:
            if q not in out:
                out.append(q)
        return out[:3]

    @staticmethod
    def _concrete_knowledge_bullets(
        focus: str,
        *,
        company: str,
        role: str,
        intel_hints: list[str] | None = None,
    ) -> list[str]:
        """2–4 concrete Chinese study/answer points — never the FE placeholder shell."""
        focus = (focus or "").strip() or "本岗匹配"
        bullets: list[str] = []
        for hint in intel_hints or []:
            h = OpenAIMissionProvider._strip_evidence_dump(str(hint).strip())
            if not h:
                continue
            if "待补充" in h:
                continue
            if "UNKNOWN" in h.upper():
                continue
            if len(h) > 160:
                h = h[:157] + "…"
            if h not in bullets:
                bullets.append(h if h.startswith(("高频", "概念", "证据", "面经", "准备", "补")) else f"面经要点：{h}")
            if len(bullets) >= 2:
                break
        bullets.extend(
            [
                f"高频问法：围绕「{focus}」的场景题/追问（优先对照{company}面经或牛客真题）",
                f"概念准备：能用自己的话解释「{focus}」与{role}职责的对应关系，并举 1 个边界例子",
                f"证据方向：从目标简历挑 1 条可核对经历，按背景-行动-结果讲清个人贡献（不编造指标）",
            ]
        )
        # de-dupe preserve order
        out: list[str] = []
        for b in bullets:
            if b and b not in out:
                out.append(b)
        return out[:4]


    def _interview_pack_fallback(
        *,
        extraction: JobExtractionPayload,
        what_matters: WhatMattersPayload,
        interview_intel: list[dict[str, object]],
        target_resume: TargetResumePayload,
        red_team: RedTeamPayload,
    ) -> InterviewPackPayload:
        """Heuristic topics when the LLM returns empty/invalid interview packs."""
        topics: list[dict[str, object]] = []

        def _is_demo_intel(item: dict[str, object]) -> bool:
            blob = " ".join(
                [
                    str(item.get("skill_id") or ""),
                    str(item.get("name") or ""),
                    str(item.get("topic") or ""),
                    str(item.get("provenance") or ""),
                    " ".join(str(x) for x in (item.get("source_refs") or [])),
                ]
            ).upper()
            return (
                "DEMO_" in blob
                or blob.startswith("DEMO")
                or "SYNTHETIC" in blob
                or "DEMO ONLY" in blob
                or "SYNTHETIC_DEMO" in blob
            )

        def _has_cjk(value: object) -> bool:
            return any("\u4e00" <= ch <= "\u9fff" for ch in str(value or ""))

        def _intel_sort_key(item: dict[str, object]) -> tuple:
            skill = str(item.get("skill_id") or "").upper()
            name = str(item.get("name") or "")
            refs = " ".join(str(x) for x in (item.get("source_refs") or [])).upper()
            curated = 0 if (
                skill.startswith("CURATED_")
                or "NIUKE" in refs
                or "NOWCODER" in refs
                or "牛客" in str(item.get("name") or "")
                or "牛客" in refs
            ) else 1
            demo = 1 if _is_demo_intel(item) else 0
            cjk = 0 if (_has_cjk(item.get("topic")) or _has_cjk(item.get("name")) or _has_cjk(item.get("body"))) else 1
            return (demo, curated, cjk, skill)

        def _intel_refs(item: dict[str, object]) -> list[str]:
            refs: list[str] = []
            for key in ("id", "source", "ref", "intel_ref", "skill_id"):
                value = item.get(key)
                values = value if isinstance(value, list) else [value]
                for entry in values:
                    value_text = str(entry or "").strip()
                    if value_text and value_text not in refs:
                        refs.append(value_text)
            for entry in (item.get("source_refs") or []):
                value_text = str(entry or "").strip()
                if value_text and value_text not in refs:
                    refs.append(value_text)
            return refs

        def _intel_questions(item: dict[str, object]) -> list[str]:
            raw = item.get("question_patterns") or item.get("questions") or item.get("sample_questions") or []
            patterns = [raw] if isinstance(raw, str) else list(raw) if isinstance(raw, list) else []
            body = str(item.get("body") or "")
            in_section = False
            for line in body.splitlines():
                stripped = line.strip()
                if not stripped:
                    if in_section:
                        in_section = False
                    continue
                if "question patterns" in stripped.casefold() or ("问题" in stripped and ("问法" in stripped or "题" in stripped)):
                    in_section = True
                    continue
                if in_section and (stripped.startswith(("-", "*", "•")) or stripped.endswith(("？", "?"))):
                    patterns.append(stripped.lstrip("-*• "))
            out: list[str] = []
            for value in patterns:
                question = OpenAIMissionProvider._strip_evidence_dump(str(value).strip())
                if question and question not in out:
                    out.append(question)
            return out[:8]

        def _add(
            topic: str,
            why: str,
            *,
            priority: str = "HIGH",
            claims: list[str] | None = None,
            capabilities: list[str] | None = None,
            question_patterns: list[str] | None = None,
            evidence_expected: list[str] | None = None,
            intel_refs: list[str] | None = None,
        ) -> None:
            cleaned = (topic or "").strip()
            if not cleaned:
                return
            if any(str(item.get("topic", "")).strip() == cleaned for item in topics):
                return
            topics.append(
                {
                    "priority": priority,
                    "topic": cleaned[:600],
                    "why": (why or "本岗面试很可能追问这个主题。").strip()[:1000],
                    "claims": list(claims or [])[:20],
                    "capabilities": list(capabilities or [])[:20],
                    "intel_refs": list(intel_refs or [])[:20],
                    "question_patterns": list(question_patterns or [])[:20],
                    "evidence_expected": list(evidence_expected or [])[:20],
                }
            )

        caps = [c.name for c in (what_matters.core_capabilities or []) if getattr(c, "name", None)]
        company, role = OpenAIMissionProvider._pack_company_role(extraction)
        intel_items = [item for item in (interview_intel or []) if isinstance(item, dict)]
        intel_items.sort(key=_intel_sort_key)
        preferred_intel = [item for item in intel_items if not _is_demo_intel(item)]
        demo_intel = [item for item in intel_items if _is_demo_intel(item)]
        # Prefer Niuke/CURATED/Chinese; only fall back to DEMO_/synthetic English if nothing else.
        ordered_intel = (preferred_intel or demo_intel)[:8]
        for item in ordered_intel:
            topic = str(
                item.get("topic")
                or item.get("title")
                or item.get("theme")
                or ""
            ).strip()
            if not topic:
                # Avoid English DEMO pack names as topics when body/competency can ground a CN label.
                name = str(item.get("name") or "").strip()
                competency = str(item.get("competency") or "").strip()
                if _has_cjk(name):
                    topic = name
                elif competency:
                    topic = f"面试重点：{competency}"
                elif name and not _is_demo_intel(item):
                    topic = name
                else:
                    continue
            why = str(
                item.get("why")
                or item.get("summary")
                or item.get("rationale")
                or f"来自面经/情报的常见追问方向（{company}）。"
            ).replace("CURATED", "").replace("SYNTHETIC_DEMO", "").strip()
            refs = _intel_refs(item)
            patterns = _intel_questions(item)
            _add(
                topic,
                why,
                priority="HIGH",
                capabilities=caps[:3],
                question_patterns=OpenAIMissionProvider._distinct_topic_questions(
                    topic,
                    company=OpenAIMissionProvider._pack_company_role(extraction)[0],
                    role=OpenAIMissionProvider._pack_company_role(extraction)[1],
                    index=len(topics),
                    intel_questions=patterns[:5],
                ),
                intel_refs=refs[:5],
                evidence_expected=OpenAIMissionProvider._concrete_knowledge_bullets(
                    topic,
                    company=OpenAIMissionProvider._pack_company_role(extraction)[0],
                    role=OpenAIMissionProvider._pack_company_role(extraction)[1],
                    intel_hints=[why],
                ),
            )

        for finding in (red_team.findings or [])[:8]:
            claim = str(getattr(finding, "claim", "") or "").strip()
            risk = str(getattr(finding, "risk_level", "") or "").upper()
            followups = [str(x).strip() for x in (getattr(finding, "likely_followups", None) or []) if str(x).strip()][:5]
            _add(
                claim or "简历表述可辩护性",
                str(
                    getattr(finding, "why", "")
                    or getattr(finding, "company_interview_trigger", "")
                    or "压力测试标出了高风险点，需要准备可追问的具体回答。"
                ),
                priority="HIGH" if risk == "HIGH" else "MEDIUM",
                claims=[claim] if claim else [],
                capabilities=caps[:3],
                question_patterns=followups
                or [
                    "请举一个能证明这条表述的具体例子？",
                    "其中你个人贡献和团队贡献分别是什么？",
                ],
                evidence_expected=[
                    str(
                        getattr(finding, "recommended_next_step", "")
                        or "准备可核对的证据和可量化结果"
                    ).strip()
                ],
            )

        for cap_index, cap in enumerate((what_matters.core_capabilities or [])[:5]):
            name = str(getattr(cap, "name", "") or "").strip()
            why = str(
                getattr(cap, "why", "")
                or f"岗位看重「{name}」，面试常追问可验证证据。"
            ).strip()
            focus = name or "核心能力"
            intel_qs = []
            intel_hints = []
            for item in ordered_intel:
                blob = " ".join(str(item.get(k) or "") for k in ("topic", "title", "theme", "name", "competency", "body", "summary"))
                if name and name[:4] not in blob and focus.casefold()[:4] not in blob.casefold():
                    continue
                intel_qs.extend(_intel_questions(item))
                for key in ("body", "summary", "why", "rationale"):
                    val = str(item.get(key) or "").strip()
                    if val:
                        intel_hints.append(val.splitlines()[0][:120] if val else "")
            _add(
                f"能力证明：{name}" if name else "核心能力证明",
                why,
                priority="MEDIUM",
                capabilities=[name] if name else caps[:3],
                question_patterns=OpenAIMissionProvider._distinct_topic_questions(
                    focus, company=company, role=role, index=cap_index, intel_questions=intel_qs
                ),
                evidence_expected=OpenAIMissionProvider._concrete_knowledge_bullets(
                    focus, company=company, role=role, intel_hints=intel_hints
                ),
            )

        positioning = str(getattr(target_resume, "positioning_statement", "") or "").strip()
        if positioning:
            _add(
                "开场定位与代表作经历",
                "面试官通常会检验你的定位是否贴合 JD，并追问代表作经历。",
                priority="RESUME_SPECIFIC",
                claims=[positioning[:500]],
                capabilities=caps[:3],
                question_patterns=[
                    "两分钟说明你为什么适合这个岗位？",
                    "简历里哪段经历最值得对方记住？",
                ],
                evidence_expected=["准备 1–2 条与定位声明一致的经历"],
            )

        if not topics:
            company = extraction.company if extraction.company and extraction.company != "UNKNOWN" else "目标公司"
            role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"
            _add(
                f"{company} · {role} 岗位匹配",
                "模型未返回结构化题单时的兜底：准备岗位匹配说明与代表作成绩。",
                priority="HIGH",
                question_patterns=["为什么选择这个岗位？", "你最能证明匹配 JD 的证据是什么？"],
                evidence_expected=["准备与 JD 关键词对齐的经历要点"],
            )

        return InterviewPackPayload.model_validate({"topics": topics[:12]})

    @staticmethod
    def _enrich_interview_topics(
        topics: list,
        *,
        extraction: JobExtractionPayload,
        what_matters: WhatMattersPayload,
        interview_intel: list[dict[str, object]],
    ) -> list[dict[str, object]]:
        """Ensure each topic has Chinese question_patterns + evidence_expected for FE 提问/该补的知识."""
        caps = [c.name for c in (what_matters.core_capabilities or []) if getattr(c, "name", None)]
        company = extraction.company if extraction.company and extraction.company != "UNKNOWN" else "目标公司"
        role = extraction.role if extraction.role and extraction.role != "UNKNOWN" else "目标岗位"

        def _intel_questions(topic: str) -> list[str]:
            tlow = (topic or "").lower()
            out: list[str] = []
            for item in interview_intel or []:
                if not isinstance(item, dict):
                    continue
                blob = " ".join(
                    str(item.get(k) or "")
                    for k in ("topic", "title", "theme", "name", "competency", "body")
                )
                if topic and topic[:8] not in blob and tlow[:8] not in blob.lower():
                    # still allow curated Niuke questions as general bank
                    refs = " ".join(str(x) for x in (item.get("source_refs") or [])).upper()
                    if "NIUKE" not in refs and "NOWCODER" not in refs and "牛客" not in blob:
                        continue
                patterns = item.get("question_patterns") or item.get("questions") or item.get("sample_questions") or []
                if isinstance(patterns, str):
                    patterns = [patterns]
                for q in patterns:
                    q = OpenAIMissionProvider._strip_evidence_dump(str(q).strip())
                    if q and q not in out:
                        out.append(q)
                body = str(item.get("body") or item.get("summary") or "").strip()
                if body and ("？" in body or "?" in body):
                    for part in re.split(r"[\n；;]", body):
                        part = OpenAIMissionProvider._strip_evidence_dump(part.strip())
                        if ("？" in part or "?" in part) and 6 <= len(part) <= 200 and part not in out:
                            out.append(part)
                if len(out) >= 5:
                    break
            return out[:5]

        enriched: list[dict[str, object]] = []
        for raw in topics or []:
            if hasattr(raw, "model_dump"):
                item = raw.model_dump(mode="json")
            elif isinstance(raw, dict):
                item = dict(raw)
            else:
                continue
            topic = OpenAIMissionProvider._strip_evidence_dump(str(item.get("topic") or "").strip())[:600]
            if not topic:
                continue
            why = OpenAIMissionProvider._strip_evidence_dump(str(item.get("why") or "").strip())[:1000]
            if not why:
                why = f"面试官很可能围绕「{topic}」追问可验证细节（{company}·{role}）。"
            patterns = [OpenAIMissionProvider._strip_evidence_dump(str(x).strip()) for x in (item.get("question_patterns") or []) if str(x).strip()]
            # Accept aliases from LLM / intel
            for key in ("question", "questions", "knowledge_questions", "sample_questions"):
                extra = item.get(key)
                if isinstance(extra, str) and extra.strip():
                    patterns.append(OpenAIMissionProvider._strip_evidence_dump(extra.strip()))
                elif isinstance(extra, list):
                    patterns.extend(OpenAIMissionProvider._strip_evidence_dump(str(x).strip()) for x in extra if str(x).strip())
            patterns = [p for p in dict.fromkeys(patterns) if p][:20]
            if not patterns:
                patterns = _intel_questions(topic)
            if not patterns:
                patterns = OpenAIMissionProvider._distinct_topic_questions(
                    topic,
                    company=company,
                    role=role,
                    index=len(enriched),
                    intel_questions=_intel_questions(topic),
                )
            # Ban identical copy-paste template that only swaps X
            patterns = [
                p for p in patterns
                if "哪个近期项目最能证明你的" not in p
            ] or OpenAIMissionProvider._distinct_topic_questions(
                topic, company=company, role=role, index=len(enriched)
            )
            evidence = [OpenAIMissionProvider._strip_evidence_dump(str(x).strip()) for x in (item.get("evidence_expected") or []) if str(x).strip()]
            for key in ("knowledge_to_study", "knowledge", "study_points", "to_study"):
                extra = item.get(key)
                if isinstance(extra, str) and extra.strip():
                    evidence.append(OpenAIMissionProvider._strip_evidence_dump(extra.strip()))
                elif isinstance(extra, list):
                    evidence.extend(OpenAIMissionProvider._strip_evidence_dump(str(x).strip()) for x in extra if str(x).strip())
            evidence = [e for e in dict.fromkeys(evidence) if e][:20]
            # Drop FE placeholder residue if model echoed it
            evidence = [e for e in evidence if e and "待补充" not in e]
            if not evidence or len(evidence) < 2:
                evidence = OpenAIMissionProvider._concrete_knowledge_bullets(
                    topic,
                    company=company,
                    role=role,
                    intel_hints=evidence,
                )
            enriched.append({
                "priority": item.get("priority") or "HIGH",
                "topic": topic,
                "why": why,
                "claims": list(item.get("claims") or [])[:20],
                "capabilities": list(item.get("capabilities") or caps[:3])[:20],
                "intel_refs": [str(x) for x in (item.get("intel_refs") or [])][:20],
                "question_patterns": patterns[:20],
                "evidence_expected": evidence[:20],
            })
        return enriched

    def build_interview_pack(
        self,
        *,
        extraction: JobExtractionPayload,
        what_matters: WhatMattersPayload,
        interview_intel: list[dict[str, object]],
        target_resume: TargetResumePayload,
        red_team: RedTeamPayload,
    ) -> InterviewPackPayload:
        pack = None
        try:
            pack = self._call(
                "build a company-specific interview pack (Simplified Chinese topics; each topic MUST include DISTINCT non-empty question_patterns shaped for that topic (ban identical templates that only swap capability name e.g. 哪个近期项目最能证明你的「X」); each topic MUST include 2-4 concrete evidence_expected / knowledge_to_study bullets: 高频问法/概念/证据方向 — never empty and never literal placeholder 待补充; prefer interview_intel/Niuke; never invent metrics/employers; never put UUIDs in topic/why/questions)",
                {
                    "extraction": extraction.model_dump(mode="json"),
                    "what_matters": what_matters.model_dump(mode="json"),
                    "interview_intel": interview_intel,
                    "target_resume": target_resume.model_dump(mode="json"),
                    "red_team": red_team.model_dump(mode="json"),
                },
                InterviewPackPayload,
            )
        except MissionProviderError:
            # Soft-fail: timeout/upstream/invalid JSON still return heuristic topics
            # instead of surfacing HTTP 502 to the Mission interview tab.
            pack = None
        if pack is None or not pack.topics:
            pack = OpenAIMissionProvider._interview_pack_fallback(
                extraction=extraction,
                what_matters=what_matters,
                interview_intel=interview_intel,
                target_resume=target_resume,
                red_team=red_team,
            )
        enriched = OpenAIMissionProvider._enrich_interview_topics(
            list(pack.topics or []),
            extraction=extraction,
            what_matters=what_matters,
            interview_intel=interview_intel,
        )
        if not enriched:
            pack = OpenAIMissionProvider._interview_pack_fallback(
                extraction=extraction,
                what_matters=what_matters,
                interview_intel=interview_intel,
                target_resume=target_resume,
                red_team=red_team,
            )
            enriched = OpenAIMissionProvider._enrich_interview_topics(
                list(pack.topics or []),
                extraction=extraction,
                what_matters=what_matters,
                interview_intel=interview_intel,
            )
        return InterviewPackPayload.model_validate({"topics": enriched[:12]})


_provider: MissionProvider | None = None


def set_mission_provider(provider: MissionProvider | None) -> None:
    global _provider
    _provider = provider


def get_mission_provider() -> MissionProvider:
    return _provider if _provider is not None else OpenAIMissionProvider()

