from __future__ import annotations

import re
from collections.abc import Iterable, Mapping

from .interview_intelligence import InterviewIntelRetriever, InterviewIntelResult
from .mission_provider import MissionProvider, get_mission_provider
from .mission_schemas import JobExtractionPayload, WhatMattersPayload


def intel_records(items: list[InterviewIntelResult]) -> list[dict[str, object]]:
    return [
        {
            "skill_id": item.skill_id,
            "name": item.name,
            "company_relevance": item.company_relevance,
            "role_relevance": item.role_relevance,
            "competency": item.competency,
            "source_count": item.source_count,
            "recency": item.recency,
            "confidence": item.confidence,
            "source_refs": item.source_refs,
            "observed_label": item.observed_label,
            "body": item.body,
            "provenance": item.provenance,
        }
        for item in items
    ]


def bounded_intel_records(items: Iterable[object] | None, *, max_items: int = 6, max_questions: int = 3) -> list[dict[str, object]]:
    """Project curated interview intel into a small, model-safe context block."""
    out: list[dict[str, object]] = []
    for raw in items or []:
        if isinstance(raw, InterviewIntelResult):
            item = intel_records([raw])[0]
        elif isinstance(raw, Mapping):
            item = dict(raw)
        else:
            continue
        provenance = str(item.get("provenance") or "").upper()
        skill_id = str(item.get("skill_id") or "")
        if "SYNTHETIC" in provenance or "DEMO_ONLY" in provenance or skill_id.upper().startswith("DEMO_"):
            continue
        body = str(item.get("body") or "")
        section = ""
        focus: list[str] = []
        questions: list[str] = []
        for line in body.splitlines():
            stripped = line.strip()
            if stripped.startswith("## "):
                section = stripped[3:].casefold()
                continue
            if not stripped.startswith("- "):
                continue
            value = stripped[2:].strip()
            value = re.sub(r"\s*（来源面经[^）]*）$", "", value).strip()
            value = re.sub(r"\s*\[[^\]]*\]$", "", value).strip()
            if not value or "未提及" in value or "无题目" in value:
                continue
            if "question patterns" in section and value not in questions:
                questions.append(value)
            elif "interviewer intent" in section and value not in focus:
                focus.append(value)
        out.append(
            {
                "skill_id": skill_id,
                "name": str(item.get("name") or skill_id),
                "company_relevance": str(item.get("company_relevance") or ""),
                "source_refs": [str(ref) for ref in (item.get("source_refs") or []) if str(ref).strip()][:6],
                "provenance": str(item.get("provenance") or ""),
                "focus": focus[:3],
                "question_patterns": questions[:max_questions],
            }
        )
        if len(out) >= max_items:
            break
    return out


class MissionIntelligenceService:
    def __init__(self, *, provider: MissionProvider | None = None, retriever: InterviewIntelRetriever | None = None):
        self.provider = provider or get_mission_provider()
        self.retriever = retriever or InterviewIntelRetriever()

    def analyze_jd(self, raw_text: str) -> tuple[JobExtractionPayload, WhatMattersPayload, list[dict[str, object]]]:
        extraction = self.provider.parse_jd(raw_text)
        intel = self.retriever.retrieve(
            company=extraction.company,
            role=extraction.role,
            role_family=extraction.role_family,
            competencies=[*extraction.capabilities, *extraction.keywords],
        )
        records = intel_records(intel)
        what_matters = self.provider.build_what_matters(raw_text=raw_text, extraction=extraction, interview_intel=records)
        return extraction, what_matters, records

