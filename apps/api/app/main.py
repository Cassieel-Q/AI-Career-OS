from __future__ import annotations

import json
import logging
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import NoReturn, Protocol, TypeVar
from urllib.parse import urlparse
from uuid import UUID

import fitz
import httpx
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, ConfigDict, Field, ValidationError
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.database import get_db
from app.profile_schemas import ProfileRead, ProfileUpdate
from app.profile_service import (
    confirm_profile,
    create_draft_profile,
    get_profile,
    update_draft_profile,
)
from app.resume_normalization import normalize_resume_extraction
from app.resume_schemas import (
    Certification,
    Education,
    Experience,
    ExperienceType,
    LeanCertification,
    LeanEducation,
    LeanExperience,
    LeanResumeExtractionResult,
    LeanSkill,
    ResumeExtractionResult,
    Skill,
)
from app.resume_sections import ResumeSection, completeness_warnings, detect_sections, section_for_warning

MAX_RESUME_BYTES = 10 * 1024 * 1024
LOCAL_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
DEFAULT_OPENAI_TIMEOUT_SECONDS = 30.0
MAX_OPENAI_TIMEOUT_SECONDS = 120.0
DEFAULT_OPENAI_MAX_RETRIES = 0
MAX_OPENAI_RETRIES = 2
MAX_LLM_CALLS_PER_RESUME = 5
MAX_SECTION_REPAIR_CALLS_PER_RESUME = MAX_LLM_CALLS_PER_RESUME - 1
_TIMING_FIELDS = (
    "pdf_extract_ms",
    "initial_llm_ms",
    "education_llm_ms",
    "experience_llm_ms",
    "campus_llm_ms",
    "other_llm_ms",
    "education_repair_1_ms",
    "education_repair_2_ms",
    "other_section_repair_ms",
    "grounding_normalization_ms",
    "db_persist_ms",
    "total_resume_ms",
    "total_llm_calls",
)
logger = logging.getLogger(__name__)

_PROVIDER_FAILURE_TIMEOUT = "timeout"
_PROVIDER_FAILURE_CONNECTION = "connection_error"
_PROVIDER_FAILURE_UPSTREAM = "upstream_status_error"
_PROVIDER_FAILURE_STRUCTURED_OUTPUT = "structured_output_validation"
_PROVIDER_FAILURE_INTERNAL = "unexpected_internal_processing"
_PROVIDER_FAILURE_RESPONSES = {
    _PROVIDER_FAILURE_TIMEOUT: (504, "Resume extraction provider timed out"),
    _PROVIDER_FAILURE_CONNECTION: (502, "Resume extraction provider unavailable"),
    _PROVIDER_FAILURE_UPSTREAM: (502, "Resume extraction provider unavailable"),
    _PROVIDER_FAILURE_STRUCTURED_OUTPUT: (502, "Resume extraction returned invalid structured output"),
    _PROVIDER_FAILURE_INTERNAL: (500, "Resume extraction processing failed"),
}
_MODEL_T = TypeVar("_MODEL_T", bound=BaseModel)
_FULL_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (no Markdown or commentary) with these top-level arrays: education, skills, "
    "experiences, and certifications; use [] when a section has no supported facts. Education items require "
    "institution and may include degree, field_of_study, dates, and relevant_courses (an array of strings); "
    "skill items require name; experience items require title and may include organization, dates, description, "
    "experience_type, and source_section; certification items require name and may include issuer, date, score, "
    "and status. Use null only for optional scalar fields and do not add unsupported fields."
)
_EDUCATION_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape: "
    '{"items":[{"institution":"...","degree":null,"field_of_study":null,"dates":null,'
    '"relevant_courses":[]}]}. '
    "Education items must use exactly institution, degree, field_of_study, dates, and relevant_courses; "
    "use null for missing optional scalar values and [] for no courses. "
    "Do not include evidence, provenance, raw, canonical, or any other fields."
)
_EXPERIENCE_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape: "
    '{"items":[{"title":"...","organization":null,"dates":null,'
    '"description":null,"experience_type":"WORK"}]}. '
    "Experience items must use exactly title, organization, dates, description, and experience_type; use the "
    "supported WORK, INTERNSHIP, PROJECT, or CAMPUS value when the heading supports it, and use null for "
    "missing optional scalar values. "
    "For each experience item, each optional field returned must be copied VERBATIM as one contiguous source value "
    "from the supplied section. "
    "Do not combine bullets or lines, normalize date punctuation, rewrite an organization, synthesize date ranges, "
    "or join separate content; return null when an optional field is not individually copyable verbatim. "
    "Do not include evidence, provenance, raw, canonical, source_section, or any other fields."
)
_CAMPUS_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape: "
    '{"items":[{"title":"...","organization":null,"dates":null,'
    '"description":null,"experience_type":"CAMPUS"}]}. '
    "Experience items must use exactly title, organization, dates, description, and experience_type=CAMPUS; use "
    "null for missing optional scalar values. "
    "For each experience item, each optional field returned must be copied VERBATIM as one contiguous source value "
    "from the supplied section. "
    "Do not combine bullets or lines, normalize date punctuation, rewrite an organization, synthesize date ranges, "
    "or join separate content; return null when an optional field is not individually copyable verbatim. "
    "Do not include evidence, provenance, raw, canonical, source_section, or any other fields."
)
_SKILLS_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape: "
    '{"items":[{"name":"..."}]}. '
    "Skill items must use exactly name; do not include proficiency or any other field. "
    "Do not include evidence, provenance, raw, canonical, or any other fields."
)
_CREDENTIALS_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape: "
    '{"items":[{"name":"...","issuer":null,"date":null,"score":null}]}. '
    "LeanCertification keys are exactly: name, issuer, date, score; it must not include status, credential_type, "
    "level, type, category, or any other key. Use null for missing optional scalar values. "
    "Do not include evidence, provenance, raw, canonical, or any other fields."
)
_LANGUAGE_JSON_OBJECT_CONTRACT = (
    " Return only a JSON object (JSON only; no Markdown or commentary) with exactly this object shape when both kinds "
    "are present: "
    '{"skills":[{"name":"..."}],"certifications":[{"name":"...","issuer":null,"date":null,"score":null}]}. '
    "Return only LeanSkill items with exactly name and LeanCertification items with exactly name, issuer, date, "
    "and score; either array may be [] when unsupported. Never add status, credential_type, level, type, category, "
    "or any other key. Use null for missing optional scalar values. Do not include "
    "evidence, provenance, raw, canonical, or any other fields."
)


class EducationSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LeanEducation] = Field(default_factory=list)


class ExperienceSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LeanExperience] = Field(default_factory=list)


class CampusSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LeanExperience] = Field(default_factory=list)


class SkillsSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LeanSkill] = Field(default_factory=list)


class CredentialSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    items: list[LeanCertification] = Field(default_factory=list)


class LanguageSectionPayload(BaseModel):
    model_config = ConfigDict(extra="forbid")

    skills: list[LeanSkill] = Field(default_factory=list)
    certifications: list[LeanCertification] = Field(default_factory=list)


_SECTION_PAYLOAD_MODELS: dict[str, type[BaseModel]] = {
    "EDUCATION": EducationSectionPayload,
    "COURSES": EducationSectionPayload,
    "EXPERIENCE": ExperienceSectionPayload,
    "CAMPUS": CampusSectionPayload,
    "SKILLS": SkillsSectionPayload,
    "CREDENTIALS": CredentialSectionPayload,
    "LANGUAGE": LanguageSectionPayload,
}
_SECTION_IGNORED_PROVIDER_KEYS: dict[str, frozenset[str]] = {
    "CREDENTIALS": frozenset({"skills"}),
}


def _section_payload_to_lean_result(
    payload: BaseModel,
    section_label: str,
) -> LeanResumeExtractionResult:
    if section_label in {"EDUCATION", "COURSES"}:
        section_payload = payload
        assert isinstance(section_payload, EducationSectionPayload)
        return LeanResumeExtractionResult(education=section_payload.items)
    if section_label == "EXPERIENCE":
        section_payload = payload
        assert isinstance(section_payload, ExperienceSectionPayload)
        return LeanResumeExtractionResult(experiences=section_payload.items)
    if section_label == "CAMPUS":
        section_payload = payload
        assert isinstance(section_payload, CampusSectionPayload)
        return LeanResumeExtractionResult(
            experiences=[
                item.model_copy(update={"experience_type": ExperienceType.CAMPUS})
                for item in section_payload.items
            ]
        )
    if section_label == "SKILLS":
        section_payload = payload
        assert isinstance(section_payload, SkillsSectionPayload)
        return LeanResumeExtractionResult(skills=section_payload.items)
    if section_label == "CREDENTIALS":
        section_payload = payload
        assert isinstance(section_payload, CredentialSectionPayload)
        return LeanResumeExtractionResult(certifications=section_payload.items)
    if section_label == "LANGUAGE":
        section_payload = payload
        assert isinstance(section_payload, LanguageSectionPayload)
        return LeanResumeExtractionResult(
            skills=section_payload.skills,
            certifications=section_payload.certifications,
        )
    raise ValueError(f"unsupported section label: {section_label}")


_SAFE_DIAGNOSTIC_TOKEN = re.compile(r"^[A-Za-z0-9_]+$")


def _safe_validation_loc(loc: object) -> str:
    if not isinstance(loc, (tuple, list)) or not loc:
        return "<root>"
    parts: list[str] = []
    for part in loc:
        if isinstance(part, int) and not isinstance(part, bool) and 0 <= part <= 999999:
            parts.append(str(part))
        elif isinstance(part, str) and len(part) <= 64 and _SAFE_DIAGNOSTIC_TOKEN.fullmatch(part):
            parts.append(part)
        else:
            parts.append("<field>")
    return ".".join(parts)[:256]


def _safe_validation_metadata(error: BaseException) -> tuple[str, str, int] | None:
    if not isinstance(error, ValidationError):
        return None
    details = error.errors()
    if not details:
        return "<root>", "validation_error", 0
    first = details[0]
    error_type = first.get("type")
    safe_type = (
        error_type
        if isinstance(error_type, str)
        and len(error_type) <= 64
        and _SAFE_DIAGNOSTIC_TOKEN.fullmatch(error_type)
        else "<type>"
    )
    return _safe_validation_loc(first.get("loc")), safe_type, len(details)


def _has_exception_name(error: BaseException, names: tuple[str, ...]) -> bool:
    return any(base.__name__ in names for base in type(error).__mro__)


def _safe_upstream_status(error: BaseException) -> int | None:
    possible_statuses = (
        getattr(error, "status_code", None),
        getattr(getattr(error, "response", None), "status_code", None),
    )
    for status in possible_statuses:
        if isinstance(status, int) and not isinstance(status, bool) and 100 <= status <= 599:
            return status
    return None


