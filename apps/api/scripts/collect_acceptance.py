"""岗位采集真实验收脚本（M1）。

跑真实 API + 真实公开来源，输出证据 JSON 到 docs/evaluation/overnight-sprint/。

覆盖用例：
1. 网页触发的一次真实采集（任务接口）
2. 重复采集 → DUPLICATE 去重
3. 空结果（关键词无匹配）
4. 来源返回异常（错误的招聘板标识 → 真实 HTTP 404）
5. 字段缺失 → NEEDS_REVIEW
6. 城市 / 实习条件 → 本地过滤如实排除
7. 用户取消采集
8. 批量保存后进入 JD 分析（导入正式岗位）
"""
from __future__ import annotations

import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
OUT = Path("docs/evaluation/overnight-sprint")
OUT.mkdir(parents=True, exist_ok=True)


def call(method: str, path: str, body: dict | None = None) -> dict:
    data = json.dumps(body or {}).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            return json.load(response)
    except urllib.error.HTTPError as exc:
        return {"__http_error": exc.code, "detail": exc.read().decode("utf-8", "replace")[:400]}


def run_task(payload: dict, *, poll_interval: float = 0.8, max_wait: float = 90.0) -> dict:
    task = call("POST", f"/api/v1/profiles/{PROFILE_ID}/job-ingest/collect-runs", payload)
    if "__http_error" in task:
        return task
    deadline = time.time() + max_wait
    snapshot = task
    while snapshot.get("status") == "RUNNING" and time.time() < deadline:
        time.sleep(poll_interval)
        snapshot = call("GET", f"/api/v1/job-ingest/collect-runs/{task['task_id']}")
    return snapshot


def short(jobs: list[dict], limit: int = 6) -> list[dict]:
    rows = []
    for job in jobs[:limit]:
        rows.append(
            {
                "source": job.get("source"),
                "company": job.get("company"),
                "role": job.get("role"),
                "location": job.get("location"),
                "employment_type": job.get("employment_type"),
                "result_status": job.get("result_status"),
                "needs_confirm": job.get("needs_confirm"),
                "source_url": job.get("source_url"),
            }
        )
    return rows


if len(sys.argv) < 3:
    print("usage: python collect_acceptance.py <base_url> <profile_id>")
    sys.exit(2)
PROFILE_ID = sys.argv[2]

started = datetime.now(timezone.utc).isoformat()
evidence: dict = {"started_at": started, "base_url": BASE, "profile_id": PROFILE_ID, "cases": []}


def record(name: str, data: dict) -> None:
    evidence["cases"].append({"case": name, **data})
    print(f"--- {name}: {json.dumps({k: v for k, v in data.items() if k != 'jobs_sample'}, ensure_ascii=False)[:400]}")


# 1 · 网页点击「开始采集」对应的真实任务
first = run_task(
    {
        "keywords": ["account executive", "designer"],
        "sources": ["remoteok", "remotive"],
        "limit": 6,
        "timeout_seconds": 90,
    }
)
# 1b · 把「新增」的岗位真正写进岗位库，才能在第 2 步验证重复采集被识别为 DUPLICATE
first_jobs = (first.get("result") or {}).get("jobs", [])
first_saveable = [job for job in first_jobs if job.get("result_status") in (None, "NEW", "UPDATED", "NEEDS_REVIEW")]
first_saved = (
    call("POST", f"/api/v1/profiles/{PROFILE_ID}/job-ingest/save-collected", {"jobs": first_saveable, "update_duplicates": False})
    if first_saveable
    else {"saved_count": 0, "skipped_count": 0}
)
record(
    "1-real-collect",
    {
        "task_status": first.get("status"),
        "elapsed_seconds": first.get("elapsed_seconds"),
        "totals": (first.get("result") or {}).get("totals"),
        "batch_save": {"attempted": len(first_saveable), "saved_count": first_saved.get("saved_count"), "skipped_count": first_saved.get("skipped_count")},
        "reports": [
            {"source": r["source"], "status": r["status"], "fetched": r.get("fetched"), "kept": r.get("count"), "latency_ms": r.get("latency_ms")}
            for r in (first.get("result") or {}).get("reports", [])
        ],
        "jobs_sample": short(first_jobs),
    },
)

# 2 · 再采集一次 → 应识别为已存在
second = run_task(
    {
        "keywords": ["account executive", "designer"],
        "sources": ["remoteok", "remotive"],
        "limit": 6,
        "timeout_seconds": 90,
    }
)
record(
    "2-dedupe",
    {
        "task_status": second.get("status"),
        "totals": (second.get("result") or {}).get("totals"),
        "jobs_sample": short((second.get("result") or {}).get("jobs", [])),
    },
)

