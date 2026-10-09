"""Validate offline fixture manifests and schemas.

Usage (from repo root):
  python -m evals.benchmark.validate
"""

from __future__ import annotations

import sys
from pathlib import Path

from evals.benchmark.io_util import read_json
from evals.benchmark.paths import FIXTURES_DIR, MANIFESTS_DIR, PACKAGE_DIR

VALID_DECISIONS = {"KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"}


def _fail(message: str, errors: list[str]) -> None:
    errors.append(message)


def validate_manifest() -> list[str]:
    errors: list[str] = []
    manifest_path = MANIFESTS_DIR / "offline_fixture_manifest.json"
    if not manifest_path.exists():
        return [f"missing manifest: {manifest_path}"]
    manifest = read_json(manifest_path)
    suites = manifest.get("suites") or {}
    for suite, meta in suites.items():
        rel = meta.get("fixture")
        if not rel:
            _fail(f"{suite}: missing fixture path", errors)
            continue
        path = PACKAGE_DIR / rel
        if not path.exists():
            _fail(f"{suite}: fixture file missing: {path}", errors)
            continue
        data = read_json(path)
        if not isinstance(data, list):
            _fail(f"{suite}: fixture must be a JSON list", errors)
            continue
        expected_count = int(meta.get("count") or 0)
        if len(data) != expected_count:
            _fail(f"{suite}: manifest count {expected_count} != actual {len(data)}", errors)
        if suite == "jd":
            ids = [row.get("jd_id") for row in data]
            if len(ids) != len(set(ids)):
                _fail("jd: duplicate jd_id", errors)
            for row in data:
                if "expected" not in row or "offline_actual" not in row:
                    _fail(f"jd {row.get('jd_id')}: need expected + offline_actual", errors)
        elif suite == "match":
            for row in data:
                labels = row.get("expected_labels") or {}
                for decision in labels.values():
                    if decision not in VALID_DECISIONS:
                        _fail(f"match {row.get('case_id')}: invalid decision {decision}", errors)
                actual = row.get("offline_actual_labels") or {}
                for decision in actual.values():
                    if decision not in VALID_DECISIONS:
                        _fail(f"match {row.get('case_id')}: invalid actual decision {decision}", errors)
        elif suite == "rewrite":
            for row in data:
                if not row.get("unit_id"):
                    _fail("rewrite: missing unit_id", errors)
                if "offline_actual" not in row:
                    _fail(f"rewrite {row.get('unit_id')}: missing offline_actual", errors)
        elif suite == "interview":
            for row in data:
                if not row.get("question_id"):
                    _fail("interview: missing question_id", errors)
                if "expected" not in row or "offline_actual" not in row:
                    _fail(f"interview {row.get('question_id')}: need expected + offline_actual", errors)
    return errors


def main(argv: list[str] | None = None) -> int:
    del argv  # unused; kept for CLI symmetry
    errors = validate_manifest()
    if errors:
        print("VALIDATE FAILED")
        for item in errors:
            print(f" - {item}")
        return 1
    print("VALIDATE OK")
    print(f"manifest={MANIFESTS_DIR / 'offline_fixture_manifest.json'}")
    print(f"fixtures_root={FIXTURES_DIR}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