def _classify_provider_failure(error: BaseException, *, provider_call: bool) -> str:
    if isinstance(error, (TimeoutError, httpx.TimeoutException)) or _has_exception_name(
        error, ("APITimeoutError",)
    ):
        return _PROVIDER_FAILURE_TIMEOUT
    if isinstance(error, (ConnectionError, httpx.RequestError)) or _has_exception_name(
        error, ("APIConnectionError",)
    ):
        return _PROVIDER_FAILURE_CONNECTION
    if isinstance(error, httpx.HTTPStatusError) or _has_exception_name(
        error, ("APIStatusError",)
    ):
        return _PROVIDER_FAILURE_UPSTREAM
    if isinstance(error, (json.JSONDecodeError, ValidationError)) or _has_exception_name(
        error,
        (
            "APIResponseValidationError",
            "LengthFinishReasonError",
            "ContentFilterFinishReasonError",
        ),
    ):
        return _PROVIDER_FAILURE_STRUCTURED_OUTPUT
    if provider_call and isinstance(error, (ValueError, TypeError)):
        return _PROVIDER_FAILURE_STRUCTURED_OUTPUT
    if _has_exception_name(error, ("APIError", "OpenAIError")):
        return _PROVIDER_FAILURE_UPSTREAM
    return _PROVIDER_FAILURE_INTERNAL


class ResumeExtractionFailure(Exception):
    """Internal failure carrying only safe metadata for the upload boundary."""

    def __init__(
        self,
        error: BaseException,
        *,
        stage: str,
        elapsed_ms: float,
        total_llm_calls: int,
        provider_call: bool,
    ) -> None:
        self.failure_type = _classify_provider_failure(error, provider_call=provider_call)
        self.stage = stage
        self.exception_class = type(error).__name__
        self.upstream_status = _safe_upstream_status(error)
        validation_metadata = _safe_validation_metadata(error)
        self.validation_loc = validation_metadata[0] if validation_metadata else None
        self.validation_type = validation_metadata[1] if validation_metadata else None
        self.validation_error_count = validation_metadata[2] if validation_metadata else None
        self.elapsed_ms = elapsed_ms
        self.total_llm_calls = total_llm_calls
        super().__init__("resume extraction failure")


def _raise_resume_extraction_failure(
    error: BaseException,
    *,
    stage: str,
    elapsed_ms: float,
    total_llm_calls: int,
    provider_call: bool,
) -> NoReturn:
    raise ResumeExtractionFailure(
        error,
        stage=stage,
        elapsed_ms=elapsed_ms,
        total_llm_calls=total_llm_calls,
        provider_call=provider_call,
    ) from None


def _log_provider_failure(
    failure: ResumeExtractionFailure,
    *,
    section: str | None = None,
) -> None:
    logger.error(
        "provider_failure failure_type=%s stage=%s exception_class=%s upstream_status=%s "
        "elapsed_ms=%.2f total_llm_calls=%d",
        failure.failure_type,
        failure.stage,
        failure.exception_class,
        failure.upstream_status if failure.upstream_status is not None else "none",
        failure.elapsed_ms,
        failure.total_llm_calls,
    )
    if failure.validation_loc is not None:
        logger.error(
            "structured_output_validation stage=%s section=%s loc=%s type=%s error_count=%d",
            failure.stage,
            section or "none",
            failure.validation_loc,
            failure.validation_type or "<type>",
            failure.validation_error_count or 0,
        )


def _provider_failure_http_exception(failure: ResumeExtractionFailure) -> HTTPException:
    status_code, detail = _PROVIDER_FAILURE_RESPONSES[failure.failure_type]
    return HTTPException(status_code=status_code, detail=detail)


def get_openai_timeout_seconds() -> float:
    raw_value = os.getenv("OPENAI_TIMEOUT_SECONDS", "").strip()
    if not raw_value:
        return DEFAULT_OPENAI_TIMEOUT_SECONDS
    try:
        value = float(raw_value)
    except ValueError as error:
        raise ValueError("OPENAI_TIMEOUT_SECONDS must be a number") from error
    if not math.isfinite(value) or value <= 0 or value > MAX_OPENAI_TIMEOUT_SECONDS:
        raise ValueError(
            f"OPENAI_TIMEOUT_SECONDS must be greater than 0 and no more than {MAX_OPENAI_TIMEOUT_SECONDS:g}"
        )
    return value


def get_openai_max_retries() -> int:
    raw_value = os.getenv("OPENAI_MAX_RETRIES", "").strip()
    if not raw_value:
        return DEFAULT_OPENAI_MAX_RETRIES
    try:
        value = int(raw_value)
    except ValueError as error:
        raise ValueError("OPENAI_MAX_RETRIES must be an integer") from error
    if value < 0 or value > MAX_OPENAI_RETRIES:
        raise ValueError(f"OPENAI_MAX_RETRIES must be between 0 and {MAX_OPENAI_RETRIES}")
    return value


def _is_deepseek_endpoint(base_url: str | None) -> bool:
    if not base_url:
        return False
    hostname = urlparse(base_url).hostname
    normalized_hostname = hostname.casefold() if hostname else ""
    return normalized_hostname == "deepseek.com" or normalized_hostname.endswith(".deepseek.com")


class ResumeProvider(Protocol):
    def extract(self, evidence_text: str) -> ResumeExtractionResult: ...

    def extract_section(
        self,
        section_text: str,
        section_label: str,
    ) -> LeanResumeExtractionResult | ResumeExtractionResult: ...


class OpenAIResumeProvider:
    def __init__(self) -> None:
        from openai import OpenAI

        client_options: dict[str, object] = {
            "api_key": os.environ["OPENAI_API_KEY"],
            "timeout": get_openai_timeout_seconds(),
            "max_retries": get_openai_max_retries(),
        }
        base_url = os.getenv("OPENAI_BASE_URL")
        if base_url:
            client_options["base_url"] = base_url
        self.client = OpenAI(**client_options)
        self.model = os.getenv("OPENAI_MODEL") or os.getenv("OPENAI_RESUME_MODEL") or "gpt-4o-mini"
        self._is_deepseek = _is_deepseek_endpoint(base_url)

    def _create_json_completion(
        self,
        *,
        system_prompt: str,
        user_content: str,
    ) -> object:
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
    def _parse_json_completion(
        response: object,
        model_type: type[_MODEL_T],
        *,
        ignored_keys: frozenset[str] = frozenset(),
    ) -> _MODEL_T:
        content = response.choices[0].message.content
        if not isinstance(content, str) or not content.strip():
            raise ValueError("OpenAI returned no JSON resume result")
        data = json.loads(content)
        if ignored_keys and isinstance(data, dict):
            data = {
                key: value
                for key, value in data.items()
                if key not in ignored_keys
            }
        return model_type.model_validate(data)

    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        response = self._create_json_completion(
            system_prompt=(
                "Extract explicit resume facts only. Use section headings as structural evidence and map "
                "教育背景 to education, 主修课程 to education.relevant_courses, 实习经历 to "
                "INTERNSHIP, 工作经历 to WORK, 校园经历 to CAMPUS, 项目经历 to PROJECT, 专业技能 "
                "to skills, and explicit 证书/资格证书/language credentials to certifications. "
                "For each experience, return source_section as the exact heading when present and "
                "experience_type as WORK, INTERNSHIP, CAMPUS, PROJECT, or OTHER. Keep generic language "
                "ability in skills, and keep explicit credentials such as CET-4/CET-6, IELTS, TOEFL, "
                "JLPT, or 普通话二级甲等 in certifications. Never invent a credential. "
                "For every evidence_text, copy a VERBATIM contiguous excerpt from the resume. Do not "
                "paraphrase, summarize, translate, or rewrite evidence_text. Preserve evidence_text "
                "exactly as shown. Keep evidence excerpts concise but include the relevant course text "
                "when returning relevant_courses. For each item, set raw_value to the exact extracted "
                "value before any canonicalization; canonical_value is reserved for deterministic aliases "
                "such as PPT to PowerPoint. Keep explicit credential score text in score, never infer "
                "pass/fail status, and do not emit unsupported facts. Do not infer skill proficiency; "
                "proficiency must remain null."
                + _FULL_JSON_OBJECT_CONTRACT
            ),
            user_content=evidence_text,
        )
        return self._parse_json_completion(response, ResumeExtractionResult)

    def extract_section(
        self,
        section_text: str,
        section_label: str,
    ) -> LeanResumeExtractionResult:
        payload_model = _SECTION_PAYLOAD_MODELS.get(section_label)
        if payload_model is None:
            raise ValueError(f"unsupported section label: {section_label}")
        source_surface_instruction = (
            "Every returned string that represents a source fact must be copied VERBATIM from the supplied "
            "section (source surface). Do not paraphrase, summarize, translate, or rewrite source values; never "
            "canonicalize, improve wording, or infer synonyms. Application code owns canonicalization, evidence anchoring, offsets, and "
            "provenance."
        )
        if section_label in {"EDUCATION", "COURSES"}:
            system_prompt = (
                f"{source_surface_instruction} Extract only explicit semantic education facts from this single "
                "resume section. Return only "
                "education items: school as institution, degree, major as field_of_study, an explicit start/end "
                "date range as dates, and relevant_courses. The application owns evidence anchoring, raw_value, "
                "canonical aliases, offsets, and provenance, so do not return evidence_text, evidence offsets, "
                "raw_value, canonical_value, or source_section. The existing contract stores start and end "
                "together in dates; do not invent a missing boundary. Do not return skills, experiences, "
                "certifications, or career implications. Do not infer school, major, degree, dates, or courses."
                + _EDUCATION_JSON_OBJECT_CONTRACT
            )
        elif section_label == "EXPERIENCE":
            system_prompt = (
                f"{source_surface_instruction} Extract only explicit semantic experience facts from this single "
                "resume section. Return only "
                "experience items with title, organization, dates, description, and an experience_type when the "
                "section supports WORK, INTERNSHIP, PROJECT, or CAMPUS. The application owns evidence anchoring, "
                "raw_value, canonical aliases, offsets, and provenance; do not return evidence_text, evidence "
                "offsets, raw_value, canonical_value, or source_section. Do not use or invent information outside "
                "the supplied section. Read the exact heading and never use OTHER when it provides a supported "
                "classification."
                + _EXPERIENCE_JSON_OBJECT_CONTRACT
            )
        elif section_label == "CAMPUS":
            system_prompt = (
                f"{source_surface_instruction} Extract only explicit semantic campus-experience facts from this "
                "single resume section. Return "
                "only experience items with title, organization, dates, and description. The application owns "
                "evidence anchoring, raw_value, canonical aliases, offsets, provenance, and CAMPUS classification; "
                "do not return evidence_text, evidence offsets, raw_value, canonical_value, or source_section. "
                "Do not use or invent information outside the supplied section."
                + _CAMPUS_JSON_OBJECT_CONTRACT
            )
        else:
            section_contract = {
                "SKILLS": _SKILLS_JSON_OBJECT_CONTRACT,
                "CREDENTIALS": _CREDENTIALS_JSON_OBJECT_CONTRACT,
                "LANGUAGE": _LANGUAGE_JSON_OBJECT_CONTRACT,
            }.get(section_label, _LANGUAGE_JSON_OBJECT_CONTRACT)
            system_prompt = (
                f"{source_surface_instruction} Extract only explicit semantic facts from this single resume "
                f"section: {section_label}. "
                "Do not use or invent information outside the supplied section. Return semantic skill or "
                "credential values only. The application owns evidence anchoring, raw_value, canonical aliases, "
                "offsets, and provenance; do not return evidence_text, evidence offsets, raw_value, "
                "canonical_value, or source_section. Keep generic language ability in skills and explicit "
                "credentials in certifications. Do not infer credential pass/fail status."
                + section_contract
            )
        response = self._create_json_completion(
            system_prompt=system_prompt,
            user_content=section_text,
        )
        ignored_keys = _SECTION_IGNORED_PROVIDER_KEYS.get(section_label, frozenset())
        payload = self._parse_json_completion(
            response,
            payload_model,
            ignored_keys=frozenset(ignored_keys),
        )
        return _section_payload_to_lean_result(payload, section_label)


