"""Service helpers that do not need a live Postgres or FastAPI."""
from __future__ import annotations

import sys
from pathlib import Path

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.evidence_os.helpers import competencies_for, priority_for, split_requirements


def test_split_requirements_dedupes():
    raw = """
    - Must have experience with RAG and evaluation
    - Must have experience with RAG and evaluation
    Preferred: agent orchestration
    short
    """
    lines = split_requirements(raw)
    assert len(lines) == 2
    assert "RAG" in lines[0]


def test_priority_hard_vs_preferred():
    assert priority_for("Must have Python") == "hard_gate"
    assert priority_for("Nice to have design sense") == "preferred"
    assert priority_for("Ship roadmaps with eng") == "core"


def test_competencies_detect_ai_pm():
    comps, kws = competencies_for("Own RAG retrieval quality and offline eval harness")
    assert "rag" in comps
    assert "model_evaluation" in comps
