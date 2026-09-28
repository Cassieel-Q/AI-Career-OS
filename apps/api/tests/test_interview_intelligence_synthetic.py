"""Synthetic demo packs must not leak into real company intel (mission 1ef029bf regression)."""

from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.interview_intelligence import InterviewIntelRetriever, is_synthetic_pack
from app.knowledge_packs import KnowledgePackRegistry, load_default_registry


def _is_synthetic_item(item) -> bool:
    return is_synthetic_pack(item.skill_id, item.provenance)


def test_default_registry_still_contains_demo_packs():
    ids = {pack.id for pack in load_default_registry().by_kind("interview_skill")}
    assert any(pack_id.startswith("DEMO_BAIDU_") for pack_id in ids)


def test_baidu_default_retrieval_excludes_synthetic_and_keeps_curated():
    retriever = InterviewIntelRetriever()
    for company in ("百度", "百度智能云", "Baidu"):
        items = retriever.retrieve(company=company, role="AI产品经理", role_family="AI_PRODUCT")
        assert items, company
        assert not any(_is_synthetic_item(item) for item in items), (company, [i.skill_id for i in items])
        assert not any(item.skill_id.upper().startswith("DEMO_") for item in items)
        same_company = [item for item in items if item.company_relevance == "SAME_COMPANY"]
        assert [item.skill_id for item in same_company] == ["CURATED_BAIDU_AI_PRODUCT"], company
        assert items[0].skill_id == "CURATED_BAIDU_AI_PRODUCT"
        assert all("CURATED" in item.provenance.upper() for item in items)


def test_include_synthetic_returns_demo_packs_but_never_same_company():
    items = InterviewIntelRetriever().retrieve(
        company="百度智能云", role="AI产品经理", role_family="AI_PRODUCT", limit=100, include_synthetic=True
    )
    synthetic = [item for item in items if _is_synthetic_item(item)]
    assert any(item.skill_id.startswith("DEMO_BAIDU_") for item in synthetic)
    assert all(item.company_relevance == "SYNTHETIC_DEMO" for item in synthetic)
    assert all(item.company_relevance != "SAME_COMPANY" for item in synthetic)
    # no SAME_COMPANY +0.15 bonus: max = 0.55 + 0.1 + 0.15
    assert all(item.confidence <= 0.8 + 1e-9 for item in synthetic)
    # real packs always rank before any synthetic pack
    first_synthetic = next(i for i, item in enumerate(items) if _is_synthetic_item(item))
    assert all(not _is_synthetic_item(item) for item in items[:first_synthetic])
    assert all(_is_synthetic_item(item) for item in items[first_synthetic:])
    assert "CURATED_BAIDU_AI_PRODUCT" in [item.skill_id for item in items]
    assert items[0].skill_id == "CURATED_BAIDU_AI_PRODUCT"
    assert items[0].company_relevance == "SAME_COMPANY"


def _write(path: Path, *, pack_id: str, provenance: str, company: str | None, role_family: str) -> None:
    path.write_text(
        "---\n"
        f"id: {pack_id}\n"
        "kind: interview_skill\n"
        f"name: {pack_id}\n"
        "version: 1.0.0\n"
        f"provenance: {provenance}\n"
        + (f"company: {company}\n" if company else "")
        + f"role_family: {role_family}\n"
        "competencies: [evaluation]\n"
        "source_count: 3\n"
        "recency: 2026-01-01\n"
        "---\nSkill body.\n",
        encoding="utf-8",
    )


def test_only_synthetic_available_returns_empty_list_by_default(tmp_path: Path):
    root = tmp_path / "interview_skills"
    root.mkdir()
    _write(root / "demo.md", pack_id="DEMO_ACME_PM", provenance="SYNTHETIC_DEMO_ONLY", company="Acme", role_family="AI_PRODUCT")
    _write(root / "generic.md", pack_id="GENERIC_EVAL", provenance="SYNTHETIC_DEMO", company=None, role_family="GENERIC_AI_PM")
    _write(root / "odd.md", pack_id="DEMO_NO_PROV", provenance="CURATED", company="Acme", role_family="AI_PRODUCT")
    retriever = InterviewIntelRetriever(KnowledgePackRegistry(tmp_path))
    assert retriever.retrieve(company="Acme", role="PM", role_family="AI_PRODUCT") == []
    opted = retriever.retrieve(company="Acme", role="PM", role_family="AI_PRODUCT", include_synthetic=True)
    assert {item.skill_id for item in opted} == {"DEMO_ACME_PM", "GENERIC_EVAL", "DEMO_NO_PROV"}
    assert all(item.company_relevance == "SYNTHETIC_DEMO" for item in opted)
