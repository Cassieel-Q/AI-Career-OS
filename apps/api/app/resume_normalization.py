from __future__ import annotations

import re

from app.resume_schemas import Certification, ExperienceType, ResumeExtractionResult, Skill


_OFFICE_ALIASES = {
    "word": "Word",
    "microsoft word": "Word",
    "excel": "Excel",
    "microsoft excel": "Excel",
    "ppt": "PowerPoint",
    "powerpoint": "PowerPoint",
    "microsoft powerpoint": "PowerPoint",
}
_OFFICE_SEPARATOR = re.compile(r"\s*(?:[,，、/／|;；+&]|\band\b|和)\s*", re.IGNORECASE)
_CREDENTIAL_PATTERNS = (
    (re.compile(r"\b(?:cet[- ]?4|大学英语四级)\b", re.IGNORECASE), "CET-4"),
    (re.compile(r"\b(?:cet[- ]?6|大学英语六级)\b", re.IGNORECASE), "CET-6"),
    (re.compile(r"普通话二级甲等"), "普通话二级甲等"),
    (re.compile(r"\b(?:ielts|雅思)\b", re.IGNORECASE), "IELTS"),
    (re.compile(r"\b(?:toefl|托福)\b", re.IGNORECASE), "TOEFL"),
    (re.compile(r"\bjlpt\b", re.IGNORECASE), "JLPT"),
)
_CREDENTIAL_SCORE = re.compile(
    r"(?:cet[- ]?[46]|大学英语四级|大学英语六级)\s*(?:score|成绩|分数)?\s*[:：-]?\s*(\d{2,4})",
    re.IGNORECASE,
)
_LANGUAGE_PATTERNS = (
    (re.compile(r"普通话|国语|mandarin", re.IGNORECASE), "普通话"),
    (re.compile(r"英语|english", re.IGNORECASE), "English"),
)
_SECTION_TYPES = (
    (re.compile(r"校园经历|学生工作|社团|campus|student union", re.IGNORECASE), ExperienceType.CAMPUS),
    (re.compile(r"实习|intern", re.IGNORECASE), ExperienceType.INTERNSHIP),
    (re.compile(r"项目经历|项目经验|project", re.IGNORECASE), ExperienceType.PROJECT),
    (re.compile(r"工作经历|工作经验|任职经历|professional experience|work experience", re.IGNORECASE), ExperienceType.WORK),
)


def _clean_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        normalized = value.strip()
        key = normalized.casefold()
        if normalized and key not in seen:
            seen.add(key)
            cleaned.append(normalized)
    return cleaned


def _canonical_office_items(name: str) -> list[tuple[str, str]]:
    normalized = name.strip().casefold()
    direct = _OFFICE_ALIASES.get(normalized)
    if direct:
        return [(direct, name.strip())]
    parts = _OFFICE_SEPARATOR.split(name.strip())
    if len(parts) < 2:
        return [(name.strip(), name.strip())]
    canonical = [_OFFICE_ALIASES.get(part.casefold()) for part in parts]
    if all(canonical):
        return list(dict.fromkeys((item, part) for item, part in zip(canonical, parts)))
    return [(name.strip(), name.strip())]


def _credential_details(name: str) -> tuple[str, str | None] | None:
    for pattern, canonical in _CREDENTIAL_PATTERNS:
        if pattern.search(name):
            score_match = _CREDENTIAL_SCORE.search(name)
            return canonical, score_match.group(1) if score_match else None
    return None


def _credential_name(name: str) -> str | None:
    details = _credential_details(name)
    return details[0] if details else None


def _language_name(name: str) -> str | None:
    if _credential_name(name):
        return None
    for pattern, canonical in _LANGUAGE_PATTERNS:
        if pattern.search(name):
            return canonical
    return None


def _classify_experience(source_section: str | None, current: ExperienceType) -> ExperienceType:
    for pattern, experience_type in _SECTION_TYPES:
        if source_section and pattern.search(source_section):
            return experience_type
    return current


def normalize_resume_extraction(result: ResumeExtractionResult) -> ResumeExtractionResult:
    """Normalize only deterministic, explicitly supported resume patterns.

    Every generated item keeps the original evidence excerpt. Canonical names are
    aliases for facts already present in that excerpt; this function never creates
    a fact from free-form prose.
    """

    education = [
        item.model_copy(update={"relevant_courses": _clean_list(item.relevant_courses)})
        for item in result.education
    ]
    experiences = [
        item.model_copy(update={"experience_type": _classify_experience(item.source_section, item.experience_type)})
        for item in result.experiences
    ]

    skills: list[Skill] = []
    certifications = list(result.certifications)
    for skill in result.skills:
        raw_value = skill.raw_value or skill.name
        credential_details = _credential_details(raw_value)
        if credential_details:
            credential, score = credential_details
            certifications.append(
                Certification(
                    name=credential,
                    score=score,
                    evidence_text=skill.evidence_text,
                    raw_value=raw_value,
                    canonical_value=credential,
                    evidence_start=skill.evidence_start,
                    evidence_end=skill.evidence_end,
                )
            )
            continue
        language = _language_name(raw_value)
        names = [(language, raw_value)] if language else _canonical_office_items(raw_value)
        skills.extend(
            skill.model_copy(
                update={"name": name, "raw_value": raw_name, "canonical_value": name}
            )
            for name, raw_name in names
            if name
        )

    normalized_certifications: list[Certification] = []
    for certification in certifications:
        credential_details = _credential_details(certification.raw_value or certification.name)
        if credential_details:
            credential, detected_score = credential_details
            normalized_certification = certification.model_copy(
                update={
                    "name": credential,
                    "score": certification.score or detected_score,
                    "raw_value": certification.raw_value or certification.name,
                    "canonical_value": credential,
                }
            )
            normalized_certifications.append(normalized_certification)
            continue
        raw_value = certification.raw_value or certification.name
        language = _language_name(raw_value)
        if language:
            skills.append(
                Skill(
                    name=language,
                    evidence_text=certification.evidence_text,
                    raw_value=raw_value,
                    canonical_value=language,
                    evidence_start=certification.evidence_start,
                    evidence_end=certification.evidence_end,
                )
            )
            continue
        normalized_certifications.append(
            certification.model_copy(
                update={"raw_value": raw_value, "canonical_value": certification.name}
            )
        )

    deduped_skills: list[Skill] = []
    skill_keys: set[str] = set()
    for skill in skills:
        key = skill.name.casefold()
        if key not in skill_keys:
            skill_keys.add(key)
            deduped_skills.append(skill)

    deduped_certifications: list[Certification] = []
    certification_keys: set[str] = set()
    for certification in normalized_certifications:
        key = certification.name.casefold()
        if key not in certification_keys:
            certification_keys.add(key)
            deduped_certifications.append(certification)

    return result.model_copy(
        update={
            "education": education,
            "skills": deduped_skills,
            "experiences": experiences,
            "certifications": deduped_certifications,
        }
    )
