"""真实公开招聘来源在线采集验证。

对每个适用规则允许访问的公开来源发**真实请求**，并记录：

- 来源名称 / 真实请求地址 / 请求时间 / 接口状态
- 原始返回数量 / 成功解析数量 / 符合搜索条件数量 / 重复数量 / 新增入库数量 / 错误数量
- 采集耗时 / 可追溯的岗位 ID

严格区分两件事：

- **成功获取真实岗位**：接口真的返回了岗位，且落库；
- **成功获取目标岗位**：在真实岗位里进一步命中「AI 产品 / 实习」目标条件。

禁止把采集时间当成岗位发布时间，禁止仅凭成功返回就宣称岗位仍在招。
不修改关键词凑数、不虚构岗位、不用演示数据冒充真实结果。

运行::

    cd apps/api && .venv/Scripts/python.exe ../../evals/job-collection-v1/run_live_smoke.py --api http://127.0.0.1:8100
"""
from __future__ import annotations

import argparse
import json
import pathlib
import re
import sys
import time
from datetime import datetime, timezone

import httpx

HERE = pathlib.Path(__file__).resolve().parent
API_ROOT = HERE.parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

# ------------------------------------------------------------------ 来源配置
#: 只选适用规则允许访问、且真实存在的公开招聘来源。
SOURCES: list[dict] = [
    {
        "source": "remoteok",
        "label": "RemoteOK 公开接口",
        "endpoint": "https://remoteok.com/api",
        "boards": [],
        "companies": [],
    },
    {
        "source": "remotive",
        "label": "Remotive 公开接口",
        "endpoint": "https://remotive.com/api/remote-jobs",
        "boards": [],
        "companies": [],
    },
    {
        "source": "greenhouse",
        "label": "Greenhouse 公开招聘板",
        "endpoint": "https://boards-api.greenhouse.io/v1/boards/{board}/jobs?content=true",
        "boards": ["anthropic", "figma", "stripe"],
        "companies": [],
    },
    {
        "source": "lever",
        "label": "Lever 公开招聘板",
        "endpoint": "https://api.lever.co/v0/postings/{company}?mode=json",
        "boards": [],
        "companies": ["palantir", "leverdemo"],
    },
]

#: 宽关键词：验证采集技术链路能拿到真实岗位（不保证是 AI 产品岗）
BROAD_KEYWORDS = ["ai", "product"]
#: 目标关键词：用户的真实需求——AI 产品方向（含实习）
TARGET_KEYWORDS = ["ai product manager", "product manager intern", "ai product"]

CORE_FIELDS = ("company", "role", "location", "jd", "source_url", "employment_type", "posted_at")


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


def log(msg: str) -> None:
    print(msg, flush=True)


def local_client() -> httpx.Client:
    """访问本机后端必须绕过环境代理。

    本机 Shell 环境里设置了 ``HTTP_PROXY``，httpx 默认 ``trust_env=True`` 会把
    ``127.0.0.1:8100`` 的请求也发给代理，代理转发后把路径写成绝对形式
    （``http://127.0.0.1:8100/api/...``），后端就会返回 404。
    这不是应用缺陷，但会让采集脚本误报，因此显式关掉。
    """
    return httpx.Client(timeout=180.0, trust_env=False)


def call(client: httpx.Client, method: str, path: str, **kwargs) -> tuple[int, object]:
    try:
        response = client.request(method, f"{args.api}{path}", **kwargs)
    except httpx.HTTPError as exc:
        return 0, {"error": f"{exc.__class__.__name__}: {exc}"}
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, {"_text": response.text[:500]}


def probe_raw_candidates(source: dict) -> tuple[int | None, str]:
    """直接请求公开接口统计原始返回条数（每个来源只做一次探测，不重复打接口）。

    返回 ``(条数, 说明)``；条数为 None 表示探测失败（如实记录，不猜）。
    """
    name = source["source"]
    try:
        if name == "remoteok":
            payload = httpx.get(source["endpoint"], timeout=30.0).json()
            # RemoteOK 数组首条是法律声明，不是岗位
            return (max(0, len(payload) - 1) if isinstance(payload, list) else None), "公开数组（扣除首条法律声明）"
        if name == "remotive":
            payload = httpx.get(source["endpoint"] + "?limit=1", timeout=30.0).json()
            total = (payload or {}).get("job-count") if isinstance(payload, dict) else None
            return total, "接口返回的 job-count 总量"
        if name == "greenhouse":
            total = 0
            for board in source["boards"]:
                got = httpx.get(source["endpoint"].format(board=board), timeout=30.0).json()
                jobs = (got or {}).get("jobs") if isinstance(got, dict) else None
                if isinstance(jobs, list):
                    total += len(jobs)
                else:
                    return None, f"{board} 返回结构里没有 jobs 数组"
            return total, f"招聘板 {', '.join(source['boards'])} 的岗位条目合计"
        if name == "lever":
            total = 0
            for company in source["companies"]:
                got = httpx.get(source["endpoint"].format(company=company), timeout=30.0).json()
                total += len(got) if isinstance(got, list) else 0
            return total, f"企业 {', '.join(source['companies'])} 的岗位条目合计"
    except Exception as exc:  # noqa: BLE001 - 探测失败如实记录
        return None, f"探测失败：{exc.__class__.__name__}"
    return None, "未知来源"


