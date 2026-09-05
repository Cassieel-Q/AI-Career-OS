from __future__ import annotations

import logging
import math
import os
import re
import time
import unicodedata
from dataclasses import dataclass
from typing import Protocol
from uuid import UUID

import fitz
from fastapi import Depends, FastAPI, File, HTTPException, UploadFile
from fastapi.middleware.cors import CORSMiddleware
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
from app.resume_schemas import Certification, Education, Experience, ExperienceType, ResumeExtractionResult, Skill
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
    "education_repair_1_ms",
    "education_repair_2_ms",
    "other_section_repair_ms",
    "grounding_normalization_ms",
    "db_persist_ms",
    "total_resume_ms",
    "total_llm_calls",
)
logger = logging.getLogger(__name__)


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


class ResumeProvider(Protocol):
    def extract(self, evidence_text: str) -> ResumeExtractionResult: ...

    def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult: ...


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

    def extract(self, evidence_text: str) -> ResumeExtractionResult:
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
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
                    ),
                },
                {"role": "user", "content": evidence_text},
            ],
            response_format=ResumeExtractionResult,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no structured resume result")
        return ResumeExtractionResult.model_validate(parsed)

    def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult:
        if section_label == "EDUCATION":
            system_prompt = (
                "Extract only explicit education facts from this single resume section. Return only education "
                "items: school as institution, degree, major as field_of_study, an explicit start/end date range "
                "as dates, and relevant_courses. The existing contract stores start and end together in dates; "
                "do not invent a missing boundary. Do not return skills, experiences, certifications, or career "
                "implications. Do not infer school, major, degree, dates, or courses. For every returned item, "
                "preserve raw_value and copy a VERBATIM contiguous excerpt into evidence_text."
            )
        else:
            system_prompt = (
                f"Extract explicit facts from this single resume section only: {section_label}. "
                "Do not use or invent information outside the supplied section. For every raw fact, "
                "preserve the exact source value in raw_value and copy a VERBATIM contiguous excerpt "
                "into evidence_text. Keep generic language ability in skills and explicit credentials "
                "in certifications. Do not infer credential pass/fail status."
            )
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": system_prompt,
                },
                {"role": "user", "content": section_text},
            ],
            response_format=ResumeExtractionResult,
        )
        parsed = response.choices[0].message.parsed
        if parsed is None:
            raise ValueError("OpenAI returned no structured section result")
        return ResumeExtractionResult.model_validate(parsed)


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


def recover_explicit_facts(result: ResumeExtractionResult, source_text: str) -> ResumeExtractionResult:
    recovered_office = _recover_explicit_office_skills(source_text)
    recovered_credentials = _recover_explicit_credentials(source_text)

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


def ground_resume_extraction(
    result: ResumeExtractionResult,
    source_text: str,
    *,
    source: str = "initial",
    strict: bool = False,
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
            anchor = next(
                (
                    candidate
                    for value in dict.fromkeys(values)
                    if (candidate := anchor_fact_to_source_span(source_text, value, fact.evidence_text)) is not None
                ),
                None,
            )
            if anchor is None:
                warning = ValidationWarning(
                    code="UNSUPPORTED_FACT",
                    category=category,
                    index=index,
                    reason=_warning_reason(source_text, fact.evidence_text),
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
                    "raw_value": values[0] if fact.raw_value else next(
                        value for value in dict.fromkeys(values)
                        if anchor_fact_to_source_span(source_text, value, fact.evidence_text) is not None
                    ),
                    "evidence_text": anchor.text,
                    "evidence_start": anchor.start,
                    "evidence_end": anchor.end,
                }
            )
            if isinstance(fact, Education):
                education_updates: dict[str, str | None] = {}
                for field_name in ("degree", "field_of_study", "dates"):
                    field_value = getattr(fact, field_name)
                    if field_value is None:
                        continue
                    normalized_field = normalize_text(field_value)
                    if not normalized_field or normalized_field not in normalize_text(anchor.text):
                        warnings.append(
                            ValidationWarning(
                                code="UNSUPPORTED_FACT",
                                category=f"education.{field_name}",
                                index=index,
                                reason="field_not_in_evidence",
                                raw_value=field_value,
                                evidence_text=fact.evidence_text,
                                source=source,
                            )
                        )
                        education_updates[field_name] = None
                if education_updates:
                    grounded_fact = grounded_fact.model_copy(update=education_updates)
                grounded_courses: list[str] = []
                for course_index, course in enumerate(fact.relevant_courses):
                    if anchor_fact_to_source(source_text, course, anchor.text) is None:
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
                    else:
                        grounded_courses.append(course)
                grounded_fact = grounded_fact.model_copy(update={"relevant_courses": grounded_courses})
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
        "resume_timing pdf_extract_ms=%.2f initial_llm_ms=%.2f education_repair_1_ms=%.2f "
        "education_repair_2_ms=%.2f other_section_repair_ms=%.2f grounding_normalization_ms=%.2f "
        "db_persist_ms=%.2f total_resume_ms=%.2f total_llm_calls=%d",
        values["pdf_extract_ms"],
        values["initial_llm_ms"],
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
    """Map evidence grounded in reconstructed section text back to resume offsets."""

    section_source = source_text[section.start : section.end]
    updates: dict[str, list[object]] = {}
    for collection, facts in _fact_groups(result):
        rebased_facts: list[object] = []
        for fact in facts:
            raw_value = fact.raw_value or get_primary_fact_value(fact)
            anchor = anchor_fact_to_source_span(section_source, raw_value, fact.evidence_text)
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