_resume_provider: ResumeProvider | None = None


def set_resume_provider(provider: ResumeProvider | None) -> None:
    global _resume_provider
    _resume_provider = provider


def extract_pdf_text(data: bytes) -> str:
    try:
        document = fitz.open(stream=data, filetype="pdf")
    except Exception as error:
        raise HTTPException(status_code=415, detail="The uploaded file is not a valid PDF") from error
    try:
        try:
            text = "\n".join(page.get_text() for page in document).strip()
        except Exception as error:
            raise HTTPException(status_code=422, detail="The PDF text could not be extracted") from error
    finally:
        document.close()
    if not text:
        raise HTTPException(status_code=422, detail="The PDF contains no extractable text")
    return text


def get_resume_provider() -> ResumeProvider:
    if _resume_provider is not None:
        return _resume_provider
    if not os.getenv("OPENAI_API_KEY"):
        raise HTTPException(status_code=503, detail="Resume extraction service is not configured")
    return OpenAIResumeProvider()


def get_allowed_frontend_origins() -> list[str]:
    configured_origins = [
        origin.strip().rstrip("/")
        for origin in os.getenv("FRONTEND_ORIGINS", "").split(",")
        if origin.strip()
    ]
    return list(dict.fromkeys([*LOCAL_FRONTEND_ORIGINS, *configured_origins]))


def _normalize_text_with_spans(text: str) -> tuple[str, list[tuple[int, int]]]:
    normalized_chars: list[str] = []
    source_spans: list[tuple[int, int]] = []
    pending_space: tuple[int, int] | None = None

    def hangul_jamo_type(character: str) -> str | None:
        normalized_character = unicodedata.normalize("NFKC", character)
        if len(normalized_character) != 1:
            return None
        codepoint = ord(normalized_character)
        if 0x1100 <= codepoint <= 0x115F or 0xA960 <= codepoint <= 0xA97C:
            return "L"
        if 0x1160 <= codepoint <= 0x11A7 or 0xD7B0 <= codepoint <= 0xD7C6:
            return "V"
        if 0x11A8 <= codepoint <= 0x11FF or 0xD7CB <= codepoint <= 0xD7FB:
            return "T"
        return None

    def continues_hangul_composition(start: int, index: int) -> bool:
        first_type = hangul_jamo_type(text[start])
        current_type = hangul_jamo_type(text[index])
        if first_type != "L" or current_type is None:
            return False
        segment_length = index - start
        if segment_length == 1:
            return current_type == "V"
        if segment_length == 2:
            return hangul_jamo_type(text[start + 1]) == "V" and current_type == "T"
        return False

    def emit(normalized_text: str, source_span: tuple[int, int]) -> None:
        nonlocal pending_space
        for normalized_character in normalized_text:
            if normalized_character.isspace() or normalized_character == "\u00a0":
                pending_space = (
                    (pending_space[0], source_span[1]) if pending_space else source_span
                )
                continue
            if pending_space is not None and normalized_chars:
                normalized_chars.append(" ")
                source_spans.append(pending_space)
            pending_space = None
            normalized_chars.append(normalized_character)
            source_spans.append(source_span)

    segment_start: int | None = None
    for index, character in enumerate(text):
        if character.isspace() or character == "\u00a0":
            if segment_start is not None:
                segment = text[segment_start:index]
                emit(unicodedata.normalize("NFKC", segment).casefold(), (segment_start, index))
                segment_start = None
            emit(" ", (index, index + 1))
        elif segment_start is None:
            segment_start = index
        elif unicodedata.combining(character) == 0 and not (
            segment_start is not None and continues_hangul_composition(segment_start, index)
        ):
            segment = text[segment_start:index]
            emit(unicodedata.normalize("NFKC", segment).casefold(), (segment_start, index))
            segment_start = index

    if segment_start is not None:
        segment = text[segment_start:]
        emit(unicodedata.normalize("NFKC", segment).casefold(), (segment_start, len(text)))

    return "".join(normalized_chars), source_spans


def normalize_text(text: str) -> str:
    return _normalize_text_with_spans(text)[0]


@dataclass(frozen=True)
class EvidenceAnchor:
    text: str
    start: int
    end: int


def anchor_fact_to_source_span(source_text: str, fact_value: str, candidate_evidence: str) -> EvidenceAnchor | None:
    normalized_source, source_spans = _normalize_text_with_spans(source_text)
    normalized_fact = normalize_text(fact_value)
    normalized_candidate = normalize_text(candidate_evidence)
    if not normalized_fact:
        return None

    match_start = -1
    match_text = ""
    if normalized_fact in normalized_candidate:
        match_start = normalized_source.find(normalized_candidate)
        match_text = normalized_candidate
    if match_start == -1:
        match_start = normalized_source.find(normalized_fact)
        match_text = normalized_fact
    if match_start == -1:
        return None

    match_end = match_start + len(match_text) - 1
    source_start = source_spans[match_start][0]
    source_end = source_spans[match_end][1]
    return EvidenceAnchor(text=source_text[source_start:source_end], start=source_start, end=source_end)


def anchor_fact_to_source(source_text: str, fact_value: str, candidate_evidence: str) -> str | None:
    anchor = anchor_fact_to_source_span(source_text, fact_value, candidate_evidence)
    return anchor.text if anchor else None


def _anchor_source_value_span(
    source_text: str,
    fact_value: str,
    candidate_evidence: str,
) -> EvidenceAnchor | None:
    """Anchor one source value, rather than the whole candidate evidence span."""

    normalized_source, source_spans = _normalize_text_with_spans(source_text)
    normalized_value = normalize_text(fact_value)
    normalized_candidate = normalize_text(candidate_evidence)
    if (
        not normalized_value
        or not normalized_candidate
        or normalized_value not in normalized_candidate
        or not source_spans
    ):
        return None

    candidate_start = normalized_source.find(normalized_candidate)
    if candidate_start >= 0:
        candidate_end = candidate_start + len(normalized_candidate)
        match_start = normalized_source.find(normalized_value, candidate_start, candidate_end)
    else:
        match_start = normalized_source.find(normalized_value)
    if match_start < 0:
        return None

    match_end = match_start + len(normalized_value) - 1
    source_start = source_spans[match_start][0]
    source_end = source_spans[match_end][1]
    return EvidenceAnchor(text=source_text[source_start:source_end], start=source_start, end=source_end)


def get_primary_fact_value(fact: Education | Skill | Experience | Certification) -> str:
    if isinstance(fact, Education):
        return fact.institution
    if isinstance(fact, Skill):
        return fact.name
    if isinstance(fact, Experience):
        return fact.title
    return fact.name


def _fact_aliases(fact: Education | Skill | Experience | Certification) -> list[str]:
    if isinstance(fact, Skill):
        aliases = {
            "powerpoint": ["PowerPoint", "PPT", "Microsoft PowerPoint"],
            "word": ["Word", "Microsoft Word"],
            "excel": ["Excel", "Microsoft Excel"],
            "english": ["English", "英语"],
            "普通话": ["普通话", "Mandarin"],
        }
        return aliases.get(normalize_text(fact.name), [fact.name])
    if isinstance(fact, Certification):
        aliases = {
            "cet-4": ["CET-4", "CET 4", "大学英语四级"],
            "cet-6": ["CET-6", "CET 6", "大学英语六级"],
            "普通话二级甲等": ["普通话二级甲等"],
            "ielts": ["IELTS", "雅思"],
            "toefl": ["TOEFL", "托福"],
            "jlpt": ["JLPT"],
        }
        return aliases.get(normalize_text(fact.name), [fact.name])
    return [get_primary_fact_value(fact)]


@dataclass(frozen=True)
class ValidationWarning:
    code: str
    category: str
    index: int
    reason: str
    raw_value: str
    evidence_text: str
    source: str = "initial"


@dataclass(frozen=True)
class GroundingResult:
    result: ResumeExtractionResult
    warnings: list[ValidationWarning]
    total_items: int
    accepted_items: int


@dataclass(frozen=True)
class ProcessedResumeResult:
    result: ResumeExtractionResult
    warnings: list[ValidationWarning]
    completeness_warnings: list[str]
    total_llm_calls: int = 0


_EXPLICIT_OFFICE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z0-9_])Microsoft[ \t]+PowerPoint(?![A-Za-z0-9_])", re.IGNORECASE), "PowerPoint"),
    (re.compile(r"(?<![A-Za-z0-9_])Microsoft[ \t]+Word(?![A-Za-z0-9_])", re.IGNORECASE), "Word"),
    (re.compile(r"(?<![A-Za-z0-9_])Microsoft[ \t]+Excel(?![A-Za-z0-9_])", re.IGNORECASE), "Excel"),
    (re.compile(r"(?<![A-Za-z0-9_])PowerPoint(?![A-Za-z0-9_])", re.IGNORECASE), "PowerPoint"),
    (re.compile(r"(?<![A-Za-z0-9_])Word(?![A-Za-z0-9_])", re.IGNORECASE), "Word"),
    (re.compile(r"(?<![A-Za-z0-9_])Excel(?![A-Za-z0-9_])", re.IGNORECASE), "Excel"),
    (re.compile(r"(?<![A-Za-z0-9_])PPT(?![A-Za-z0-9_])", re.IGNORECASE), "PowerPoint"),
)
_EXPLICIT_CREDENTIAL_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z0-9_])CET[- ]?4(?![A-Za-z0-9_])", re.IGNORECASE), "CET-4"),
    (re.compile(r"(?<![A-Za-z0-9_])CET[- ]?6(?![A-Za-z0-9_])", re.IGNORECASE), "CET-6"),
    (re.compile(r"大学英语四级"), "CET-4"),
    (re.compile(r"大学英语六级"), "CET-6"),
    (re.compile(r"普通话二级甲等"), "普通话二级甲等"),
    (re.compile(r"(?<![A-Za-z0-9_])IELTS(?![A-Za-z0-9_])", re.IGNORECASE), "IELTS"),
    (re.compile(r"雅思"), "IELTS"),
    (re.compile(r"(?<![A-Za-z0-9_])TOEFL(?![A-Za-z0-9_])", re.IGNORECASE), "TOEFL"),
    (re.compile(r"托福"), "TOEFL"),
    (re.compile(r"(?<![A-Za-z0-9_])JLPT(?![A-Za-z0-9_])", re.IGNORECASE), "JLPT"),
)
_EXPLICIT_LANGUAGE_PATTERNS: tuple[tuple[re.Pattern[str], str], ...] = (
    (re.compile(r"(?<![A-Za-z0-9_])English(?![A-Za-z0-9_])", re.IGNORECASE), "English"),
    (re.compile(r"英语"), "English"),
    (re.compile(r"(?<![A-Za-z0-9_])Mandarin(?![A-Za-z0-9_])", re.IGNORECASE), "普通话"),
    (re.compile(r"普通话"), "普通话"),
)
_EXPLICIT_SCORE_SUFFIX = re.compile(
    r"[\s:：()（）-]*(?:(?:score|成绩|分数)[\s:：-]*)?(\d{1,4}(?:\.\d+)?)",
    re.IGNORECASE,
)
_OFFICE_UMBRELLA_NAMES = {"办公软件", "办公技能"}
_INSTITUTION_CN_PATTERN = re.compile(
    r"(?<![\u4e00-\u9fffA-Za-z0-9·])"
    r"(?P<value>[\u4e00-\u9fffA-Za-z0-9·&.'-]{2,60}(?:职业技术学院|研究院|大学|学院|学校))"
)
_INSTITUTION_EN_PATTERN = re.compile(
    r"(?ix)\b(?P<value>"
    r"(?:(?:[A-Za-z0-9][A-Za-z0-9&.'()/-]*[ \t]+){0,8}?"
    r"(?:University|College|Institute|School)"
    r"(?:[ \t]+of[ \t]+[A-Za-z0-9][A-Za-z0-9&.'()/-]*(?:[ \t]+[A-Za-z0-9][A-Za-z0-9&.'()/-]*){0,6})?"
    r"))\b"
)
_INSTITUTION_CN_CONTEXT = (
    "毕业院校",
    "毕业学校",
    "毕业于",
    "就读于",
    "就读",
    "考入",
    "录取于",
    "入读",
    "主修于",
)
_INSTITUTION_EN_CONTEXT_PATTERN = re.compile(
    r"(?i)(?:graduated from|studied at|attended|enrolled at|at)[ \t]+"
)


