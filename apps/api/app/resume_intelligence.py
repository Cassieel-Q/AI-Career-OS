from __future__ import annotations

from typing import Protocol

from .knowledge_packs import KnowledgePack, KnowledgePackRegistry, load_default_registry
from .mission_provider import MissionProvider


class CareerEvidenceIntelligence(Protocol):
    def profile_facts(self, profile: object) -> list[dict[str, object]]: ...


class ResumeIntelligence(Protocol):
    provider: MissionProvider


class DefaultCareerEvidenceIntelligence:
    """Project Profile facts into a provider-safe, evidence-referenced shape."""

    @staticmethod
    def profile_facts(profile: object) -> list[dict[str, object]]:
        facts: list[dict[str, object]] = []
        for collection_name, kind, fields in (
            ("education", "education", ("institution", "degree", "field_of_study", "dates", "relevant_courses")),
            ("skills", "skill", ("name", "proficiency")),
            ("experiences", "experience", ("title", "organization", "dates", "description", "experience_type")),
            ("certifications", "certification", ("name", "issuer", "date", "score", "status")),
        ):
            for item in list(getattr(profile, collection_name, []) or []):
                value: dict[str, object] = {"id": str(item.id), "kind": kind}
                for field in fields:
                    candidate = getattr(item, field, None)
                    if candidate is not None:
                        value[field] = candidate
                if getattr(item, "evidence_text", None):
                    value["evidence_text"] = item.evidence_text
                facts.append(value)
        return facts


def resume_skill_records(registry: KnowledgePackRegistry | None = None, *, limit: int = 24) -> list[dict[str, object]]:
    """Serialize resume_skill knowledge packs for provider payloads."""
    reg = registry or load_default_registry()
    out: list[dict[str, object]] = []
    for pack in reg.by_kind("resume_skill")[:limit]:
        out.append(
            {
                "skill_id": pack.id,
                "name": pack.name,
                "provenance": pack.provenance,
                "competencies": list(pack.competencies),
                "body": pack.body[:2000],
                "source_refs": list(pack.source_refs),
            }
        )
    return out


CORE_RESUME_SKILL_IDS: tuple[str, ...] = (
    "EVIDENCE_GROUNDED_WRITING",
    "RESPONSIBILITY_BOUNDARY",
    "ACTION_METHOD_RESULT",
    "JD_RELEVANCE",
    "PROJECT_POSITIONING",
    "NO_FABRICATED_METRICS",
    "ASK_BEFORE_INVENTING",
    "REMOVE_GENERIC_LANGUAGE",
)


def select_applicable_resume_skills(
    registry: KnowledgePackRegistry | None = None,
    *,
    role: str | None = None,
    role_family: str | None = None,
    company: str | None = None,
    competencies: list[str] | None = None,
    min_count: int = 5,
    max_count: int = 12,
) -> list[dict[str, object]]:
    """Retrieve 5–12 resume skills for the Target Resume LLM prompt (must enter prompt)."""
    reg = registry or load_default_registry()
    packs = list(reg.by_kind("resume_skill"))
    if not packs:
        return []

    role_l = (role or "").casefold()
    family_l = (role_family or "").casefold()
    company_l = (company or "").casefold()
    comps = {c.casefold() for c in (competencies or []) if c}

    scored: list[tuple[int, object]] = []
    for pack in packs:
        score = 0
        pid = str(pack.id)
        if pid in CORE_RESUME_SKILL_IDS:
            score += 100
        # Optional domain skills when metadata matches
        blob = " ".join(
            [
                pid,
                pack.name,
                " ".join(pack.roles or []),
                " ".join(pack.related_roles or []),
                pack.role_family or "",
                pack.company or "",
                " ".join(pack.competencies or []),
            ]
        ).casefold()
        if any(tok in blob for tok in ("asu", "arizona", "github", "ai pm", "ai_product", "product manager", "实习", "intern")):
            if role_l and any(tok in role_l for tok in ("pm", "product", "实习", "intern", "ai")):
                score += 20
            if "ai_product" in family_l or "product" in family_l:
                score += 15
            if company_l and pack.company and pack.company.casefold() in company_l:
                score += 25
        if pack.role_family and pack.role_family.casefold() == family_l:
            score += 30
        if comps and any(c.casefold() in comps for c in (pack.competencies or [])):
            score += 10
        scored.append((score, pack))

    scored.sort(key=lambda item: (-item[0], item[1].id))
    # Always prefer core skills first
    chosen: list[object] = []
    seen: set[str] = set()
    for sid in CORE_RESUME_SKILL_IDS:
        for score, pack in scored:
            if pack.id == sid and pack.id not in seen:
                chosen.append(pack)
                seen.add(pack.id)
                break
    for score, pack in scored:
        if pack.id in seen:
            continue
        if score <= 0 and len(chosen) >= min_count:
            continue
        chosen.append(pack)
        seen.add(pack.id)
        if len(chosen) >= max_count:
            break
    if len(chosen) < min_count:
        for score, pack in scored:
            if pack.id in seen:
                continue
            chosen.append(pack)
            seen.add(pack.id)
            if len(chosen) >= min_count:
                break
    chosen = chosen[:max_count]
    return [
        {
            "skill_id": pack.id,
            "name": pack.name,
            "provenance": pack.provenance,
            "competencies": list(pack.competencies),
            "body": pack.body[:2000],
            "source_refs": list(pack.source_refs),
            "roles": list(pack.roles or []),
            "role_family": pack.role_family,
            "company": pack.company,
        }
        for pack in chosen
    ]

