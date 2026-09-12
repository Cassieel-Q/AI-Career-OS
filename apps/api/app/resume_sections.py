from __future__ import annotations

from dataclasses import dataclass
import re
import unicodedata

from app.resume_schemas import ExperienceType, ResumeExtractionResult


@dataclass(frozen=True)
class ResumeSection:
    key: str
    heading: str
    text: str
    content: str
    start: int
    end: int


_SECTION_ALIASES: tuple[tuple[str, tuple[str, ...]], ...] = (
    (
        "EDUCATION",
        ("教育背景", "教育经历", "学历信息", "education", "education background", "academic background"),
    ),
    ("CAMPUS", ("校园经历", "学生工作", "campus experience", "campus activities")),
    (
        "EXPERIENCE",
        (
            "实习经历",
            "工作经历",
            "实习/工作经历",
            "工作/实习经历",
            "项目经历",
            "实习经验",
            "工作经验",
            "professional experience",
            "work experience",
            "work history",
            "experience",
            "internship",
            "internship experience",
            "project experience",
        ),
    ),
    ("SKILLS", ("专业技能", "技能", "技能特长", "个人技能", "职业技能", "technical skills", "skills")),
    ("COURSES", ("主修课程", "核心课程", "相关课程", "relevant courses", "courses")),
    (
        "CREDENTIALS",
        (
            "证书",
            "资格证书",
            "技能证书",
            "语言证书",
            "certification",
            "certifications",
            "certificates",
            "credential",
            "credentials",
        ),
    ),
    ("LANGUAGE", ("语言能力", "语言技能", "language", "languages", "language skills")),
)


_LEADING_SECTION_NUMBER_RE = re.compile(
    r"^\s*(?:(?:\d{1,3}|[一二三四五六七八九十百千万]+)\s*"
    r"(?:[.．、:：)\]）-]\s*|\s+)|"
    r"[（(]\s*(?:\d{1,3}|[一二三四五六七八九十百千万]+)\s*[)）]\s*)"
)
_HEADING_DECORATOR_CHARS = " \t|/／()（）[]【】<>《》-–—:："


def _normalize_heading_surface(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        character for character in normalized if unicodedata.category(character) != "Cf"
    )
    return re.sub(r"\s+", " ", normalized).strip()


def _strip_leading_section_number(value: str) -> str:
    match = _LEADING_SECTION_NUMBER_RE.match(value)
    return value[match.end() :].strip() if match else value


def _decorated_heading_suffix(value: str) -> str:
    return value.strip(_HEADING_DECORATOR_CHARS).strip()


def _match_heading(line: str) -> tuple[str, str, str | None] | None:
    stripped = line.strip()
    candidate = _strip_leading_section_number(stripped)
    normalized_candidate = _normalize_heading_surface(candidate.rstrip(":：").strip())
    if not normalized_candidate:
        return None
    for key, aliases in _SECTION_ALIASES:
        normalized_aliases = {
            _normalize_heading_surface(other_alias)
            for other_alias in aliases
        }
        for alias in sorted(aliases, key=len, reverse=True):
            normalized_alias = _normalize_heading_surface(alias)
            if normalized_candidate == normalized_alias:
                return key, stripped.rstrip(":：").strip(), None

            inline_match = re.match(rf"^{re.escape(alias)}\s*[:：]", candidate, re.IGNORECASE)
            if inline_match:
                content = candidate[inline_match.end() :].strip()
                prefix_offset = len(stripped) - len(candidate)
                heading_end = prefix_offset + inline_match.end()
                heading = stripped[:heading_end].rstrip(":：").strip()
                return key, heading, content

            if not candidate.casefold().startswith(alias.casefold()):
                continue
            suffix = candidate[len(alias) :]
            normalized_suffix = _normalize_heading_surface(_decorated_heading_suffix(suffix))
            if normalized_suffix and normalized_suffix in normalized_aliases - {normalized_alias}:
                return key, stripped, None
    return None


def detect_sections(source_text: str) -> list[ResumeSection]:
    raw_lines = source_text.splitlines(keepends=True)
    lines = [line.rstrip("\r\n") for line in raw_lines]
    line_offsets: list[int] = []
    offset = 0
    for raw_line in raw_lines:
        line_offsets.append(offset)
        offset += len(raw_line)
    starts: list[tuple[int, str, str, str | None]] = []
    for index, line in enumerate(lines):
        match = _match_heading(line)
        if match:
            starts.append((index, *match))

    sections: list[ResumeSection] = []
    for position, (start, key, heading, inline_content) in enumerate(starts):
        end = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
        content_lines = lines[start + 1 : end]
        content_line_parts = [line.strip() for line in content_lines if line.strip()]
        content_parts = ([inline_content] if inline_content else []) + content_line_parts
        content = "\n".join(part for part in content_parts if part).strip()
        if content:
            text = "\n".join([lines[start].strip(), *content_line_parts]).strip()
            section_end_line = starts[position + 1][0] if position + 1 < len(starts) else len(lines)
            sections.append(
                ResumeSection(
                    key=key,
                    heading=heading,
                    text=text,
                    content=content,
                    start=line_offsets[start],
                    end=line_offsets[section_end_line] if section_end_line < len(line_offsets) else len(source_text),
                )
            )
    return sections