def _section_match_candidates(
    source_text: str,
    sections: tuple[str, ...],
    patterns: tuple[tuple[re.Pattern[str], str], ...],
) -> list[tuple[int, int, str, str]]:
    candidates: list[tuple[int, int, str, str]] = []
    for section in detect_sections(source_text):
        if section.key not in sections:
            continue
        section_text = source_text[section.start : section.end]
        for pattern, canonical in patterns:
            for match in pattern.finditer(section_text):
                start = section.start + match.start()
                end = section.start + match.end()
                candidates.append((start, end, canonical, source_text[start:end]))
    return candidates


# Courses are an Education subfield, not a standalone public Profile item;
# keeping COURSE sections out of the targeted plan avoids inventing an institution.
_SECTION_TARGET_KEYS = {"EDUCATION", "EXPERIENCE", "CAMPUS", "SKILLS", "CREDENTIALS", "LANGUAGE"}
_SECTION_NOISE_PATTERN = re.compile(r"[\s,，、/／|;；+&:：()（）\[\]【】{}<>《》.。·-]+")
_SECTION_SCORE_PATTERN = re.compile(r"\d{1,4}(?:\.\d+)?")


def _section_has_semantic_content(section: ResumeSection, *, content: str | None = None) -> bool:
    content = section.content if content is None else content
    if section.key == "SKILLS":
        for pattern, _ in _EXPLICIT_OFFICE_PATTERNS:
            content = pattern.sub(" ", content)
        content = content.replace("办公软件", " ").replace("办公技能", " ").replace("等", " ")
    elif section.key in {"CREDENTIALS", "LANGUAGE"}:
        for pattern, _ in _EXPLICIT_CREDENTIAL_PATTERNS:
            content = pattern.sub(" ", content)
        if section.key == "LANGUAGE":
            for pattern, _ in _EXPLICIT_LANGUAGE_PATTERNS:
                content = pattern.sub(" ", content)
        content = _SECTION_SCORE_PATTERN.sub(" ", content)
        content = re.sub(r"(?i)\bscore\b|成绩|分数", " ", content)
    return bool(_SECTION_NOISE_PATTERN.sub("", content))


def _deterministic_section_facts(
    section: ResumeSection,
    deterministic: ResumeExtractionResult,
) -> tuple[object, ...]:
    if section.key == "SKILLS":
        return tuple(deterministic.skills)
    if section.key == "CREDENTIALS":
        return tuple(deterministic.certifications)
    if section.key == "LANGUAGE":
        return (*deterministic.skills, *deterministic.certifications)
    return ()


def _uncovered_section_content(
    section: ResumeSection,
    deterministic: ResumeExtractionResult,
) -> str:
    remaining = normalize_text(section.content)
    for fact in _deterministic_section_facts(section, deterministic):
        evidence = normalize_text(getattr(fact, "evidence_text", ""))
        if evidence:
            remaining = remaining.replace(evidence, " ", 1)
    return remaining


def _section_requires_targeted_extraction(
    section: ResumeSection,
    deterministic: ResumeExtractionResult | None = None,
) -> bool:
    if section.key not in _SECTION_TARGET_KEYS:
        return False
    if section.key not in {"SKILLS", "CREDENTIALS", "LANGUAGE"}:
        return True
    if deterministic is None:
        return _section_has_semantic_content(section)
    return _section_has_semantic_content(
        section,
        content=_uncovered_section_content(section, deterministic),
    )


def build_section_extraction_plan(
    source_text: str,
    deterministic: ResumeExtractionResult,
) -> list[ResumeSection]:
    """Return non-empty sections that need one bounded semantic extraction."""

    priority = {"EDUCATION": 0, "EXPERIENCE": 1, "CAMPUS": 2}
    eligible = [
        (index, section)
        for index, section in enumerate(detect_sections(source_text))
        if _section_requires_targeted_extraction(section, deterministic)
    ]
    eligible.sort(key=lambda item: (priority.get(item[1].key, 3), item[0]))
    return [section for _, section in eligible[:MAX_LLM_CALLS_PER_RESUME]]


def _section_candidate_fact(fact: object, section: ResumeSection) -> object:
    updates: dict[str, object] = {
        "evidence_text": section.content,
        "evidence_start": None,
        "evidence_end": None,
        "raw_value": None,
        "canonical_value": None,
    }
    if isinstance(fact, Experience):
        updates["source_section"] = section.heading
        if section.key == "CAMPUS":
            updates["experience_type"] = ExperienceType.CAMPUS
    return fact.model_copy(update=updates)


def _lean_result_to_section_result(
    raw_result: LeanResumeExtractionResult | ResumeExtractionResult | object,
    section: ResumeSection,
) -> ResumeExtractionResult:
    if isinstance(raw_result, ResumeExtractionResult):
        return ResumeExtractionResult.model_validate(
            {
                "education": [_section_candidate_fact(item, section) for item in raw_result.education],
                "skills": [_section_candidate_fact(item, section) for item in raw_result.skills],
                "experiences": [_section_candidate_fact(item, section) for item in raw_result.experiences],
                "certifications": [_section_candidate_fact(item, section) for item in raw_result.certifications],
            }
        )

    lean_result = LeanResumeExtractionResult.model_validate(raw_result)
    return ResumeExtractionResult(
        education=[
            Education(
                institution=item.institution,
                degree=item.degree,
                field_of_study=item.field_of_study,
                dates=item.dates,
                relevant_courses=item.relevant_courses,
                evidence_text=section.content,
            )
            for item in lean_result.education
            if item.institution
        ],
        skills=[Skill(name=item.name, evidence_text=section.content) for item in lean_result.skills],
        experiences=[
            Experience(
                title=item.title,
                organization=item.organization,
                dates=item.dates,
                description=item.description,
                experience_type=item.experience_type or ExperienceType.OTHER,
                source_section=section.heading,
                evidence_text=section.content,
            )
            for item in lean_result.experiences
        ],
        certifications=[
            Certification(
                name=item.name,
                issuer=item.issuer,
                date=item.date,
                score=item.score,
                evidence_text=section.content,
            )
            for item in lean_result.certifications
        ],
    )


def _localize_section_evidence(
    result: ResumeExtractionResult,
    source_text: str,
    section: ResumeSection,
) -> ResumeExtractionResult:
    del source_text
    updates: dict[str, list[object]] = {}
    for collection, facts in _fact_groups(result):
        updates[collection] = [
            fact.model_copy(
                update={
                    "evidence_text": section.content,
                    "evidence_start": None,
                    "evidence_end": None,
                }
            )
            for fact in facts
        ]
    return result.model_copy(
        update={
            "education": updates["education"],
            "skills": updates["skill"],
            "experiences": updates["experience"],
            "certifications": updates["certification"],
        }
    )


def _select_non_overlapping_candidates(
    candidates: list[tuple[int, int, str, str]],
) -> list[tuple[int, int, str, str]]:
    selected: list[tuple[int, int, str, str]] = []
    seen_canonical: set[str] = set()
    for candidate in sorted(candidates, key=lambda item: (item[0], -(item[1] - item[0]))):
        start, end, canonical, _ = candidate
        if canonical in seen_canonical:
            continue
        if any(start < selected_end and end > selected_start for selected_start, selected_end, _, _ in selected):
            continue
        selected.append(candidate)
        seen_canonical.add(canonical)
    return sorted(selected, key=lambda item: item[0])


def _trim_institution_context(raw_value: str) -> tuple[str, int]:
    value = raw_value.lstrip()
    relative_start = len(raw_value) - len(value)
    for context in _INSTITUTION_CN_CONTEXT:
        context_index = value.rfind(context)
        if context_index < 0:
            continue
        suffix = value[context_index + len(context) :]
        trimmed_suffix = suffix.lstrip()
        relative_start += context_index + len(context) + len(suffix) - len(trimmed_suffix)
        value = trimmed_suffix
        break
    else:
        context_match = _INSTITUTION_EN_CONTEXT_PATTERN.search(value)
        if context_match is not None:
            suffix = value[context_match.end() :]
            trimmed_suffix = suffix.lstrip()
            relative_start += context_match.end() + len(suffix) - len(trimmed_suffix)
            value = trimmed_suffix

    leading_punctuation = value.lstrip(" \t,:：;；-—/|([{（【《\"'")
    relative_start += len(value) - len(leading_punctuation)
    value = leading_punctuation
    connector_match = re.match(r"(?i)(?:and|or|&)\s+", value)
    if connector_match is not None:
        relative_start += connector_match.end()
        value = value[connector_match.end() :]
    return value.rstrip(" \t,:：;；-—/|)]}）】》\"'"), relative_start


def _is_high_confidence_institution(value: str) -> bool:
    normalized = normalize_text(value)
    if not normalized:
        return False
    if _INSTITUTION_CN_PATTERN.search(value) is not None:
        return True
    suffix_match = re.search(r"(?i)\b(?:University|College|Institute|School)\b", value)
    if suffix_match is None:
        return False
    prefix = value[: suffix_match.start()].strip()
    suffix = value[suffix_match.end() :].strip()
    return bool((prefix and prefix.casefold() != "of") or re.match(r"(?i)^of\b", suffix))


def _explicit_institution_candidates(
    source_text: str,
    section: ResumeSection,
) -> list[EvidenceAnchor]:
    section_source = source_text[section.start : section.end]
    candidates: dict[str, EvidenceAnchor] = {}
    for pattern in (_INSTITUTION_CN_PATTERN, _INSTITUTION_EN_PATTERN):
        for match in pattern.finditer(section_source):
            raw_value = match.group("value")
            value, relative_start = _trim_institution_context(raw_value)
            if not _is_high_confidence_institution(value):
                continue
            start = section.start + match.start("value") + relative_start
            end = start + len(value)
            candidate = EvidenceAnchor(text=source_text[start:end], start=start, end=end)
            candidates.setdefault(normalize_text(candidate.text), candidate)
    return sorted(candidates.values(), key=lambda candidate: candidate.start)