def _dedupe_experiences(items: list[Experience]) -> list[Experience]:
    seen: set[tuple[str, ExperienceType]] = set()
    deduped: list[Experience] = []
    for item in items:
        key = (item.title.casefold(), item.experience_type)
        if key not in seen:
            seen.add(key)
            deduped.append(item)
    return deduped


def process_resume_extraction(
    result: ResumeExtractionResult,
    source_text: str,
    *,
    provider: ResumeProvider | None = None,
    allow_repair: bool = True,
    initial_llm_calls: int = 1,
    timing_ms: dict[str, float | int] | None = None,
) -> ProcessedResumeResult:
    if initial_llm_calls < 0:
        raise ValueError("initial_llm_calls must not be negative")
    if initial_llm_calls > MAX_LLM_CALLS_PER_RESUME:
        raise ValueError(f"initial_llm_calls must not exceed {MAX_LLM_CALLS_PER_RESUME}")
    repair_calls = 0
    if timing_ms is not None:
        timing_ms["total_llm_calls"] = initial_llm_calls

    grounding_started = time.perf_counter()
    grounded = ground_resume_extraction(result, source_text)
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
                try:
                    repair_calls += 1
                    repair_started = time.perf_counter()
                    try:
                        repair_raw = provider.extract_section(section.text, section.key)
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
                    if section_key == "EDUCATION" and not repair_raw.education:
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_REPAIR_EMPTY",
                                "targeted_repair_returned_no_education",
                                source="repair",
                            )
                        )
                    repair_grounded = ground_resume_extraction(
                        repair_raw,
                        section.text,
                        source="repair",
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
                    normalization_started = time.perf_counter()
                    try:
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
                    finally:
                        if timing_ms is not None:
                            timing_ms["grounding_normalization_ms"] = (
                                float(timing_ms.get("grounding_normalization_ms", 0.0))
                                + (time.perf_counter() - normalization_started) * 1000
                            )
                except Exception as error:
                    if section_key == "EDUCATION":
                        warnings.append(
                            _education_diagnostic_warning(
                                "EDUCATION_REPAIR_FAILED",
                                type(error).__name__,
                                source="repair",
                            )
                        )
                    else:
                        warnings.append(
                            ValidationWarning(
                                code="SECTION_REPAIR_FAILED",
                                category=section.key,
                                index=0,
                                reason=type(error).__name__,
                                raw_value=section.heading,
                                evidence_text=section.text,
                                source="repair",
                            )
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
            provider = get_resume_provider()
            initial_started = time.perf_counter()
            initial_llm_calls = 1
            try:
                extracted = provider.extract(text)
            finally:
                timing_ms["initial_llm_ms"] = (time.perf_counter() - initial_started) * 1000
            result = ResumeExtractionResult.model_validate(extracted)
            processed = process_resume_extraction(
                result,
                text,
                provider=provider,
                initial_llm_calls=initial_llm_calls,
                timing_ms=timing_ms,
            )
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
        except Exception as error:
            raise HTTPException(status_code=502, detail="Resume extraction provider failed") from error
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
