"""Shared filesystem paths for the benchmark package."""

from __future__ import annotations

from pathlib import Path

PACKAGE_DIR = Path(__file__).resolve().parent
REPO_ROOT = PACKAGE_DIR.parents[1]
SCHEMAS_DIR = PACKAGE_DIR / "schemas"
MANIFESTS_DIR = PACKAGE_DIR / "manifests"
FIXTURES_DIR = PACKAGE_DIR / "fixtures"
ANNOTATIONS_DIR = PACKAGE_DIR / "annotations"
BASELINES_DIR = PACKAGE_DIR / "baselines"
REPORTS_DIR = PACKAGE_DIR / "reports"
PRIVATE_DIR = PACKAGE_DIR / "private"
RUNS_DIR = PACKAGE_DIR / "runs"
