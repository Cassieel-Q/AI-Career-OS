from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT))

from evals.benchmark import validate as validate_mod
from evals.benchmark import run as run_mod
from evals.benchmark.paths import MANIFESTS_DIR, REPORTS_DIR


def test_validate_offline_manifest_ok():
    assert validate_mod.validate_manifest() == []
    assert validate_mod.main([]) == 0


def test_offline_run_all_writes_summary(tmp_path, monkeypatch):
    # Keep artifacts under package reports/runs (gitignored runs ok).
    code = run_mod.main(["--suite", "all", "--mode", "offline", "--run-id", "test-offline-all"])
    assert code == 0
    summary = REPORTS_DIR / "test-offline-all.summary.json"
    assert summary.exists()
    payload = json.loads(summary.read_text(encoding="utf-8"))
    assert payload["mode"] == "offline"
    assert len(payload["suites"]) == 4
    assert all(item["status"] == "COMPLETED" for item in payload["suites"])
    assert all(item["fixture_count"] == 2 for item in payload["suites"])


def test_live_mode_without_key_is_not_run(monkeypatch):
    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    result = run_mod.run_suite("jd", "live")
    assert result["status"] == "NOT_RUN"
    assert "OPENAI_API_KEY" in result["reason"]


def test_manifest_plan_vs_actual_is_honest():
    manifest = json.loads(
        (MANIFESTS_DIR / "offline_fixture_manifest.json").read_text(encoding="utf-8")
    )
    plan = manifest["plan_vs_actual"]
    assert plan["EVAL-JD"]["planned"] == 30
    assert plan["EVAL-JD"]["actual_fixtures"] == 2
    assert plan["EVAL-REWRITE"]["planned"] == 90
    assert plan["EVAL-REWRITE"]["actual_fixtures"] == 2