# 3 · 空结果
empty = run_task({"keywords": ["zzz-nonexistent-role-9f8a7b"], "sources": ["remoteok"], "limit": 5, "timeout_seconds": 60})
record(
    "3-empty-result",
    {
        "task_status": empty.get("status"),
        "totals": (empty.get("result") or {}).get("totals"),
        "reports": [(r.get("source"), r.get("status"), r.get("note")) for r in (empty.get("result") or {}).get("reports", [])],
    },
)

# 4 · 来源异常（错误招聘板 → 真实 HTTP 404）
bad_source = run_task({"keywords": ["engineer"], "sources": ["greenhouse"], "greenhouse_boards": ["definitely-not-a-board-xyz"], "limit": 5, "timeout_seconds": 60})
record(
    "4-source-error",
    {
        "task_status": bad_source.get("status"),
        "totals": (bad_source.get("result") or {}).get("totals"),
        "reports": [(r.get("source"), r.get("status"), r.get("note")) for r in (bad_source.get("result") or {}).get("reports", [])],
    },
)

# 5 · 字段缺失 → NEEDS_REVIEW（Greenhouse 公开接口不返回公司名）
greenhouse = run_task({"keywords": ["engineer"], "sources": ["greenhouse"], "greenhouse_boards": ["stripe"], "limit": 3, "timeout_seconds": 90})
record(
    "5-missing-fields",
    {
        "task_status": greenhouse.get("status"),
        "totals": (greenhouse.get("result") or {}).get("totals"),
        "jobs_sample": short((greenhouse.get("result") or {}).get("jobs", [])),
    },
)

# 6 · 城市筛选 → 本地过滤并如实报告排除数量
filtered = run_task(
    {
        "keywords": ["engineer", "manager"],
        "sources": ["remoteok"],
        "location": "北京",
        "limit": 6,
        "timeout_seconds": 60,
    }
)
record(
    "6-city-filter",
    {
        "task_status": filtered.get("status"),
        "totals": (filtered.get("result") or {}).get("totals"),
        "reports": [(r.get("source"), r.get("status"), r.get("fetched"), r.get("filtered_out"), r.get("filter_mode")) for r in (filtered.get("result") or {}).get("reports", [])],
    },
)

# 7 · 用户取消
cancel_task = call(
    "POST",
    f"/api/v1/profiles/{PROFILE_ID}/job-ingest/collect-runs",
    {
        "keywords": ["engineer"],
        "sources": ["greenhouse", "greenhouse", "greenhouse"],
        "greenhouse_boards": ["stripe", "airbnb", "figma", "databricks", "reddit", "roblox"],
        "limit": 5,
        "timeout_seconds": 60,
    },
)
cancel_result = None
if "task_id" in cancel_task:
    time.sleep(1.2)
    call("POST", f"/api/v1/job-ingest/collect-runs/{cancel_task['task_id']}/cancel")
    deadline = time.time() + 60
    snapshot = cancel_task
    while snapshot.get("status") == "RUNNING" and time.time() < deadline:
        time.sleep(0.6)
        snapshot = call("GET", f"/api/v1/job-ingest/collect-runs/{cancel_task['task_id']}")
    cancel_result = snapshot
record(
    "7-cancel",
    {
        "task_status": (cancel_result or {}).get("status"),
        "totals": ((cancel_result or {}).get("result") or {}).get("totals"),
        "reports": [(r.get("source"), r.get("status")) for r in ((cancel_result or {}).get("result") or {}).get("reports", [])],
    },
)

# 8 · 批量保存 + 进入 JD 分析（导入正式岗位）
fresh = run_task({"keywords": ["service desk engineer"], "sources": ["remotive"], "limit": 2, "timeout_seconds": 90})
jobs = (fresh.get("result") or {}).get("jobs", [])
saveable = [job for job in jobs if job.get("result_status") in (None, "NEW", "UPDATED", "NEEDS_REVIEW")]
save_result = call("POST", f"/api/v1/profiles/{PROFILE_ID}/job-ingest/save-collected", {"jobs": saveable, "update_duplicates": False}) if saveable else {"skipped": True}
mission = None
candidate_id = None
if save_result.get("saved"):
    candidate_id = save_result["saved"][0]["candidate_ids"][0]
    imported = call("POST", f"/api/v1/candidate-jobs/{candidate_id}/import")
    mission = imported if "__http_error" not in imported else imported
record(
    "8-save-and-jd-analysis",
    {
        "collected": len(jobs),
        "saveable": len(saveable),
        "saved_count": save_result.get("saved_count"),
        "skipped_count": save_result.get("skipped_count"),
        "candidate_id": candidate_id,
        "import_result": {k: mission.get(k) for k in ("mission_id", "company", "role", "reused")} if isinstance(mission, dict) else None,
    },
)

evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
target = OUT / "m1-collect-acceptance.json"
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2), encoding="utf-8")
print(f"\n证据文件：{target}")