def _recover_explicit_office_skills(source_text: str) -> list[Skill]:
    candidates = _select_non_overlapping_candidates(
        _section_match_candidates(source_text, ("SKILLS",), _EXPLICIT_OFFICE_PATTERNS)
    )
    return [
        Skill(
            name=canonical,
            raw_value=raw_value,
            canonical_value=canonical,
            evidence_text=raw_value,
            evidence_start=start,
            evidence_end=end,
        )
        for start, end, canonical, raw_value in candidates
    ]


def _recover_explicit_credentials(source_text: str) -> list[Certification]:
    candidates = _select_non_overlapping_candidates(
        _section_match_candidates(source_text, ("CREDENTIALS", "LANGUAGE"), _EXPLICIT_CREDENTIAL_PATTERNS)
    )
    recovered: list[Certification] = []
    for start, end, canonical, raw_value in candidates:
        score = None
        score_suffix = _EXPLICIT_SCORE_SUFFIX.match(source_text, end)
        if score_suffix is not None:
            end = score_suffix.end()
            raw_value = source_text[start:end]
            score = score_suffix.group(1)
        recovered.append(
            Certification(
                name=canonical,
                score=score,
                raw_value=raw_value,
                canonical_value=canonical,
                evidence_text=raw_value,
                evidence_start=start,
                evidence_end=end,
            )
        )
    return recovered


def _recover_explicit_language_skills(source_text: str) -> list[Skill]:
    candidates = _select_non_overlapping_candidates(
        _section_match_candidates(source_text, ("LANGUAGE",), _EXPLICIT_LANGUAGE_PATTERNS)
    )
    return [
        Skill(
            name=canonical,
            raw_value=raw_value,
            canonical_value=canonical,
            evidence_text=raw_value,
            evidence_start=start,
            evidence_end=end,
        )
        for start, end, canonical, raw_value in candidates
    ]


def recover_explicit_facts(result: ResumeExtractionResult, source_text: str) -> ResumeExtractionResult:
    recovered_office = _recover_explicit_office_skills(source_text)
    recovered_credentials = _recover_explicit_credentials(source_text)
    recovered_language = _recover_explicit_language_skills(source_text)

    skills = list(result.skills)
    if recovered_office:
        recovered_by_name = {skill.name.casefold(): skill for skill in recovered_office}
        skills = [
            skill
            for skill in skills
            if skill.name.casefold() not in recovered_by_name
            and skill.name.casefold() not in {name.casefold() for name in _OFFICE_UMBRELLA_NAMES}
        ]
        skills.extend(recovered_office)
    if recovered_language:
        recovered_by_name = {skill.name.casefold(): skill for skill in recovered_language}
        skills = [skill for skill in skills if skill.name.casefold() not in recovered_by_name]
        skills.extend(recovered_language)

    certifications = list(result.certifications)
    for recovered in recovered_credentials:
        existing_index = next(
            (index for index, certification in enumerate(certifications) if certification.name.casefold() == recovered.name.casefold()),
            None,
        )
        if existing_index is None:
            certifications.append(recovered)
            continue
        existing = certifications[existing_index]
        certifications[existing_index] = existing.model_copy(
            update={
                "raw_value": recovered.raw_value,
                "canonical_value": recovered.canonical_value,
                "evidence_text": recovered.evidence_text,
                "evidence_start": recovered.evidence_start,
                "evidence_end": recovered.evidence_end,
                "score": recovered.score if recovered.score is not None else existing.score,
            }
        )

    return result.model_copy(update={"skills": skills, "certifications": certifications})


def _fact_groups(result: ResumeExtractionResult) -> tuple[tuple[str, list[object]], ...]:
    return (
        ("education", result.education),
        ("skill", result.skills),
        ("experience", result.experiences),
        ("certification", result.certifications),
    )


def _warning_reason(source_text: str, evidence_text: str) -> str:
    return "evidence_not_in_source" if normalize_text(evidence_text) not in normalize_text(source_text) else "fact_not_in_evidence"


def _raise_grounding_warning(warning: ValidationWarning) -> None:
    raise HTTPException(
        status_code=502,
        detail=f"Resume evidence validation failed: {warning.category}[{warning.index}]: {warning.reason}",
    )


def _ground_optional_fact_fields(
    fact: Education | Experience | Certification,
    category: str,
    index: int,
    anchor: EvidenceAnchor,
    source: str,
    *,
    field_source_text: str | None = None,
    field_candidate_evidence: str | None = None,
) -> tuple[object, list[ValidationWarning], list[EvidenceAnchor]]:
    field_names = {
        "education": ("degree", "field_of_study", "dates"),
        "experience": ("organization", "dates", "description"),
        "certification": ("issuer", "date", "score", "status"),
    }.get(category, ())
    updates: dict[str, object] = {}
    warnings: list[ValidationWarning] = []
    field_source = field_source_text or anchor.text
    field_evidence = field_candidate_evidence or anchor.text
    field_anchors: list[EvidenceAnchor] = []
    for field_name in field_names:
        field_value = getattr(fact, field_name)
        if field_value is None:
            continue
        field_anchor = _anchor_source_value_span(field_source, field_value, field_evidence)
        if field_anchor is None:
            warnings.append(
                ValidationWarning(
                    code="UNSUPPORTED_FACT",
                    category=f"{category}.{field_name}",
                    index=index,
                    reason="field_not_in_evidence",
                    raw_value=field_value,
                    evidence_text=anchor.text,
                    source=source,
                )
            )
            updates[field_name] = None
            continue
        updates[field_name] = field_anchor.text
        field_anchors.append(field_anchor)

    if isinstance(fact, Education):
        grounded_courses: list[str] = []
        for course_index, course in enumerate(fact.relevant_courses):
            course_anchor = _anchor_source_value_span(field_source, course, field_evidence)
            if course_anchor is None:
                warnings.append(
                    ValidationWarning(
                        code="UNSUPPORTED_FACT",
                        category="education.relevant_courses",
                        index=course_index,
                        reason="course_not_in_evidence",
                        raw_value=course,
                        evidence_text=anchor.text,
                        source=source,
                    )
                )
                continue
            grounded_courses.append(course_anchor.text)
            field_anchors.append(course_anchor)
        updates["relevant_courses"] = grounded_courses

    grounded_fact = fact.model_copy(update=updates) if updates else fact
    return grounded_fact, warnings, field_anchors


def ground_resume_extraction(
    result: ResumeExtractionResult,
    source_text: str,
    *,
    source: str = "initial",
    strict: bool = False,
    field_source_text: str | None = None,
) -> GroundingResult:
    warnings: list[ValidationWarning] = []
    fact_groups = _fact_groups(result)
    collection_for_category = {
        "education": "education",
        "skill": "skills",
        "experience": "experiences",
        "certification": "certifications",
    }
    accepted: dict[str, list[object]] = {
        collection: [] for collection in collection_for_category.values()
    }
    total_items = sum(len(facts) for _, facts in fact_groups)
    for category, facts in fact_groups:
        for index, fact in enumerate(facts):
            raw_value = fact.raw_value or get_primary_fact_value(fact)
            values = [raw_value] if fact.raw_value else [raw_value, *_fact_aliases(fact)]
            anchored_value: str | None = None
            anchor: EvidenceAnchor | None = None
            for value in dict.fromkeys(values):
                candidate = (
                    _anchor_source_value_span(source_text, value, fact.evidence_text)
                    if field_source_text is not None
                    else anchor_fact_to_source_span(source_text, value, fact.evidence_text)
                )
                if candidate is not None:
                    anchored_value = value
                    anchor = candidate
                    break
            if anchor is None:
                warning_reason = _warning_reason(source_text, fact.evidence_text)
                if field_source_text is not None and not any(
                    normalize_text(value) in normalize_text(source_text)
                    for value in dict.fromkeys(values)
                    if normalize_text(value)
                ):
                    warning_reason = "evidence_not_in_source"
                warning = ValidationWarning(
                    code="UNSUPPORTED_FACT",
                    category=category,
                    index=index,
                    reason=warning_reason,
                    raw_value=raw_value,
                    evidence_text=fact.evidence_text,
                    source=source,
                )
                if strict:
                    _raise_grounding_warning(warning)
                warnings.append(warning)
                continue
            if isinstance(fact, Experience) and fact.source_section:
                if normalize_text(fact.source_section) not in normalize_text(source_text):
                    warning = ValidationWarning(
                        code="UNSUPPORTED_FACT",
                        category=category,
                        index=index,
                        reason="section_not_in_source",
                        raw_value=fact.source_section,
                        evidence_text=fact.evidence_text,
                        source=source,
                    )
                    if strict:
                        _raise_grounding_warning(warning)
                    warnings.append(warning)
                    continue
            grounded_fact = fact.model_copy(
                update={
                    "raw_value": values[0] if fact.raw_value else anchored_value,
                    "evidence_text": anchor.text,
                    "evidence_start": anchor.start,
                    "evidence_end": anchor.end,
                }
            )
            evidence_anchors = [anchor]
            if isinstance(fact, (Education, Experience, Certification)):
                grounded_fact, optional_warnings, optional_anchors = _ground_optional_fact_fields(
                    grounded_fact,
                    category,
                    index,
                    anchor,
                    source,
                    field_source_text=field_source_text,
                    field_candidate_evidence=(
                        fact.evidence_text if field_source_text is not None else None
                    ),
                )
                warnings.extend(optional_warnings)
                evidence_anchors.extend(optional_anchors)
            evidence_start = min(item.start for item in evidence_anchors)
            evidence_end = max(item.end for item in evidence_anchors)
            grounded_fact = grounded_fact.model_copy(
                update={
                    "evidence_text": source_text[evidence_start:evidence_end],
                    "evidence_start": evidence_start,
                    "evidence_end": evidence_end,
                }
            )
            accepted[collection_for_category[category]].append(grounded_fact)
    return GroundingResult(
        result=ResumeExtractionResult.model_validate(accepted),
        warnings=warnings,
        total_items=total_items,
        accepted_items=sum(len(items) for items in accepted.values()),
    )


def _raise_if_unreliable(grounded: GroundingResult) -> None:
    if grounded.total_items and grounded.accepted_items == 0:
        if grounded.warnings:
            _raise_grounding_warning(grounded.warnings[0])
        raise HTTPException(status_code=502, detail="Resume evidence validation failed: no_grounded_facts")


def _section_diagnostic_warning(
    source_text: str,
    warning: str,
    *,
    code: str,
    reason: str,
    source: str,
) -> ValidationWarning:
    category = warning.split(":", 1)[-1]
    section = section_for_warning(source_text, warning)
    return ValidationWarning(
        code=code,
        category=category,
        index=0,
        reason=reason,
        raw_value=section.heading if section is not None else category,
        evidence_text=section.text if section is not None else "",
        source=source,
    )


def _education_diagnostic_warning(code: str, reason: str, *, source: str) -> ValidationWarning:
    return ValidationWarning(
        code=code,
        category="education",
        index=0,
        reason=reason,
        raw_value="EDUCATION",
        evidence_text="",
        source=source,
    )


def _institution_diagnostic_warning(code: str, reason: str, *, source: str) -> ValidationWarning:
    return ValidationWarning(
        code=code,
        category="education.institution",
        index=0,
        reason=reason,
        raw_value="INSTITUTION",
        evidence_text="",
        source=source,
    )


