"""不调用模型的简历解析（可信求职 v1.2 · 指令 3.2）。

无模型时用户也必须能建档、编辑原文、管理岗位。这条路径只做**保守的结构化**：
把原文切成教育 / 技能 / 经历 / 证书四块，每条都带原文证据（``evidence_text``）。
识别不出来就留空，绝不臆造事实——用户随后可在简历工作台里自行补正，
或在配置好模型后再跑一次 AI 解析。
"""

from __future__ import annotations

import re
from typing import Any

_SECTION_PATTERNS: tuple[tuple[str, tuple[str, ...]], ...] = (
    ("education", ("教育经历", "教育背景", "教育", "学历")),
    ("skills", ("专业技能", "技能清单", "技能", "掌握工具", "工具", "技术栈")),
    ("certifications", ("证书", "荣誉", "获奖", "奖励")),
    ("experiences", ("实习经历", "工作经历", "项目经历", "项目经验", "实践经历", "社团经历", "校园经历", "经历", "经验")),
)

_YEAR_RE = re.compile(r"(20\d{2}|19\d{2})\s*[./年\-]?\s*(\d{1,2})?")
_CONTACT_EMAIL_RE = re.compile(r"[\w.+-]+@[\w-]+\.[\w.]+")
_PHONE_RE = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
_SCHOOL_RE = re.compile(r"[\u4e00-\u9fa5A-Za-z]{2,20}(大学|学院|学校|University|College)")
_DEGREE_RE = re.compile(r"(博士|硕士|研究生|本科|学士|大专|MBA|Master|Bachelor|PhD)")
_SPLIT_RE = re.compile(r"[、,，/|；;]+")
_BULLET_RE = re.compile(r"^\s*[-•*·]\s*")


def _line_kind(line: str) -> str | None:
    stripped = line.strip()
    for kind, markers in _SECTION_PATTERNS:
        for marker in markers:
            if stripped.startswith(marker) and len(stripped) <= len(marker) + 4:
                return kind
    return None


def _split_sections(raw_text: str) -> dict[str, list[str]]:
    """按段落标题把原文切成四块；没有标题的都归到 unassigned。"""
    sections: dict[str, list[str]] = {"education": [], "skills": [], "certifications": [], "experiences": [], "unassigned": []}
    current = "unassigned"
    for raw_line in (raw_text or "").splitlines():
        line = raw_line.strip()
        if not line:
            continue
        kind = _line_kind(line)
        if kind:
            current = kind
            continue
        sections[current].append(line)
    return sections


def _guess_experience_type(title: str, body: str) -> str:
    text = f"{title} {body}"
    if "实习" in text:
        return "INTERNSHIP"
    if "项目" in text:
        return "PROJECT"
    if "社团" in text or "学生会" in text or "校园" in text:
        return "CAMPUS"
    if "工作" in text or "任职" in text:
        return "WORK"
    return "OTHER"


def _parse_education(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        school = _SCHOOL_RE.search(line)
        if not school:
            continue
        degree = _DEGREE_RE.search(line)
        dates = _YEAR_RE.search(line)
        out.append(
            {
                "institution": school.group(0).strip(),
                "degree": degree.group(0) if degree else None,
                "field_of_study": None,
                "dates": dates.group(0) if dates else None,
                "evidence_text": line[:400],
            }
        )
    return out[:6]


def _parse_skills(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        body = _BULLET_RE.sub("", line)
        if len(body) > 120:
            continue
        for part in _SPLIT_RE.split(body):
            name = part.strip().strip("：: 。")
            if not name or len(name) > 30:
                continue
            if name in {item["name"] for item in out}:
                continue
            out.append({"name": name, "evidence_text": line[:400]})
    return out[:30]


def _parse_experiences(lines: list[str]) -> list[dict[str, Any]]:
    """以「看起来像标题」的行（短、或带日期）作为一条经历的开始，其后缩进行作为描述。"""
    out: list[dict[str, Any]] = []
    current: dict[str, Any] | None = None
    for line in lines:
        body = _BULLET_RE.sub("", line).strip()
        if not body:
            continue
        looks_like_heading = bool(_YEAR_RE.search(body)) or (len(body) <= 30 and not _SPLIT_RE.search(body))
        if looks_like_heading and not body.startswith(("负责", "参与", "协助", "完成", "使用")):
            if current and current.get("description"):
                out.append(current)
            dates = _YEAR_RE.search(body)
            title = _YEAR_RE.sub("", body).strip(" ·|-——") or body
            current = {
                "title": title[:120] or body[:120],
                "organization": None,
                "dates": dates.group(0) if dates else None,
                "description": None,
                "experience_type": _guess_experience_type(title, ""),
                "evidence_text": line[:400],
            }
            continue
        if current is None:
            continue
        current["description"] = (f"{current['description'] or ''} {body}".strip())[:1_200]
        current["experience_type"] = _guess_experience_type(str(current["title"]), current["description"] or "")
    if current and current.get("description"):
        out.append(current)
    return out[:20]


def _parse_certifications(lines: list[str]) -> list[dict[str, Any]]:
    out: list[dict[str, Any]] = []
    for line in lines:
        body = _BULLET_RE.sub("", line).strip()
        if not body or len(body) > 80:
            continue
        dates = _YEAR_RE.search(body)
        out.append({"name": body, "issuer": None, "date": dates.group(0) if dates else None, "evidence_text": line[:400]})
    return out[:10]


def local_resume_extraction(raw_text: str) -> dict[str, Any]:
    """返回与 :class:`app.resume_schemas.ResumeExtractionResult` 兼容的字典。"""
    sections = _split_sections(raw_text)
    education = _parse_education(sections["education"])
    skills = _parse_skills(sections["skills"])
    certifications = _parse_certifications(sections["certifications"])
    experiences = _parse_experiences(sections["experiences"])

    # 没有任何段落标题时，从整段文字里做一次保守兜底。
    if not education and not experiences and sections["unassigned"]:
        education = _parse_education(sections["unassigned"])
        fallback_experiences = _parse_experiences(sections["unassigned"])
        if not experiences:
            experiences = fallback_experiences

    email = _CONTACT_EMAIL_RE.search(raw_text or "")
    phone = _PHONE_RE.search(raw_text or "")

    return {
        "education": education,
        "skills": skills,
        "experiences": experiences,
        "certifications": certifications,
        "full_name": None,
        "phone": phone.group(0) if phone else None,
        "email": email.group(0) if email else None,
        "city": None,
    }