def ai_product_guess(job: dict) -> tuple[bool, str]:
    """Agent 对「是否 AI 产品相关」的**预判**（不是人工金标准）。

    规则：岗位名里同时出现 AI/ML 语义与产品语义，或岗位名直接是 AI 产品类。
    """
    role = (job.get("role") or "").lower()
    jd = (job.get("jd") or "").lower()
    ai_hit = bool(re.search(r"\b(ai|a\.i\.|ml|llm|machine learning|人工智能|大模型)\b", role)) or "人工智能" in role
    product_hit = bool(re.search(r"\b(product|pm|产品经理|产品)\b", role))
    if ai_hit and product_hit:
        return True, "岗位名同时命中 AI 与产品语义"
    if product_hit and re.search(r"\b(ai|ml|llm|model|人工智能|大模型)\b", jd[:1500]):
        return True, "岗位名为产品类且 JD 前段出现 AI/大模型语义"
    return False, "未同时命中 AI 与产品语义"


def main() -> int:
    parser = argparse.ArgumentParser(description="真实公开招聘来源在线采集验证")
    parser.add_argument("--api", default="http://127.0.0.1:8100", help="AI Career OS 后端地址")
    parser.add_argument("--limit", type=int, default=30, help="每个来源每次采集的岗位上限")
    parser.add_argument("--skip-save", action="store_true", help="只采集不入库（用于只读冒烟）")
    global args
    args = parser.parse_args()

    dataset_id = (HERE / ".dataset_id").read_text(encoding="utf-8").strip() if (HERE / ".dataset_id").exists() else None

    run: dict = {
        "schema": "ai-career-os/job-collection-smoke@1",
        "dataset_id": dataset_id,
        "started_at": now(),
        "api": args.api,
        "requests": [],
        "sources": [],
        "saves": [],
        "notes": [
            "采集时间（collected_at）仅代表本次抓取时刻，不代表岗位发布时间。",
            "接口成功返回不代表该岗位此刻仍在招；仍在招需用户点开原始链接自行确认。",
        ],
    }

    with local_client() as client:
        # ---------------------------------------------------------- 建隔离档案
        status, profile = call(client, "POST", "/api/v1/profiles/draft", json={})
        if status not in {200, 201}:
            log(f"[FATAL] 建档失败 HTTP {status}: {profile}")
            return 1
        profile_id = (profile or {}).get("profile_id") or (profile or {}).get("id")
        run["profile_id"] = str(profile_id)
        log(f"[SETUP] 隔离数据集={dataset_id} 测试档案={profile_id}")

        for source in SOURCES:
            name = source["source"]
            log(f"\n=== {name} ({source['label']}) ===")

            # ---------------------------------------------------- 原始条数探测
            raw_count, raw_note = probe_raw_candidates(source)
            log(f"  原始返回条数: {raw_count} ({raw_note})")

            for phase, keywords in (("BROAD", BROAD_KEYWORDS), ("TARGET", TARGET_KEYWORDS)):
                payload = {
                    "sources": [name],
                    "keywords": keywords,
                    "limit": args.limit,
                    "greenhouse_boards": source["boards"],
                    "lever_companies": source["companies"],
                }
                requested_at = now()
                started = time.monotonic()
                status, result = call(client, "POST", "/api/v1/job-ingest/collect", json=payload)
                elapsed_ms = int((time.monotonic() - started) * 1000)
                result = result if isinstance(result, dict) else {}
                reports = result.get("reports") or []
                jobs = result.get("jobs") or []
                totals = result.get("totals") or {}
                report = reports[0] if reports else {}

                entry = {
                    "source": name,
                    "label": source["label"],
                    "endpoint": source["endpoint"].format(board=source["boards"][0] if source["boards"] else "", company=source["companies"][0] if source["companies"] else ""),
                    "phase": phase,
                    "keywords": keywords,
                    "limit": args.limit,
                    "requested_at": requested_at,
                    "http_status": status,
                    "interface_status": report.get("status") or result.get("status"),
                    "raw_candidates": raw_count,
                    "raw_candidates_note": raw_note,
                    "fetched": report.get("fetched", len(jobs)),
                    "parsed_jobs": len(jobs),
                    "matched_jobs": report.get("count", len(jobs)),
                    "cross_source_duplicates": totals.get("cross_source_duplicates", 0),
                    "new": totals.get("new", len(jobs)),
                    "duplicate": totals.get("duplicate", 0),
                    "updated": totals.get("updated", 0),
                    "needs_review": totals.get("needs_review", 0),
                    "failed": totals.get("failed", 0),
                    "error_count": len(report.get("errors") or []),
                    "errors": report.get("errors") or [],
                    "note": report.get("note") or "",
                    "latency_ms": elapsed_ms,
                    "job_ids": [job.get("dedupe_key") for job in jobs],
                    "jobs": jobs,
                }
                run["requests"].append({k: v for k, v in entry.items() if k != "jobs"})
                run["sources"].append(entry)
                log(f"  [{phase}] HTTP {status} status={entry['interface_status']} 解析={entry['parsed_jobs']} "
                    f"命中={entry['matched_jobs']} 耗时={elapsed_ms}ms err={entry['error_count']}")

                if not jobs or args.skip_save:
                    continue

                # ------------------------------------------------ 入库（第一条）
                status, saved = call(
                    client,
                    "POST",
                    f"/api/v1/profiles/{profile_id}/job-ingest/save-collected",
                    json={"jobs": jobs, "update_duplicates": False},
                )
                saved = saved if isinstance(saved, dict) else {}
                save_entry = {
                    "source": name,
                    "phase": phase,
                    "http_status": status,
                    "saved_count": saved.get("saved_count", 0),
                    "updated_count": saved.get("updated_count", 0),
                    "skipped_count": saved.get("skipped_count", 0),
                    "skip_reasons": [item.get("reason") for item in (saved.get("skipped") or [])],
                    "candidate_ids": [cid for item in (saved.get("saved") or []) for cid in item.get("candidate_ids", [])],
                }
                run["saves"].append(save_entry)
                log(f"     入库: 新增={save_entry['saved_count']} 更新={save_entry['updated_count']} 跳过={save_entry['skipped_count']}")

                # ------------------------------------------------ 去重：立刻再采一次
                status2, result2 = call(client, "POST", "/api/v1/job-ingest/collect", json=payload)
                result2 = result2 if isinstance(result2, dict) else {}
                jobs2 = result2.get("jobs") or []
                status3, saved2 = call(
                    client,
                    "POST",
                    f"/api/v1/profiles/{profile_id}/job-ingest/save-collected",
                    json={"jobs": jobs2, "update_duplicates": False},
                )
                saved2 = saved2 if isinstance(saved2, dict) else {}
                entry["recollect"] = {
                    "parsed_jobs": len(jobs2),
                    "saved_count": saved2.get("saved_count", 0),
                    "skipped_count": saved2.get("skipped_count", 0),
                    "skip_reasons": [item.get("reason") for item in (saved2.get("skipped") or [])],
                    "same_fingerprint": {j["dedupe_key"]: j["content_hash"] for j in jobs}
                    == {j["dedupe_key"]: j["content_hash"] for j in jobs2},
                }
                log(f"     去重: 第二次解析={len(jobs2)} 新增={saved2.get('saved_count', 0)} "
                    f"跳过={saved2.get('skipped_count', 0)} 指纹一致={entry['recollect']['same_fingerprint']}")

    run["finished_at"] = now()

    # ------------------------------------------------------------ 人工审核清单
    seen: set[str] = set()
    review: list[dict] = []
    for entry in run["sources"]:
        for job in entry.get("jobs") or []:
            key = job.get("dedupe_key") or job.get("source_url")
            if not key or key in seen:
                continue
            seen.add(key)
            related, why = ai_product_guess(job)
            missing = [f for f in CORE_FIELDS if not (job.get(f) or "" if isinstance(job.get(f), str) else job.get(f))]
            review.append(
                {
                    "company": job.get("company") or "",
                    "role": job.get("role") or "",
                    "location": job.get("location") or "",
                    "is_intern": job.get("employment_type") == "INTERN",
                    "employment_type": job.get("employment_type"),
                    "ai_product_relevant_agent_guess": related,
                    "ai_product_relevant_reason": why,
                    "ai_product_relevant_human_label": None,  # 待人工确认
                    "relevance_status": "UNREVIEWED",
                    "source_url": job.get("source_url") or "",
                    "jd_excerpt": (job.get("jd") or "")[:300],
                    "posted_at": job.get("posted_at"),
                    "collected_at": job.get("collected_at"),
                    "source": job.get("source"),
                    "dedupe_key": job.get("dedupe_key"),
                    "needs_confirm_fields": job.get("needs_confirm") or [],
                    "missing_core_fields": missing,
                    "still_open": "UNKNOWN — 需用户点开原始链接自行确认",
                }
            )

    run["review_sample_size"] = len(review)
    run["review_sample_sufficient"] = len(review) >= 20

    (HERE / "runs").mkdir(exist_ok=True)
    (HERE / "review").mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    out = HERE / "runs" / f"live-{stamp}.json"
    out.write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")
    (HERE / "review" / "review-list.json").write_text(
        json.dumps(review, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (HERE / "runs" / "latest.json").write_text(json.dumps(run, ensure_ascii=False, indent=2), encoding="utf-8")

    log(f"\n[DONE] 运行记录: {out}")
    log(f"[DONE] 审核样本: {len(review)} 条（充足={run['review_sample_sufficient']}）")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