def _has_language_fact(result: ResumeExtractionResult) -> bool:
    language_tokens = ("english", "英语", "普通话", "mandarin", "日语", "日文", "japanese")
    values = [skill.name.casefold() for skill in result.skills]
    language_credentials = ("cet-4", "cet-6", "ielts", "toefl", "jlpt", "普通话")
    credentials = [certification.name.casefold() for certification in result.certifications]
    return any(token in value for value in values for token in language_tokens) or any(
        token in value for value in credentials for token in language_credentials
    )


def _normalize_section_value(value: str) -> str:
    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = "".join(
        character for character in normalized if unicodedata.category(character) != "Cf"
    )
    return re.sub(r"\s+", "", normalized)


def _expected_experience_types(heading: str) -> frozenset[ExperienceType]:
    normalized = _normalize_section_value(heading)
    if (
        normalized in {"实习/工作经历", "工作/实习经历"}
        or ("实习" in normalized and "工作" in normalized)
        or ("intern" in normalized and "work" in normalized)
    ):
        return frozenset({ExperienceType.WORK, ExperienceType.INTERNSHIP})
    if "项目" in normalized or "project" in normalized:
        return frozenset({ExperienceType.PROJECT})
    if "实习" in normalized or "intern" in normalized:
        return frozenset({ExperienceType.INTERNSHIP})
    if "工作" in normalized or "work" in normalized or "professional" in normalized:
        return frozenset({ExperienceType.WORK})
    return frozenset({ExperienceType.WORK, ExperienceType.INTERNSHIP, ExperienceType.PROJECT})


def _experience_evidence_is_in_section(
    item: object,
    section: ResumeSection,
    source_text: str,
) -> bool:
    evidence_start = getattr(item, "evidence_start", None)
    evidence_end = getattr(item, "evidence_end", None)
    if (
        isinstance(evidence_start, int)
        and isinstance(evidence_end, int)
        and section.start <= evidence_start < evidence_end <= section.end
    ):
        return True
    evidence_text = getattr(item, "evidence_text", "")
    return bool(evidence_text) and _normalize_section_value(evidence_text) in _normalize_section_value(
        source_text[section.start : section.end]
    )


def _experience_matches_section(
    item: object,
    section: ResumeSection,
    source_text: str,
    expected_types: frozenset[ExperienceType],
) -> bool:
    if getattr(item, "experience_type", None) not in expected_types:
        return False
    source_section = getattr(item, "source_section", None)
    if source_section:
        return _normalize_section_value(source_section) == _normalize_section_value(section.heading)
    return _experience_evidence_is_in_section(item, section, source_text)


def completeness_warnings(result: ResumeExtractionResult, source_text: str) -> list[str]:
    sections = detect_sections(source_text)
    non_empty = {section.key for section in sections}
    warnings: list[str] = []
    if "EDUCATION" in non_empty and not result.education:
        warnings.append("MISSING_SECTION_CONTENT:EDUCATION")
    campus_sections = [section for section in sections if section.key == "CAMPUS"]
    if campus_sections and not any(
        any(
            _experience_matches_section(
                item,
                section,
                source_text,
                frozenset({ExperienceType.CAMPUS}),
            )
            for item in result.experiences
        )
        for section in campus_sections
    ):
        warnings.append("MISSING_SECTION_CONTENT:CAMPUS")
    experience_sections = [section for section in sections if section.key == "EXPERIENCE"]
    if experience_sections and any(
        not any(
            _experience_matches_section(
                item,
                section,
                source_text,
                _expected_experience_types(section.heading),
            )
            for item in result.experiences
        )
        for section in experience_sections
    ):
        warnings.append("MISSING_SECTION_CONTENT:EXPERIENCE")
    if "SKILLS" in non_empty and not result.skills:
        warnings.append("MISSING_SECTION_CONTENT:SKILLS")
    if "COURSES" in non_empty and not any(item.relevant_courses for item in result.education):
        warnings.append("MISSING_SECTION_CONTENT:COURSES")
    if "CREDENTIALS" in non_empty and not result.certifications:
        warnings.append("MISSING_SECTION_CONTENT:CREDENTIALS")
    if "LANGUAGE" in non_empty and not _has_language_fact(result):
        warnings.append("MISSING_SECTION_CONTENT:LANGUAGE")
    return warnings


def section_for_warning(source_text: str, warning: str) -> ResumeSection | None:
    key = warning.split(":", 1)[-1]
    return next((section for section in detect_sections(source_text) if section.key == key), None)
