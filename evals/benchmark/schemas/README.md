# Benchmark schemas

Machine-readable stubs for EVAL cases. Full JSON Schema validation of every fixture
field is intentionally light in phase 1; `python -m evals.benchmark.validate`
checks required ids, decision enums, and manifest counts.

Decision labels must match product code:
`KEEP_AND_HIGHLIGHT` / `KEEP` / `DEEMPHASIZE` / `OMIT`
(Chinese UI: 重点展示 / 保留 / 弱化 / 暂不放入).
