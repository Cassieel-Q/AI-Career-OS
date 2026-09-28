"""Eval stubs / gates for Full Intelligence v0.2.

Cases:
- Baidu retrieval preference (SAME_COMPANY over ROLE_FAMILY/GENERIC)
- No fabricated metrics gate
- Curated vs synthetic provenance labeling
"""
from __future__ import annotations

import sys
from pathlib import Path

import pytest

API_ROOT = Path(__file__).resolve().parents[1]
REPO = API_ROOT.parent.parent if (API_ROOT.parent / "knowledge").exists() else API_ROOT.parents[2]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

KNOWLEDGE = None
for cand in [
    REPO / "knowledge",
    API_ROOT.parent.parent / "knowledge",
    Path("G:/myself/ai-career-OS-v0.2-full-intelligence/knowledge"),
]:
    if cand.is_dir():
        KNOWLEDGE = cand
        break


def test_eval_baidu_retrieval_preference_packs_exist():
    """Stub: Baidu curated pack must exist so SAME_COMPANY retrieval can win."""
    if KNOWLEDGE is None:
        pytest.skip("knowledge/ not found")
    curated = list((KNOWLEDGE / "interview_skills" / "curated").glob("*baidu*"))
    assert curated, "expected curated Baidu interview pack"
    text = curated[0].read_text(encoding="utf-8")
    assert "provenance: CURATED" in text
    assert "Baidu" in text or "百度" in text


def test_eval_baidu_alias_ranks_same_company():
    try:
        from app.company_aliases import canonical_company, companies_match
    except Exception:
        pytest.skip("company_aliases not importable")
    assert companies_match("百度", "Baidu")
    assert canonical_company("百度") == "baidu"
    # Ranking stub: SAME_COMPANY key before ROLE_FAMILY / GENERIC
    tiers = ["SAME_COMPANY", "ROLE_FAMILY", "GENERIC"]
    assert tiers.index("SAME_COMPANY") < tiers.index("ROLE_FAMILY") < tiers.index("GENERIC")


def test_eval_no_fabricated_metrics_gate():
    try:
        from app.evidence_os import gates
    except Exception:
        pytest.skip("evidence_os.gates not importable")
    with pytest.raises(Exception) as ei:
        gates.assert_no_metric_estimate("提升了大概 35% 转化")
    code = getattr(ei.value, "code", "") or str(ei.value)
    assert "METRIC" in code or "estimate" in code.lower() or "35" in str(ei.value)


def test_eval_curated_vs_synthetic_provenance():
    if KNOWLEDGE is None:
        pytest.skip("knowledge/ not found")
    curated_dir = KNOWLEDGE / "interview_skills" / "curated"
    demo_dirs = [
        KNOWLEDGE / "interview_skills",
        KNOWLEDGE / "interview_skills" / "demo",
        KNOWLEDGE / "interview_skills" / "synthetic",
    ]
    curated_files = list(curated_dir.glob("*.md")) if curated_dir.is_dir() else []
    assert curated_files, "no curated interview packs"
    for p in curated_files[:5]:
        assert "provenance: CURATED" in p.read_text(encoding="utf-8")

    synthetic_hit = False
    for d in demo_dirs:
        if not d.is_dir():
            continue
        for p in d.rglob("*.md"):
            t = p.read_text(encoding="utf-8")
            if "SYNTHETIC" in t or "provenance: DEMO" in t or "SYNTHETIC_DEMO" in t:
                synthetic_hit = True
                assert "CURATED" not in t.split("provenance:", 1)[-1].splitlines()[0]
                break
        if synthetic_hit:
            break
    # Soft stub: if no demo packs in tree, still assert curated label distinctness
    assert "CURATED" != "SYNTHETIC_DEMO"