def _repair_budget_diagnostic_warning() -> ValidationWarning:
    return ValidationWarning(
        code="SECTION_REPAIR_BUDGET_EXHAUSTED",
        category="resume",
        index=0,
        reason="maximum_llm_call_budget_reached",
        raw_value="REPAIR_BUDGET",
        evidence_text="",
        source="budget",
    )


def _log_resume_timing(timing_ms: dict[str, float | int], total_llm_calls: int) -> None:
    values = {field_name: timing_ms.get(field_name, 0.0) for field_name in _TIMING_FIELDS}
    logger.info(
        "resume_timing pdf_extract_ms=%.2f initial_llm_ms=%.2f education_llm_ms=%.2f "
        "experience_llm_ms=%.2f campus_llm_ms=%.2f other_llm_ms=%.2f education_repair_1_ms=%.2f "
        "education_repair_2_ms=%.2f other_section_repair_ms=%.2f grounding_normalization_ms=%.2f "
        "db_persist_ms=%.2f total_resume_ms=%.2f total_llm_calls=%d",
        values["pdf_extract_ms"],
        values["initial_llm_ms"],
        values["education_llm_ms"],
        values["experience_llm_ms"],
        values["campus_llm_ms"],
        values["other_llm_ms"],
        values["education_repair_1_ms"],
        values["education_repair_2_ms"],
        values["other_section_repair_ms"],
        values["grounding_normalization_ms"],
        values["db_persist_ms"],
        values["total_resume_ms"],
        total_llm_calls,
    )


def _anchor_recoverable_education_value(
    section_source: str,
    value: str,
    evidence_text: str,
) -> EvidenceAnchor | None:
    normalized_value = normalize_text(value)
    normalized_evidence = normalize_text(evidence_text)
    if (
        not normalized_value
        or not normalized_evidence
        or normalized_value not in normalized_evidence
        or normalized_evidence not in normalize_text(section_source)
    ):
        return None
    return anchor_fact_to_source_span(section_source, value, evidence_text)


def _recovered_education_item(
    result: ResumeExtractionResult,
    source_text: str,
    section: ResumeSection,
    candidate: EvidenceAnchor,
) -> Education:
    section_source = source_text[section.start : section.end]
    optional_fields: dict[str, str | None] = {
        "degree": None,
        "field_of_study": None,
        "dates": None,
    }
    courses: list[str] = []
    course_keys: set[str] = set()
    evidence_spans: list[EvidenceAnchor] = [
        EvidenceAnchor(
            text=candidate.text,
            start=candidate.start - section.start,
            end=candidate.end - section.start,
        )
    ]
    for item in result.education:
        for field_name in optional_fields:
            value = getattr(item, field_name)
            if value is None or optional_fields[field_name] is not None:
                continue
            anchor = _anchor_recoverable_education_value(section_source, value, item.evidence_text)
            if anchor is None:
                continue
            optional_fields[field_name] = value
            evidence_spans.append(anchor)
        for course in item.relevant_courses:
            course_key = normalize_text(course)
            if not course_key or course_key in course_keys:
                continue
            anchor = _anchor_recoverable_education_value(section_source, course, item.evidence_text)
            if anchor is None:
                continue
            course_keys.add(course_key)
            courses.append(course)
            evidence_spans.append(anchor)

    absolute_spans = [
        EvidenceAnchor(
            text=anchor.text,
            start=section.start + anchor.start,
            end=section.start + anchor.end,
        )
        for anchor in evidence_spans
    ]
    evidence_start = min(anchor.start for anchor in absolute_spans)
    evidence_end = max(anchor.end for anchor in absolute_spans)
    return Education(
        institution=candidate.text,
        degree=optional_fields["degree"],
        field_of_study=optional_fields["field_of_study"],
        dates=optional_fields["dates"],
        relevant_courses=courses,
        raw_value=candidate.text,
        evidence_text=source_text[evidence_start:evidence_end],
        evidence_start=evidence_start,
        evidence_end=evidence_end,
    )


def _recover_explicit_education_institution(
    result: ResumeExtractionResult,
    normalized: ResumeExtractionResult,
    source_text: str,
    section: ResumeSection,
) -> tuple[ResumeExtractionResult, list[ValidationWarning]]:
    diagnostics = [
        _institution_diagnostic_warning(
            "INSTITUTION_NOT_EXTRACTED" if not result.education else "INSTITUTION_NOT_GROUNDED",
            "model_omitted_institution" if not result.education else "institution_failed_grounding",
            source="initial",
        )
    ]
    candidates = _explicit_institution_candidates(source_text, section)
    if not candidates:
        return normalized, diagnostics
    if len(candidates) > 1:
        diagnostics.append(
            _institution_diagnostic_warning(
                "INSTITUTION_RECOVERY_AMBIGUOUS",
                "multiple_explicit_candidates",
                source="recovery",
            )
        )
        return normalized, diagnostics
    recovered = _recovered_education_item(result, source_text, section, candidates[0])
    diagnostics.append(
        _institution_diagnostic_warning(
            "INSTITUTION_RECOVERED",
            "single_explicit_candidate",
            source="recovery",
        )
    )
    return normalized.model_copy(update={"education": [recovered]}), diagnostics


def _rebase_section_evidence(
    result: ResumeExtractionResult,
    source_text: str,
    section: ResumeSection,
) -> ResumeExtractionResult:
    """Map evidence grounded in the original section slice to resume offsets."""

    section_source = source_text[section.start : section.end]
    updates: dict[str, list[object]] = {}
    for collection, facts in _fact_groups(result):
        rebased_facts: list[object] = []
        for fact in facts:
            relative_start = fact.evidence_start
            relative_end = fact.evidence_end
            if (
                isinstance(relative_start, int)
                and isinstance(relative_end, int)
                and 0 <= relative_start < relative_end <= len(section_source)
                and section_source[relative_start:relative_end] == fact.evidence_text
            ):
                rebased_facts.append(
                    fact.model_copy(
                        update={
                            "evidence_text": source_text[
                                section.start + relative_start : section.start + relative_end
                            ],
                            "evidence_start": section.start + relative_start,
                            "evidence_end": section.start + relative_end,
                        }
                    )
                )
                continue
            raw_value = fact.raw_value or get_primary_fact_value(fact)
            anchor = _anchor_source_value_span(section_source, raw_value, fact.evidence_text)
            if anchor is None:
                rebased_facts.append(
                    fact.model_copy(update={"evidence_start": None, "evidence_end": None})
                )
                continue
            rebased_facts.append(
                fact.model_copy(
                    update={
                        "evidence_text": anchor.text,
                        "evidence_start": section.start + anchor.start,
                        "evidence_end": section.start + anchor.end,
                    }
                )
            )
        updates[collection] = rebased_facts
    return result.model_copy(
        update={
            "education": updates["education"],
            "skills": updates["skill"],
            "experiences": updates["experience"],
            "certifications": updates["certification"],
        }
    )


def _merge_repair(
    base: ResumeExtractionResult,
    repair: ResumeExtractionResult,
    section_label: str,
    section_heading: str,
    *,
    source_text: str | None = None,
) -> ResumeExtractionResult:
    allowed = {
        "EDUCATION": {"education"},
        "CAMPUS": {"experiences"},
        "EXPERIENCE": {"experiences"},
        "SKILLS": {"skills"},
        "COURSES": {"education"},
        "CREDENTIALS": {"certifications"},
        "LANGUAGE": {"skills", "certifications"},
    }.get(section_label, set())
    updates: dict[str, list[object]] = {}
    for collection in ("education", "skills", "experiences", "certifications"):
        if collection not in allowed:
            updates[collection] = list(getattr(base, collection))
            continue
        repair_items = list(getattr(repair, collection))
        if section_label == "CAMPUS" and collection == "experiences":
            repair_items = [
                item.model_copy(update={"source_section": section_heading, "experience_type": ExperienceType.CAMPUS})
                for item in repair_items
            ]
        updates[collection] = [*getattr(base, collection), *repair_items]

    merged = base.model_copy(update=updates)
    merged.education = _dedupe_education(merged.education, source_text=source_text)
    merged.experiences = _dedupe_experiences(merged.experiences)
    return merged


def _education_evidence_metadata(
    existing: Education,
    incoming: Education,
    source_text: str | None,
) -> dict[str, str | int | None]:
    if (
        source_text is not None
        and existing.evidence_start is not None
        and existing.evidence_end is not None
        and incoming.evidence_start is not None
        and incoming.evidence_end is not None
    ):
        evidence_start = min(existing.evidence_start, incoming.evidence_start)
        evidence_end = max(existing.evidence_end, incoming.evidence_end)
        if 0 <= evidence_start < evidence_end <= len(source_text):
            return {
                "evidence_text": source_text[evidence_start:evidence_end],
                "evidence_start": evidence_start,
                "evidence_end": evidence_end,
            }
    return {
        "evidence_text": incoming.evidence_text,
        "evidence_start": incoming.evidence_start,
        "evidence_end": incoming.evidence_end,
    }


def _dedupe_education(
    items: list[Education],
    *,
    source_text: str | None = None,
) -> list[Education]:
    by_institution: dict[str, Education] = {}
    for item in items:
        key = item.institution.casefold()
        existing = by_institution.get(key)
        if existing is None:
            by_institution[key] = item
        else:
            updates: dict[str, object] = {}
            for field_name in ("degree", "field_of_study", "dates"):
                existing_value = getattr(existing, field_name)
                incoming_value = getattr(item, field_name)
                if existing_value is None and incoming_value is not None:
                    updates[field_name] = incoming_value
            merged_courses = list(dict.fromkeys([*existing.relevant_courses, *item.relevant_courses]))
            if merged_courses != existing.relevant_courses:
                updates["relevant_courses"] = merged_courses
            if updates:
                updates.update(_education_evidence_metadata(existing, item, source_text))
            by_institution[key] = existing.model_copy(
                update=updates
            )
    return list(by_institution.values())


def _experience_records_match(existing: Experience, incoming: Experience) -> bool:
    if (
        normalize_text(existing.title) != normalize_text(incoming.title)
        or existing.experience_type != incoming.experience_type
    ):
        return False
    for field_name in ("organization", "dates", "description"):
        existing_value = getattr(existing, field_name)
        incoming_value = getattr(incoming, field_name)
        if existing_value and incoming_value and normalize_text(existing_value) != normalize_text(incoming_value):
            return False
    if (
        existing.evidence_start is not None
        and existing.evidence_end is not None
        and incoming.evidence_start is not None
        and incoming.evidence_end is not None
        and (
            existing.evidence_end <= incoming.evidence_start
            or incoming.evidence_end <= existing.evidence_start
        )
    ):
        return False
    return True


def _merge_experience_record(existing: Experience, incoming: Experience) -> Experience:
    updates: dict[str, object] = {}
    for field_name in ("organization", "dates", "description", "source_section"):
        if getattr(existing, field_name) is None and getattr(incoming, field_name) is not None:
            updates[field_name] = getattr(incoming, field_name)
    if existing.evidence_start is None and incoming.evidence_start is not None:
        updates.update(
            {
                "evidence_text": incoming.evidence_text,
                "evidence_start": incoming.evidence_start,
                "evidence_end": incoming.evidence_end,
            }
        )
    return existing.model_copy(update=updates) if updates else existing


