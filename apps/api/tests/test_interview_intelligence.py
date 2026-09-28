from pathlib import Path

from app.interview_intelligence import InterviewIntelRetriever
from app.knowledge_packs import KnowledgePackRegistry


def _write(path: Path, *, pack_id: str, company: str | None, role_family: str, competencies: str, provenance: str = "CURATED") -> None:
    path.write_text(
        "---\n"
        f"id: {pack_id}\n"
        "kind: interview_skill\n"
        f"name: {pack_id}\n"
        "version: 1.0.0\n"
        f"provenance: {provenance}\n"
        + (f"company: {company}\n" if company else "")
        + f"role_family: {role_family}\n"
        f"competencies: [{competencies}]\n"
        "source_count: 3\n"
        "recency: 2026-01-01\n"
        "---\nSkill body.\n",
        encoding="utf-8",
    )


def test_retrieval_prioritizes_company_role_then_family_then_generic(tmp_path: Path):
    root = tmp_path / "interview_skills"
    root.mkdir()
    _write(root / "company.md", pack_id="BAIDU_EVAL", company="Baidu", role_family="AI_PRODUCT", competencies="evaluation")
    _write(root / "family.md", pack_id="FAMILY_EVAL", company=None, role_family="AI_PRODUCT", competencies="evaluation")
    _write(root / "generic.md", pack_id="GENERIC", company=None, role_family="GENERIC_AI_PM", competencies="evaluation")

    results = InterviewIntelRetriever(KnowledgePackRegistry(tmp_path)).retrieve(
        company="Baidu", role="AI Product Manager", role_family="AI_PRODUCT", competencies=["evaluation"]
    )

    assert [item.skill_id for item in results] == ["BAIDU_EVAL", "FAMILY_EVAL", "GENERIC"]
    assert results[0].company_relevance == "SAME_COMPANY"
    assert results[1].company_relevance == "ROLE_FAMILY"
    assert all("Observed in" not in item.skill_id for item in results)

