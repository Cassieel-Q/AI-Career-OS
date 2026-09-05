from __future__ import annotations

from dataclasses import dataclass

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
    ("EDUCATION", ("教育背景", "教育经历", "学历信息", "education", "academic background")),
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
            "internship",
        ),
    ),
    ("SKILLS", ("专业技能", "技能", "技能特长", "个人技能", "职业技能", "technical skills", "skills")),
    ("COURSES", ("主修课程", "核心课程", "相关课程", "relevant courses", "courses")),
    (
        "CREDENTIALS",
        ("证书", "资格证书", "技能证书", "语言证书", "certifications", "certificates", "credentials"),
    ),
    ("LANGUAGE", ("语言能力", "语言技能", "languages", "language skills")),
)


def _match_heading(line: str) -> tuple[str, str, str | None] | None:
    stripped = line.strip()
    for key, aliases in _SECTION_ALIASES:
        for alias in aliases:
            if stripped.casefold() == alias.casefold() or stripped.rstrip(":：").strip().casefold() == alias.casefold():
                return key, stripped.rstrip(":：").strip(), None
            prefix = f"{alias}:".casefold()
            prefix_cn = f"{alias}：".casefold()
            if stripped.casefold().startswith(prefix) or stripped.casefold().startswith(prefix_cn):
                content = stripped[len(alias) :].lstrip(" :：")
                return key, alias, content
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
        content_parts = ([inline_content] if inline_content else []) + [line.strip() for line in content_lines if line.strip()]
        content = "\n".join(part for part in content_parts if part).strip()
        if content:
            text = "\n".join([lines[start].strip(), *content_parts]).strip()
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


def completeness_warnings(result: ResumeExtractionResult, source_text: str) -> list[str]:
    non_empty = {section.key for section in detect_sections(source_text)}
    warnings: list[str] = []
    if "EDUCATION" in non_empty and not result.education:
        warnings.append("MISSING_SECTION_CONTENT:EDUCATION")
    if "CAMPUS" in non_empty and not any(item.experience_type == ExperienceType.CAMPUS for item in result.experiences):
        warnings.append("MISSING_SECTION_CONTENT:CAMPUS")
    if "EXPERIENCE" in non_empty and not result.experiences:
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
