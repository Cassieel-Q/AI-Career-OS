"""Summarize an existing evaluation run. Does not call providers.

Usage:
  python -m evals.benchmark.report --run-id <RUN_ID>
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from evals.benchmark.io_util import read_json
from evals.benchmark.paths import REPORTS_DIR, RUNS_DIR


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="AI Career OS evaluation report")
    parser.add_argument("--run-id", required=True)
    args = parser.parse_args(argv)

    summary_path = REPORTS_DIR / f"{args.run_id}.summary.json"
    run_path = RUNS_DIR / f"{args.run_id}.json"
    if summary_path.exists():
        payload = read_json(summary_path)
        print(f"RUN_ID={payload.get('run_id')}")
        print(f"created_at={payload.get('created_at')}")
        print(f"git_head={payload.get('git_head')}")
        print(f"mode={payload.get('mode')}")
        for suite in payload.get("suites") or []:
            print(
                f"suite={suite.get('suite')} status={suite.get('status')} "
                f"fixtures={suite.get('fixture_count')} reason={suite.get('reason')}"
            )
            metrics = suite.get("metrics")
            if metrics:
                print(f"  metrics={metrics}")
        for note in payload.get("notes") or []:
            print(f"note: {note}")
        print(f"summary_path={summary_path}")
        return 0

    if run_path.exists():
        payload = read_json(run_path)
        print(f"RUN_ID={payload.get('run_id')} (raw run; summary missing)")
        print(payload)
        return 0

    print(f"NOT_FOUND run-id={args.run_id}")
    print(f"looked for {summary_path} and {run_path}")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