def _dedupe_experiences(items: list[Experience]) -> list[Experience]:
    deduped: list[Experience] = []
    for item in items:
        matching_index = next(
            (
                index
                for index, existing in enumerate(deduped)
                if _experience_records_match(existing, item)
            ),
            None,
        )
        if matching_index is None:
            deduped.append(item)
            continue
        deduped[matching_index] = _merge_experience_record(deduped[matching_index], item)
    return deduped


def _experience_repair_stage(section_key: str, attempt: int) -> str:
    if section_key == "EDUCATION":
        return f"education_repair_{attempt}"
    if section_key == "EXPERIENCE":
        return "experience_repair"
    if section_key == "CAMPUS":
        return "campus_repair"
    return "other_section_repair"


def process_resume_extraction(
    result: ResumeExtractionResult,
    source_text: str,
    *,
    provider: ResumeProvider | None = None,
    allow_repair: bool = True,
    initial_llm_calls: int = 1,
    timing_ms: dict[str, float | int] | None = None,
    grounded_result: GroundingResult | None = None,
) -> ProcessedResumeResult:
    if initial_llm_calls < 0:
        raise ValueError("initial_llm_calls must not be negative")
    if initial_llm_calls > MAX_LLM_CALLS_PER_RESUME:
        raise ValueError(f"initial_llm_calls must not exceed {MAX_LLM_CALLS_PER_RESUME}")
    repair_calls = 0
    if timing_ms is not None:
        timing_ms["total_llm_calls"] = initial_llm_calls

    grounding_started = time.perf_counter()
    try:
        grounded = (
            grounded_result
            if grounded_result is not None
            else ground_resume_extraction(result, source_text)
        )
        normalized_after_normalization = normalize_resume_extraction(grounded.result)
        warnings = list(grounded.warnings)
        if grounded.result.education and not normalized_after_normalization.education:
            warnings.append(
                _education_diagnostic_warning(
                    "EDUCATION_DROPPED_DURING_NORMALIZATION",
                    "education_missing_after_normalization",
                    source="initial",
                )
            )
        normalized = recover_explicit_facts(normalized_after_normalization, source_text)
        missing = completeness_warnings(normalized, source_text)
        education_section = next((section for section in detect_sections(source_text) if section.key == "EDUCATION"), None)
        if education_section is not None and not normalized.education:
            warnings.append(
                _education_diagnostic_warning(
                    "EDUCATION_FIRST_PASS_EMPTY",
                    "first_pass_no_grounded_education",
                    source="initial",
                )
            )
            normalized, institution_diagnostics = _recover_explicit_education_institution(
                result,
                normalized,
                source_text,
                education_section,
            )
            warnings.extend(institution_diagnostics)
            missing = completeness_warnings(normalized, source_text)
    except ResumeExtractionFailure:
        raise
    except Exception as error:
        grounding_elapsed = (time.perf_counter() - grounding_started) * 1000
        if timing_ms is not None:
            timing_ms["grounding_normalization_ms"] = grounding_elapsed
        _raise_resume_extraction_failure(
            error,
            stage="grounding_normalization",
            elapsed_ms=grounding_elapsed,
            total_llm_calls=initial_llm_calls,
            provider_call=False,
        )
    if timing_ms is not None:
        timing_ms["grounding_normalization_ms"] = (
            time.perf_counter() - grounding_started
        ) * 1000

    # This budget counts application-level extraction operations. The SDK's
    # transport retries are separately bounded by OPENAI_MAX_RETRIES.
    max_repair_calls = min(
        MAX_SECTION_REPAIR_CALLS_PER_RESUME,
        max(0, MAX_LLM_CALLS_PER_RESUME - initial_llm_calls),
    )
    if allow_repair and missing and provider is not None and hasattr(provider, "extract_section"):
        repair_attempts: dict[str, int] = {}
        for warning in list(missing):
            section_key = warning.split(":", 1)[-1]
            max_attempts = 2 if section_key == "EDUCATION" else 1
            while (
                warning in missing
                and repair_attempts.get(section_key, 0) < max_attempts
                and repair_calls < max_repair_calls
            ):
                repair_attempts[section_key] = repair_attempts.get(section_key, 0) + 1
                section = section_for_warning(source_text, warning)
                if section is None:
                    if section_key == "EDUCATION":
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_SECTION_NOT_DETECTED",
                                "section_not_detected_during_repair",
                                source="completeness",
                            )
                        )
                    else:
                        warnings.append(
                            _section_diagnostic_warning(
                                source_text,
                                warning,
                                code="SECTION_DETECTION_FAILED",
                                reason="section_not_detected",
                                source="completeness",
                            )
                        )
                    break
                repair_calls += 1
                repair_stage = _experience_repair_stage(
                    section_key,
                    repair_attempts[section_key],
                )
                repair_started = time.perf_counter()
                try:
                    repair_raw = provider.extract_section(section.text, section.key)
                except ResumeExtractionFailure:
                    raise
                except Exception as error:
                    _raise_resume_extraction_failure(
                        error,
                        stage=repair_stage,
                        elapsed_ms=(time.perf_counter() - repair_started) * 1000,
                        total_llm_calls=initial_llm_calls + repair_calls,
                        provider_call=True,
                    )
                finally:
                    repair_elapsed = (time.perf_counter() - repair_started) * 1000
                    if timing_ms is not None:
                        if section_key == "EDUCATION":
                            timing_key = f"education_repair_{repair_attempts[section_key]}_ms"
                            timing_ms[timing_key] = repair_elapsed
                        else:
                            timing_ms["other_section_repair_ms"] = (
                                float(timing_ms.get("other_section_repair_ms", 0.0))
                                + repair_elapsed
                            )
                        timing_ms["total_llm_calls"] = initial_llm_calls + repair_calls

                try:
                    repair_raw = _localize_section_evidence(
                        _lean_result_to_section_result(repair_raw, section),
                        source_text,
                        section,
                    )
                except Exception as error:
                    _raise_resume_extraction_failure(
                        error,
                        stage=repair_stage,
                        elapsed_ms=(time.perf_counter() - repair_started) * 1000,
                        total_llm_calls=initial_llm_calls + repair_calls,
                        provider_call=True,
                    )

                if section_key == "EDUCATION" and not repair_raw.education:
                    warnings.append(
                        _education_diagnostic_warning(
                            "EDUCATION_REPAIR_EMPTY",
                            "targeted_repair_returned_no_education",
                            source="repair",
                        )
                    )
                normalization_started = time.perf_counter()
                try:
                    repair_grounded = ground_resume_extraction(
                        repair_raw,
                        source_text[section.start : section.end],
                        source="repair",
                        field_source_text=source_text[section.start : section.end],
                    )
                    warnings.extend(repair_grounded.warnings)
                    if (
                        section_key == "EDUCATION"
                        and repair_raw.education
                        and not repair_grounded.result.education
                    ):
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_REPAIR_UNGROUNDED",
                                "targeted_repair_had_no_grounded_education",
                                source="repair",
                            )
                        )
                    repair_result = _rebase_section_evidence(repair_grounded.result, source_text, section)
                    merged = _merge_repair(
                        normalized,
                        repair_result,
                        section.key,
                        section.heading,
                        source_text=source_text,
                    )
                    if (
                        section_key == "EDUCATION"
                        and repair_result.education
                        and not merged.education
                    ):
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_DROPPED_DURING_MERGE",
                                "education_missing_after_repair_merge",
                                source="repair",
                            )
                        )
                    normalized_after_merge = normalize_resume_extraction(merged)
                    if (
                        section_key == "EDUCATION"
                        and merged.education
                        and not normalized_after_merge.education
                    ):
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_DROPPED_DURING_NORMALIZATION",
                                "education_missing_after_normalization",
                                source="repair",
                            )
                        )
                    normalized = recover_explicit_facts(normalized_after_merge, source_text)
                    missing = completeness_warnings(normalized, source_text)
                except ResumeExtractionFailure:
                    raise
                except Exception as error:
                    _raise_resume_extraction_failure(
                        error,
                        stage="grounding_normalization",
                        elapsed_ms=(time.perf_counter() - normalization_started) * 1000,
                        total_llm_calls=initial_llm_calls + repair_calls,
                        provider_call=False,
                    )
                finally:
                    if timing_ms is not None:
                        timing_ms["grounding_normalization_ms"] = (
                            float(timing_ms.get("grounding_normalization_ms", 0.0))
                            + (time.perf_counter() - normalization_started) * 1000
                        )

        if repair_calls >= max_repair_calls and missing:
            warnings.append(_repair_budget_diagnostic_warning())

    for warning in missing:
        category = warning.split(":", 1)[-1]
        if category == "EDUCATION":
            if not any(item.code == "EDUCATION_EXTRACTION_INCOMPLETE" for item in warnings):
                warnings.append(
                    _education_diagnostic_warning(
                        "EDUCATION_EXTRACTION_INCOMPLETE",
                        "recognized_section_remains_unresolved",
                        source="completeness",
                    )
                )
            continue
        if any(
            item.category == category
            and item.code in {"SECTION_CONTENT_MISSING", "SECTION_REPAIR_FAILED", "SECTION_DETECTION_FAILED"}
            for item in warnings
        ):
            continue
        warnings.append(
            _section_diagnostic_warning(
                source_text,
                warning,
                code="SECTION_CONTENT_MISSING",
                reason="targeted_repair_incomplete",
                source="completeness",
            )
        )
    if sum(len(facts) for _, facts in _fact_groups(normalized)) == 0:
        _raise_if_unreliable(grounded)
        raise HTTPException(status_code=502, detail="Resume evidence validation failed: no_grounded_facts")
    if timing_ms is not None:
        timing_ms["total_llm_calls"] = initial_llm_calls + repair_calls
    return ProcessedResumeResult(
        result=normalized,
        warnings=warnings,
        completeness_warnings=missing,
        total_llm_calls=initial_llm_calls + repair_calls,
    )


def _section_extraction_stage(section_key: str) -> str:
    return {
        "EDUCATION": "education_extraction",
        "EXPERIENCE": "experience_extraction",
        "CAMPUS": "campus_extraction",
    }.get(section_key, "other_extraction")


def _section_timing_key(section_key: str) -> str:
    return {
        "EDUCATION": "education_llm_ms",
        "EXPERIENCE": "experience_llm_ms",
        "CAMPUS": "campus_llm_ms",
    }.get(section_key, "other_llm_ms")


def _section_provider_failure_warning(
    section: ResumeSection,
    failure: ResumeExtractionFailure,
) -> ValidationWarning:
    return ValidationWarning(
        code="SECTION_PROVIDER_FAILURE",
        category=section.key,
        index=0,
        reason=failure.failure_type,
        raw_value=section.heading,
        evidence_text="",
        source="targeted",
    )


def _section_budget_warning(section: ResumeSection) -> ValidationWarning:
    return ValidationWarning(
        code="SECTION_EXTRACTION_BUDGET_EXHAUSTED",
        category=section.key,
        index=0,
        reason="maximum_llm_call_budget_reached",
        raw_value=section.heading,
        evidence_text="",
        source="budget",
    )


def _section_fact_counts(result: ResumeExtractionResult) -> dict[str, int]:
    return {
        "education": len(result.education),
        "skills": len(result.skills),
        "experiences": len(result.experiences),
        "certifications": len(result.certifications),
    }


