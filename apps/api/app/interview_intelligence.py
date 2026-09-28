from __future__ import annotations

from dataclasses import dataclass

from .company_aliases import canonical_company
from .knowledge_packs import KnowledgePack, KnowledgePackRegistry, load_default_registry


def _norm(value: str | None) -> str:
    return " ".join((value or "").casefold().replace("-", " ").split())


def is_synthetic_pack(pack_id: str | None, provenance: str | None) -> bool:
    """True for synthetic/demo knowledge packs (DEMO_* ids, SYNTHETIC* / *DEMO_ONLY provenance).

    These packs are fabricated examples, not real company interview reports, and must not be
    returned as company intel for real missions.
    """
    prov = (provenance or "").upper()
    return (pack_id or "").upper().startswith("DEMO_") or "SYNTHETIC" in prov or "DEMO_ONLY" in prov


@dataclass(frozen=True, slots=True)
class InterviewIntelResult:
    skill_id: str
    name: str
    company_relevance: str
    role_relevance: str
    competency: str
    source_count: int
    recency: str | None
    confidence: float
    source_refs: list[str]
    body: str
    provenance: str = ""

    @property
    def observed_label(self) -> str:
        prov = (self.provenance or "").upper()
        if "SYNTHETIC" in prov or prov.endswith("_DEMO_ONLY") or "DEMO_ONLY" in prov or (self.skill_id or "").upper().startswith("DEMO_"):
            return f"Synthetic demo pack ({self.source_count} entries) — not real company interview reports"
        if self.company_relevance == "SAME_COMPANY":
            return f"Observed in {self.source_count} curated company reports"
        if self.company_relevance in {"ROLE_FAMILY", "OTHER_COMPANY"}:
            return f"Observed in {self.source_count} adjacent-role reports"
        return f"Generic / fallback signals ({self.source_count} entries)"


class InterviewIntelRetriever:
    def __init__(self, registry: KnowledgePackRegistry | None = None):
        self.registry = registry or load_default_registry()

    def retrieve(
        self,
        *,
        company: str | None,
        role: str | None,
        role_family: str | None,
        competencies: list[str] | None = None,
        limit: int = 12,
        include_synthetic: bool = False,
    ) -> list[InterviewIntelResult]:
        """Rank interview-skill packs for a company/role.

        Synthetic demo packs (DEMO_* / SYNTHETIC* provenance) are excluded by default so they can
        never masquerade as real company intel. Pass ``include_synthetic=True`` (tests/demos only)
        to opt in; even then they are labelled ``SYNTHETIC_DEMO``, ranked after every real pack,
        and never receive the SAME_COMPANY confidence bonus.
        """
        company_key = canonical_company(company) or _norm(company)
        role_key = _norm(role)
        family_key = _norm(role_family)
        requested = {_norm(item) for item in (competencies or []) if _norm(item)}
        ranked: list[tuple[tuple[int, int, int, str], KnowledgePack, str, str]] = []
        for pack in self.registry.by_kind("interview_skill"):
            synthetic = is_synthetic_pack(pack.id, pack.provenance)
            if synthetic and not include_synthetic:
                continue
            pack_company = canonical_company(pack.company) or _norm(pack.company)
            pack_family = _norm(pack.role_family)
            roles = {_norm(item) for item in [*pack.roles, *pack.related_roles]}
            overlap = len(requested.intersection({_norm(item) for item in pack.competencies}))
            if company_key and pack_company == company_key and (not pack_family or not family_key or pack_family == family_key):
                tier, company_relevance = 1, "SAME_COMPANY"
                role_relevance = "SAME_ROLE_FAMILY" if pack_family == family_key else "RELATED_ROLE"
            elif company_key and pack_company == company_key:
                tier, company_relevance, role_relevance = 2, "SAME_COMPANY", "RELATED_ROLE"
            elif family_key and pack_family == family_key:
                tier, company_relevance, role_relevance = 3, "ROLE_FAMILY", "OTHER_COMPANY"
            elif pack_family in {"generic ai pm", "generic", "ai product"} or not pack_company:
                tier, company_relevance, role_relevance = 4, "GENERIC", "GENERIC_AI_PM"
            else:
                continue
            if synthetic:
                # Opt-in demo content: never SAME_COMPANY, always after real packs.
                tier, company_relevance = 5, "SYNTHETIC_DEMO"
            if role_key and roles and any(role_key in candidate or candidate in role_key for candidate in roles):
                role_score = 2
            elif role_key and not roles:
                role_score = 1
            else:
                role_score = 0
            prov = (pack.provenance or "").upper()
            # Prefer CURATED/Niuke; deprioritize DEMO_/SYNTHETIC English demo packs.
            demo_penalty = 1 if synthetic else 0
            curated_bonus = -1 if prov.startswith("CURATED") or "NIUKE" in prov or "NOWCODER" in prov or "牛客" in (pack.provenance or "") else 0
            ranked.append(((tier, demo_penalty, curated_bonus, -overlap, -role_score, pack.id), pack, company_relevance, role_relevance))
        ranked.sort(key=lambda row: row[0])
        results: list[InterviewIntelResult] = []
        for _, pack, company_relevance, role_relevance in ranked[:limit]:
            confidence = min(0.99, 0.55 + (0.15 if company_relevance == "SAME_COMPANY" else 0) + (0.1 if pack.source_count else 0) + min(0.15, 0.05 * len(pack.competencies)))
            results.append(
                InterviewIntelResult(
                    skill_id=pack.id,
                    name=pack.name,
                    company_relevance=company_relevance,
                    role_relevance=role_relevance,
                    competency=pack.competencies[0] if pack.competencies else "general",
                    source_count=pack.source_count,
                    recency=pack.recency,
                    confidence=confidence,
                    source_refs=list(pack.source_refs),
                    body=pack.body,
                    provenance=str(pack.provenance or ""),
                )
            )
        return results

