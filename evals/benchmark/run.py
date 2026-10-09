"""Run evaluation suites in offline / live / baseline modes.

Usage:
  python -m evals.benchmark.run --suite jd|match|rewrite|interview|all --mode offline|live|baseline
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Any

from evals.benchmark.io_util import new_run_id, read_json, utc_now_iso, write_json
from evals.benchmark.metrics import accuracy, field_exact_match, precision, recall, f1
from evals.benchmark.paths import FIXTURES_DIR, PACKAGE_DIR, REPORTS_DIR, REPO_ROOT, RUNS_DIR
from evals.benchmark import MODES, SUITE_NAMES


def _git_head() -> str:
    head_file = REPO_ROOT / ".git"
    # worktree: .git may be a file pointing elsewhere; best-effort only
    try:
        import subprocess

        out = subprocess.check_output(
            [
                "git",
                "-c",
                f"safe.directory={REPO_ROOT.as_posix()}",
                "rev-parse",
                "HEAD",
            ],
            cwd=str(REPO_ROOT),
            text=True,
            stderr=subprocess.DEVNULL,
        )
        return out.strip()
    except Exception:
        return "UNKNOWN"


def _provider_configured() -> bool:
    key = (os.environ.get("OPENAI_API_KEY") or "").strip()
    if not key or key.lower() in {"test", "dummy", "placeholder"}:
        return False
    return True


def _load_suite(suite: str) -> list[dict[str, Any]]:
    mapping = {
        "jd": FIXTURES_DIR / "jd" / "synthetic_offline.json",
        "match": FIXTURES_DIR / "match" / "synthetic_offline.json",
        "rewrite": FIXTURES_DIR / "rewrite" / "synthetic_offline.json",
        "interview": FIXTURES_DIR / "interview" / "synthetic_offline.json",
    }
    return list(read_json(mapping[suite]))


def _score_jd(rows: list[dict[str, Any]]) -> dict[str, Any]:
    fields = ["company", "role_title", "location", "years_experience", "education"]
    field_hits = {name: 0 for name in fields}
    compared = 0
    not_run = 0
    cases: list[dict[str, Any]] = []
    for row in rows:
        actual = row.get("offline_actual")
        expected = row.get("expected") or {}
        if actual is None:
            not_run += 1
            cases.append({"jd_id": row.get("jd_id"), "status": "NOT_RUN"})
            continue
        compared += 1
        row_ok = True
        detail = {}
        for name in fields:
            ok = field_exact_match(expected.get(name), actual.get(name))
            detail[name] = ok
            if ok:
                field_hits[name] += 1
            else:
                row_ok = False
        # list fields: exact set match for must_have
        must_ok = set(expected.get("must_have") or []) == set(actual.get("must_have") or [])
        detail["must_have_set"] = must_ok
        if not must_ok:
            row_ok = False
        cases.append(
            {
                "jd_id": row.get("jd_id"),
                "status": "PASSED" if row_ok else "FAILED",
                "field_exact": detail,
            }
        )
    metrics = {
        name: accuracy(field_hits[name], compared) for name in fields
    }
    metrics["must_have_set_accuracy"] = accuracy(
        sum(1 for c in cases if c.get("field_exact", {}).get("must_have_set")),
        compared,
    )
    return {
        "suite": "jd",
        "planned_note": "PLAN=30 independent JDs; ACTUAL fixtures below",
        "fixture_count": len(rows),
        "compared": compared,
        "not_run": not_run,
        "metrics": metrics,
        "cases": cases,
    }


def _score_match(rows: list[dict[str, Any]]) -> dict[str, Any]:
    labels = ["KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"]
    confusion = {gold: {pred: 0 for pred in labels} for gold in labels}
    compared_items = 0
    correct = 0
    critical_omit_errors = 0
    cases: list[dict[str, Any]] = []
    for row in rows:
        expected = row.get("expected_labels") or {}
        actual = row.get("offline_actual_labels")
        if actual is None:
            cases.append({"case_id": row.get("case_id"), "status": "NOT_RUN"})
            continue
        high = set(row.get("expected_high_priority_experience_ids") or [])
        case_ok = True
        for exp_id, gold in expected.items():
            pred = actual.get(exp_id)
            if pred is None:
                case_ok = False
                continue
            if pred not in labels or gold not in labels:
                case_ok = False
                continue
            confusion[gold][pred] += 1
            compared_items += 1
            if pred == gold:
                correct += 1
            else:
                case_ok = False
            if exp_id in high and pred == "OMIT" and gold != "OMIT":
                critical_omit_errors += 1
        cases.append(
            {
                "case_id": row.get("case_id"),
                "status": "PASSED" if case_ok else "FAILED",
                "critical_selection_error": critical_omit_errors > 0,
            }
        )
    per_class = {}
    for label in labels:
        tp = confusion[label][label]
        fp = sum(confusion[other][label] for other in labels if other != label)
        fn = sum(confusion[label][other] for other in labels if other != label)
        p = precision(tp, fp)
        r = recall(tp, fn)
        per_class[label] = {"precision": p, "recall": r, "f1": f1(p, r)}
    return {
        "suite": "match",
        "planned_note": "PLAN=30 JD x resume tasks; ACTUAL fixtures below",
        "fixture_count": len(rows),
        "compared_items": compared_items,
        "metrics": {
            "accuracy": accuracy(correct, compared_items),
            "critical_omit_error_count": critical_omit_errors,
            "per_class": per_class,
        },
        "confusion_matrix": confusion,
        "cases": cases,
    }


def _score_rewrite(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compared = 0
    fact_error_flags = 0
    unsupported_number = 0
    cases: list[dict[str, Any]] = []
    for row in rows:
        actual = row.get("offline_actual")
        if actual is None:
            cases.append({"unit_id": row.get("unit_id"), "status": "NOT_RUN"})
            continue
        compared += 1
        crit = bool(actual.get("critical_fact_error"))
        unsup = bool(actual.get("unsupported_number"))
        expected_crit = bool(row.get("critical_fact_error"))
        # Offline checker verifies the fixture's declared error flag is preserved.
        ok = crit == expected_crit
        if crit:
            fact_error_flags += 1
        if unsup:
            unsupported_number += 1
        cases.append(
            {
                "unit_id": row.get("unit_id"),
                "status": "PASSED" if ok else "FAILED",
                "critical_fact_error": crit,
                "unsupported_number": unsup,
                "human_scores": "UNRATED",
            }
        )
    return {
        "suite": "rewrite",
        "planned_note": "PLAN=90 experience-level units; ACTUAL fixtures below; human 1-5 scores UNRATED",
        "fixture_count": len(rows),
        "compared": compared,
        "metrics": {
            "critical_fact_error_rate": accuracy(fact_error_flags, compared),
            "unsupported_number_rate": accuracy(unsupported_number, compared),
            "human_dimensions": "UNRATED",
            "adoption_rate": None,
        },
        "cases": cases,
    }


def _score_interview(rows: list[dict[str, Any]]) -> dict[str, Any]:
    compared = 0
    jd_ok = 0
    resume_ok = 0
    fact_errors = 0
    cases: list[dict[str, Any]] = []
    for row in rows:
        actual = row.get("offline_actual")
        expected = row.get("expected") or {}
        if actual is None:
            cases.append({"question_id": row.get("question_id"), "status": "NOT_RUN"})
            continue
        compared += 1
        checks = {}
        for key in (
            "jd_grounded",
            "resume_grounded",
            "uses_target_company_intel_only",
            "synthetic_demo_forbidden",
            "duplicate",
        ):
            checks[key] = bool(actual.get(key)) == bool(expected.get(key))
        if expected.get("reference_answer_fact_error") is not None:
            checks["reference_answer_fact_error"] = bool(
                actual.get("reference_answer_fact_error")
            ) == bool(expected.get("reference_answer_fact_error"))
            if actual.get("reference_answer_fact_error"):
                fact_errors += 1
        if actual.get("jd_grounded"):
            jd_ok += 1
        if actual.get("resume_grounded"):
            resume_ok += 1
        ok = all(checks.values())
        cases.append(
            {
                "question_id": row.get("question_id"),
                "status": "PASSED" if ok else "FAILED",
                "checks": checks,
            }
        )
    return {
        "suite": "interview",
        "planned_note": "PLAN=10 cases / 50 questions; ACTUAL fixtures below",
        "fixture_count": len(rows),
        "compared": compared,
        "metrics": {
            "jd_grounded_rate": accuracy(jd_ok, compared),
            "resume_grounded_rate": accuracy(resume_ok, compared),
            "reference_answer_fact_error_count": fact_errors,
        },
        "cases": cases,
    }


SCORERS = {
    "jd": _score_jd,
    "match": _score_match,
    "rewrite": _score_rewrite,
    "interview": _score_interview,
}


def _not_run_payload(suite: str, mode: str, reason: str) -> dict[str, Any]:
    return {
        "suite": suite,
        "mode": mode,
        "status": "NOT_RUN",
        "reason": reason,
        "fixture_count": 0,
        "cases": [],
    }


def run_suite(suite: str, mode: str) -> dict[str, Any]:
    if mode == "offline":
        rows = _load_suite(suite)
        result = SCORERS[suite](rows)
        result["mode"] = "offline"
        result["status"] = "COMPLETED"
        result["provider_called"] = False
        return result

    if mode in {"live", "baseline"}:
        if not _provider_configured():
            return _not_run_payload(
                suite,
                mode,
                "OPENAI_API_KEY missing or placeholder; refusing to invent live results",
            )
        # Consented live corpora are not checked in yet.
        return _not_run_payload(
            suite,
            mode,
            "No consented live sample corpus / frozen baseline prompt pack in repo yet",
        )
    return _not_run_payload(suite, mode, f"unknown mode {mode}")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Career OS evaluation runner")
    parser.add_argument("--suite", required=True, choices=list(SUITE_NAMES))
    parser.add_argument("--mode", required=True, choices=list(MODES))
    parser.add_argument("--run-id", default=None)
    args = parser.parse_args(argv)

    suites = ["jd", "match", "rewrite", "interview"] if args.suite == "all" else [args.suite]
    run_id = args.run_id or new_run_id(prefix=f"{args.mode}-{args.suite}")
    suite_results = [run_suite(name, args.mode) for name in suites]

    payload = {
        "run_id": run_id,
        "created_at": utc_now_iso(),
        "git_head": _git_head(),
        "mode": args.mode,
        "suite_arg": args.suite,
        "provider_called": any(r.get("provider_called") for r in suite_results),
        "suites": suite_results,
    }

    RUNS_DIR.mkdir(parents=True, exist_ok=True)
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    run_path = RUNS_DIR / f"{run_id}.json"
    report_path = REPORTS_DIR / f"{run_id}.summary.json"
    write_json(run_path, payload)

    summary = {
        "run_id": run_id,
        "created_at": payload["created_at"],
        "git_head": payload["git_head"],
        "mode": args.mode,
        "suites": [
            {
                "suite": item.get("suite"),
                "status": item.get("status"),
                "fixture_count": item.get("fixture_count"),
                "reason": item.get("reason"),
                "metrics": item.get("metrics"),
            }
            for item in suite_results
        ],
        "raw_run_path": str(run_path.relative_to(REPO_ROOT)) if run_path.is_relative_to(REPO_ROOT) else str(run_path),
        "notes": [
            "Offline scores use synthetic fixtures only.",
            "Do not report these numbers as product quality on real JDs/resumes.",
        ],
    }
    write_json(report_path, summary)
    print(f"RUN_ID={run_id}")
    print(f"mode={args.mode} suites={[s.get('suite') for s in suite_results]}")
    for item in suite_results:
        print(
            f" - {item.get('suite')}: status={item.get('status')} "
            f"fixtures={item.get('fixture_count')} reason={item.get('reason')}"
        )
    print(f"summary={report_path}")
    # Offline completed harness is success even if a fixture intentionally flags errors.
    if args.mode == "offline":
        return 0
    # live/baseline without data still exits 0 with NOT_RUN (safe exit), non-zero only on crash
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