def _log_targeted_section_diagnostic(
    section: ResumeSection,
    extracted: ResumeExtractionResult,
    grounded: GroundingResult,
) -> None:
    extracted_counts = _section_fact_counts(extracted)
    grounded_counts = _section_fact_counts(grounded.result)
    logger.info(
        "targeted_section section_key=%s extracted_education=%d extracted_skills=%d "
        "extracted_experiences=%d extracted_certifications=%d grounded_education=%d "
        "grounded_skills=%d grounded_experiences=%d grounded_certifications=%d warnings=%d",
        section.key,
        extracted_counts["education"],
        extracted_counts["skills"],
        extracted_counts["experiences"],
        extracted_counts["certifications"],
        grounded_counts["education"],
        grounded_counts["skills"],
        grounded_counts["experiences"],
        grounded_counts["certifications"],
        len(grounded.warnings),
    )


def _ground_targeted_section(
    raw_result: LeanResumeExtractionResult | ResumeExtractionResult | object,
    source_text: str,
    section: ResumeSection,
) -> GroundingResult:
    section_result = _localize_section_evidence(
        _lean_result_to_section_result(raw_result, section),
        source_text,
        section,
    )
    section_source = source_text[section.start : section.end]
    grounded = ground_resume_extraction(
        section_result,
        section_source,
        source="targeted",
        field_source_text=section_source,
    )
    return GroundingResult(
        result=_rebase_section_evidence(grounded.result, source_text, section),
        warnings=grounded.warnings,
        total_items=grounded.total_items,
        accepted_items=grounded.accepted_items,
    )


def _run_full_resume_fallback(
    provider: ResumeProvider,
    source_text: str,
    *,
    timing_ms: dict[str, float | int] | None,
) -> ProcessedResumeResult:
    started = time.perf_counter()
    try:
        raw_result = provider.extract(source_text)
    except ResumeExtractionFailure:
        raise
    except Exception as error:
        _raise_resume_extraction_failure(
            error,
            stage="initial_extraction",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            total_llm_calls=1,
            provider_call=True,
        )
    finally:
        if timing_ms is not None:
            timing_ms["initial_llm_ms"] = (time.perf_counter() - started) * 1000

    try:
        result = ResumeExtractionResult.model_validate(raw_result)
    except Exception as error:
        _raise_resume_extraction_failure(
            error,
            stage="initial_extraction",
            elapsed_ms=(time.perf_counter() - started) * 1000,
            total_llm_calls=1,
            provider_call=True,
        )
    return process_resume_extraction(
        result,
        source_text,
        allow_repair=False,
        initial_llm_calls=1,
        timing_ms=timing_ms,
    )


def extract_section_first_resume(
    provider: ResumeProvider,
    source_text: str,
    *,
    timing_ms: dict[str, float | int] | None = None,
) -> ProcessedResumeResult:
    """Extract a resume from isolated sections before using the legacy fallback."""

    if timing_ms is not None:
        for field_name in _TIMING_FIELDS:
            if field_name != "total_llm_calls":
                timing_ms.setdefault(field_name, 0.0)
    deterministic = recover_explicit_facts(ResumeExtractionResult(), source_text)
    sections = detect_sections(source_text)
    detected_keys = ",".join(section.key for section in sections) or "none"
    logger.info(
        "resume_sections detected=%s detected_count=%d",
        detected_keys,
        len(sections),
    )
    if not sections:
        logger.info("resume_plan planned=none planned_count=0")
        return _run_full_resume_fallback(provider, source_text, timing_ms=timing_ms)

    plan = build_section_extraction_plan(source_text, deterministic)
    planned_keys = ",".join(section.key for section in plan) or "none"
    logger.info(
        "resume_plan planned=%s planned_count=%d",
        planned_keys,
        len(plan),
    )
    merged = deterministic
    warnings: list[ValidationWarning] = []
    planned_sections = {(section.key, section.start, section.end) for section in plan}
    targeted_results: dict[tuple[str, int, int], ResumeExtractionResult] = {}
    for section in sections:
        if _section_requires_targeted_extraction(section, deterministic) and (
            section.key,
            section.start,
            section.end,
        ) not in planned_sections:
            warnings.append(_section_budget_warning(section))
    total_llm_calls = 0

    for section in plan:
        total_llm_calls += 1
        started = time.perf_counter()
        provider_elapsed = 0.0
        try:
            provider_started = time.perf_counter()
            try:
                extract_section = getattr(provider, "extract_section", None)
                if callable(extract_section):
                    raw_result = extract_section(section.text, section.key)
                else:
                    raw_result = provider.extract(section.text)
            finally:
                provider_elapsed = (time.perf_counter() - provider_started) * 1000
            section_result = _lean_result_to_section_result(raw_result, section)
            targeted = _ground_targeted_section(section_result, source_text, section)
            _log_targeted_section_diagnostic(section, section_result, targeted)
            warnings.extend(targeted.warnings)
            targeted_results[(section.key, section.start, section.end)] = targeted.result
        except ResumeExtractionFailure as failure:
            _log_provider_failure(failure, section=section.key)
            warnings.append(_section_provider_failure_warning(section, failure))
        except Exception as error:
            failure = ResumeExtractionFailure(
                error,
                stage=_section_extraction_stage(section.key),
                elapsed_ms=(time.perf_counter() - started) * 1000,
                total_llm_calls=total_llm_calls,
                provider_call=True,
            )
            _log_provider_failure(failure, section=section.key)
            warnings.append(_section_provider_failure_warning(section, failure))
        finally:
            if timing_ms is not None:
                timing_key = _section_timing_key(section.key)
                timing_ms[timing_key] = (
                    float(timing_ms.get(timing_key, 0.0))
                    + provider_elapsed
                )
                timing_ms["total_llm_calls"] = total_llm_calls

    # Calls are prioritized for recall, but merge in source order so the public
    # profile remains stable relative to the resume layout.
    for section in sections:
        targeted = targeted_results.get((section.key, section.start, section.end))
        if targeted is None:
            continue
        merged = _merge_repair(
            merged,
            targeted,
            section.key,
            section.heading,
            source_text=source_text,
        )

    processed = process_resume_extraction(
        merged,
        source_text,
        allow_repair=False,
        initial_llm_calls=total_llm_calls,
        timing_ms=timing_ms,
        grounded_result=GroundingResult(
            result=merged,
            warnings=[],
            total_items=sum(len(facts) for _, facts in _fact_groups(merged)),
            accepted_items=sum(len(facts) for _, facts in _fact_groups(merged)),
        ),
    )
    return ProcessedResumeResult(
        result=processed.result,
        warnings=[*warnings, *processed.warnings],
        completeness_warnings=processed.completeness_warnings,
        total_llm_calls=processed.total_llm_calls,
    )


def validate_evidence_trace(result: ResumeExtractionResult, source_text: str) -> ResumeExtractionResult:
    grounded = ground_resume_extraction(result, source_text, strict=True).result
    # Preserve the historical identity behavior for already-grounded callers while
    # still returning deterministic source spans for newly processed extractions.
    if grounded == result:
        return result
    if all(
        fact.raw_value is None
        and fact.canonical_value is None
        and fact.evidence_start is None
        and fact.evidence_end is None
        for _, facts in _fact_groups(result)
        for fact in facts
    ) and all(
        normalize_text(fact.evidence_text) == normalize_text(grounded_fact.evidence_text)
        for (_, facts), (_, grounded_facts) in zip(_fact_groups(result), _fact_groups(grounded))
        for fact, grounded_fact in zip(facts, grounded_facts)
    ):
        return result
    return grounded


app = FastAPI(title="AI Career OS API", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_allowed_frontend_origins(),
    allow_methods=["POST", "GET", "PUT"],
    allow_headers=["*"],
)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.post("/api/v1/resumes", response_model=ProfileRead)
async def upload_resume(
    file: UploadFile = File(...),
    db: Session = Depends(get_db),
) -> ProfileRead:
    resume_started = time.perf_counter()
    timing_ms: dict[str, float | int] = {}
    initial_llm_calls = 0
    try:
        if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
        data = await file.read(MAX_RESUME_BYTES + 1)
        if len(data) > MAX_RESUME_BYTES:
            raise HTTPException(status_code=413, detail="Resume PDF exceeds the 10 MB limit")
        pdf_started = time.perf_counter()
        text = extract_pdf_text(data)
        timing_ms["pdf_extract_ms"] = (time.perf_counter() - pdf_started) * 1000
        try:
            provider_started = time.perf_counter()
            try:
                provider = get_resume_provider()
            except HTTPException:
                raise
            except Exception as error:
                _raise_resume_extraction_failure(
                    error,
                    stage="initial_extraction",
                    elapsed_ms=(time.perf_counter() - provider_started) * 1000,
                    total_llm_calls=initial_llm_calls,
                    provider_call=False,
                )
            processed = extract_section_first_resume(provider, text, timing_ms=timing_ms)
            for warning in processed.warnings:
                logger.warning(
                    "Resume extraction warning code=%s category=%s index=%d reason=%s source=%s",
                    warning.code,
                    warning.category,
                    warning.index,
                    warning.reason,
                    warning.source,
                )
        except HTTPException:
            raise
        except ResumeExtractionFailure as failure:
            _log_provider_failure(failure)
            raise _provider_failure_http_exception(failure) from None
        except Exception as error:
            failure = ResumeExtractionFailure(
                error,
                stage="grounding_normalization",
                elapsed_ms=(time.perf_counter() - resume_started) * 1000,
                total_llm_calls=initial_llm_calls,
                provider_call=False,
            )
            _log_provider_failure(failure)
            raise _provider_failure_http_exception(failure) from None
        db_started = time.perf_counter()
        try:
            profile = create_draft_profile(db, processed.result)
            return get_profile(db, profile.id)
        except SQLAlchemyError as error:
            db.rollback()
            raise HTTPException(status_code=503, detail="Profile persistence failed") from error
        finally:
            timing_ms["db_persist_ms"] = (time.perf_counter() - db_started) * 1000
    finally:
        for field_name in _TIMING_FIELDS:
            if field_name == "total_llm_calls":
                continue
            timing_ms.setdefault(field_name, 0.0)
        total_llm_calls = int(timing_ms.get("total_llm_calls", initial_llm_calls))
        timing_ms["total_llm_calls"] = total_llm_calls
        timing_ms["total_resume_ms"] = (time.perf_counter() - resume_started) * 1000
        _log_resume_timing(timing_ms, total_llm_calls)


@app.get("/api/v1/profiles/{profile_id}", response_model=ProfileRead)
def read_profile(profile_id: UUID, db: Session = Depends(get_db)) -> ProfileRead:
    return get_profile(db, profile_id)


@app.put("/api/v1/profiles/{profile_id}", response_model=ProfileRead)
def save_profile(
    profile_id: UUID,
    payload: ProfileUpdate,
    db: Session = Depends(get_db),
) -> ProfileRead:
    return update_draft_profile(db, profile_id, payload)


@app.post("/api/v1/profiles/{profile_id}/confirm", response_model=ProfileRead)
def confirm_saved_profile(profile_id: UUID, db: Session = Depends(get_db)) -> ProfileRead:
    return confirm_profile(db, profile_id)
