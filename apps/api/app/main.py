from __future__ import annotations

import logging
import os
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
from app.resume_sections import completeness_warnings, section_for_warning

MAX_RESUME_BYTES = 10 * 1024 * 1024
LOCAL_FRONTEND_ORIGINS = ["http://localhost:3000", "http://127.0.0.1:3000"]
logger = logging.getLogger(__name__)


class ResumeProvider(Protocol):
    def extract(self, evidence_text: str) -> ResumeExtractionResult: ...

    def extract_section(self, section_text: str, section_label: str) -> ResumeExtractionResult: ...


class OpenAIResumeProvider:
    def __init__(self) -> None:
        from openai import OpenAI

        client_options = {"api_key": os.environ["OPENAI_API_KEY"]}
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
        response = self.client.beta.chat.completions.parse(
            model=self.model,
            messages=[
                {
                    "role": "system",
                    "content": (
                        f"Extract explicit facts from this single resume section only: {section_label}. "
                        "Do not use or invent information outside the supplied section. For every raw fact, "
                        "preserve the exact source value in raw_value and copy a VERBATIM contiguous excerpt "
                        "into evidence_text. Keep generic language ability in skills and explicit credentials "
                        "in certifications. Do not infer credential pass/fail status."
                    ),
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
    rejected = grounded.total_items - grounded.accepted_items
    if grounded.accepted_items == 0 and grounded.warnings:
        _raise_grounding_warning(grounded.warnings[0])
    if grounded.total_items and (
        rejected / grounded.total_items > 0.25
    ):
        raise HTTPException(status_code=502, detail="Resume evidence validation failed: unsupported_item_threshold")


def _merge_repair(
    base: ResumeExtractionResult,
    repair: ResumeExtractionResult,
    section_label: str,
    section_heading: str,
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
    merged.education = _dedupe_education(merged.education)
    merged.experiences = _dedupe_experiences(merged.experiences)
    return merged


def _dedupe_education(items: list[Education]) -> list[Education]:
    by_institution: dict[str, Education] = {}
    for item in items:
        key = item.institution.casefold()
        existing = by_institution.get(key)
        if existing is None:
            by_institution[key] = item
        else:
            by_institution[key] = existing.model_copy(
                update={"relevant_courses": list(dict.fromkeys([*existing.relevant_courses, *item.relevant_courses]))}
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
) -> ProcessedResumeResult:
    grounded = ground_resume_extraction(result, source_text)
    _raise_if_unreliable(grounded)
    normalized = normalize_resume_extraction(grounded.result)
    warnings = list(grounded.warnings)
    missing = completeness_warnings(normalized, source_text)

    if allow_repair and missing and provider is not None and hasattr(provider, "extract_section"):
        warning = missing[0]
        section = section_for_warning(source_text, warning)
        if section is not None:
            try:
                repair_raw = provider.extract_section(section.text, section.key)
                repair_grounded = ground_resume_extraction(
                    repair_raw,
                    section.text,
                    source="repair",
                )
                warnings.extend(repair_grounded.warnings)
                normalized = normalize_resume_extraction(
                    _merge_repair(normalized, repair_grounded.result, section.key, section.heading)
                )
                missing = completeness_warnings(normalized, source_text)
            except Exception as error:
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
    if sum(len(facts) for _, facts in _fact_groups(normalized)) == 0:
        raise HTTPException(status_code=502, detail="Resume evidence validation failed: no_grounded_facts")
    return ProcessedResumeResult(result=normalized, warnings=warnings, completeness_warnings=missing)


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
    if file.content_type != "application/pdf" and not (file.filename or "").lower().endswith(".pdf"):
        raise HTTPException(status_code=415, detail="Only PDF resumes are supported")
    data = await file.read(MAX_RESUME_BYTES + 1)
    if len(data) > MAX_RESUME_BYTES:
        raise HTTPException(status_code=413, detail="Resume PDF exceeds the 10 MB limit")
    text = extract_pdf_text(data)
    provider = get_resume_provider()
    try:
        result = ResumeExtractionResult.model_validate(provider.extract(text))
        processed = process_resume_extraction(result, text, provider=provider)
        for warning in processed.warnings:
            logger.warning("Resume extraction warning: %s", warning)
    except HTTPException:
        raise
    except Exception as error:
        raise HTTPException(status_code=502, detail="Resume extraction provider failed") from error
    try:
        profile = create_draft_profile(db, processed.result)
        return get_profile(db, profile.id)
    except SQLAlchemyError as error:
        db.rollback()
        raise HTTPException(status_code=503, detail="Profile persistence failed") from error


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
