from pathlib import Path

from app.knowledge_packs import KnowledgePackLoader, KnowledgePackRegistry, load_default_registry


def test_loader_keeps_valid_pack_and_reports_malformed_file(tmp_path: Path):
    valid = tmp_path / "resume_skills"
    valid.mkdir()
    (valid / "writing.md").write_text(
        "---\n"
        "id: EVIDENCE_GROUNDED_WRITING\n"
        "kind: resume_skill\n"
        "name: Evidence grounded writing\n"
        "version: 1.0.0\n"
        "provenance: synthetic\n"
        "competencies: [grounding, writing]\n"
        "---\nUse only supported evidence.\n",
        encoding="utf-8",
    )
    (valid / "broken.md").write_text("not frontmatter", encoding="utf-8")

    registry = KnowledgePackRegistry(tmp_path)

    assert [pack.id for pack in registry.packs] == ["EVIDENCE_GROUNDED_WRITING"]
    assert len(registry.errors) == 1
    assert registry.packs[0].fingerprint
    assert "Use only supported evidence" in registry.packs[0].body


def test_loader_reports_unknown_fields_without_crashing(tmp_path: Path):
    path = tmp_path / "unknown.md"
    path.write_text(
        "---\nid: UNKNOWN\nkind: resume_skill\nname: Unknown\nversion: 1\nprovenance: test\nextra: nope\n---\n",
        encoding="utf-8",
    )

    pack, diagnostic = KnowledgePackLoader().load_file(path)

    assert pack is None
    assert diagnostic is not None
    assert diagnostic.code == "SCHEMA_INVALID"


def test_default_demo_registry_has_resume_generic_and_company_layers():
    registry = load_default_registry()

    resume = registry.by_kind("resume_skill")
    interview = registry.by_kind("interview_skill")
    assert len(resume) >= 8
    assert len(interview) >= 19
    companies = {pack.company for pack in interview if pack.company}
    # Demo layers remain; CURATED import may add more companies.
    assert {"Baidu", "Xiaohongshu", "ByteDance"}.issubset(companies)
    demo_company_packs = [pack for pack in interview if pack.company in {"Baidu", "Xiaohongshu", "ByteDance"} and "SYNTHETIC" in (pack.provenance or "").upper()]
    assert demo_company_packs, "expected SYNTHETIC demo packs for Baidu/XHS/ByteDance"
    curated = [pack for pack in interview if (pack.provenance or "").upper().startswith("CURATED")]
    assert curated, "expected CURATED interview packs from Nowcoder import"


def test_loader_accepts_product_brief_type_and_source_aliases(tmp_path: Path):
    path = tmp_path / "baidu.md"
    path.write_text(
        "---\n"
        "id: baidu_metrics\n"
        "type: interview\n"
        "version: 1\n"
        "source_name: synthetic-demo\n"
        "source_urls: [https://example.test/report]\n"
        "latest_source_date: 2026-09\n"
        "confidence: medium\n"
        "company: Baidu\n"
        "role_family: AI_PRODUCT\n"
        "competencies: [PRODUCT_METRICS]\n"
        "source_count: 2\n"
        "---\nObserved signal.\n",
        encoding="utf-8",
    )

    pack, diagnostic = KnowledgePackLoader().load_file(path)

    assert diagnostic is None
    assert pack is not None
    assert pack.kind == "interview_skill"
    assert pack.name == "baidu_metrics"
    assert pack.provenance == "synthetic-demo"
    assert pack.source_refs == ["https://example.test/report"]
    assert pack.recency == "2026-09"
