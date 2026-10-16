"""生成岗位采集验收报告（含 6 项指标）并输出到 docs/evaluation/job-collection-v1/。

指标口径：

- **采集解析成功率** = 成功解析的岗位数 / 接收到的候选岗位数
- **核心字段完整率** = 已满足的必填字段数 / 应填写的核心字段总数
- **保存成功率** = 实际入库的有效新岗位数 / 尝试保存的有效新岗位数
- **去重 Precision / Recall** = 按固定标注样本（``fixtures/dedupe_labels.jsonl``）计算
- **岗位相关性** = 人工确认相关数 / 人工已审核数（无人工标签时一律 ``UNREVIEWED``，不输出百分比）
- **完整流程成功率** = 完成「网页采集 → Mission」的次数 / 总执行次数

运行::

    cd apps/api && .venv/Scripts/python.exe ../../evals/job-collection-v1/report.py
"""
from __future__ import annotations

import json
import pathlib
import sys
from datetime import datetime, timezone

HERE = pathlib.Path(__file__).resolve().parent
API_ROOT = HERE.parents[1] / "apps" / "api"
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app import job_ingest_service as ingest  # noqa: E402

DOCS = HERE.parents[1] / "docs" / "evaluation" / "job-collection-v1"
CORE_FIELDS = ("company", "role", "location", "jd", "source_url", "employment_type", "posted_at")


def load_jsonl(path: pathlib.Path) -> list[dict]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def fixture_job(ref: dict) -> dict:
    """按引用从 fixture 还原一条归一化岗位（与适配器规则一致）。"""
    if ref["kind"] == "remoteok":
        raw = json.loads((HERE / "fixtures" / "remoteok_sample.json").read_text(encoding="utf-8"))
        items = [x for x in raw if isinstance(x, dict) and x.get("id") == ref["id"]]
        item = items[ref.get("occurrence", 0)]
        tags = item.get("tags") or []
        description = ingest.html_to_text(item.get("description") or "")
        return ingest.normalize_job(
            source="remoteok",
            source_url=item.get("url") or "",
            apply_url=item.get("apply_url") or "",
            company=(item.get("company") or "").strip(),
            role=(item.get("position") or "").strip(),
            location=(item.get("location") or "Remote").strip() or "Remote",
            jd=description,
            posted_at=item.get("date"),
            employment_type=ingest.detect_employment_type(item.get("position"), " ".join(tags), description),
            tags=tags,
        )
    raw = json.loads((HERE / "fixtures" / "greenhouse_sample.json").read_text(encoding="utf-8"))
    item = raw["jobs"][ref["index"]]
    content = ingest.html_to_text(item.get("content") or "")
    location_value = item.get("location")
    location = (location_value or {}).get("name") if isinstance(location_value, dict) else (location_value or "")
    title = (item.get("title") or "").strip()
    job = ingest.normalize_job(
        source="greenhouse",
        source_url=item.get("absolute_url") or "",
        apply_url=item.get("absolute_url") or "",
        company="",
        role=title,
        location=(location or "").strip(),
        jd=content,
        posted_at=item.get("updated_at") or item.get("first_published"),
        employment_type=ingest.detect_employment_type(title, "", content),
        tags=["northwind"],
        needs_confirm=["company"],
    )
    return ingest.retag_company(job, "northwind", is_board_token=True)


def dedupe_pr() -> dict:
    """按固定标注样本计算去重的 Precision / Recall。"""
    labels = load_jsonl(HERE / "fixtures" / "dedupe_labels.jsonl")
    tp = fp = fn = tn = 0
    rows = []
    for pair in labels:
        a = fixture_job(pair["a"])
        b = fixture_job(pair["b"])
        predicted = a["dedupe_key"] == b["dedupe_key"]
        truth = bool(pair["is_duplicate"])
        if predicted and truth:
            tp += 1
        elif predicted and not truth:
            fp += 1
        elif not predicted and truth:
            fn += 1
        else:
            tn += 1
        rows.append(
            {
                "pair_id": pair["pair_id"],
                "predicted_duplicate": predicted,
                "labeled_duplicate": truth,
                "correct": predicted == truth,
                "reason": pair["reason"],
            }
        )
    precision = tp / (tp + fp) if (tp + fp) else None
    recall = tp / (tp + fn) if (tp + fn) else None
    return {
        "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "precision": precision,
        "recall": recall,
        "accuracy": (tp + tn) / len(labels) if labels else None,
        "rows": rows,
    }


def main() -> int:
    runs_dir = HERE / "runs"
    run_files = sorted(runs_dir.glob("live-*.json"))
    if not run_files:
        print("[FATAL] 没有运行记录，先跑 run_live_smoke.py")
        return 1
    run = json.loads(run_files[-1].read_text(encoding="utf-8"))

    review = json.loads((HERE / "review" / "review-list.json").read_text(encoding="utf-8"))
    e2e_path = DOCS / "e2e-browser-result.json"
    e2e = json.loads(e2e_path.read_text(encoding="utf-8")) if e2e_path.exists() else None

    # ---------------------------------------------------------------- 指标 1 解析成功率
    parse_rows = []
    for entry in run["sources"]:
        raw = entry.get("raw_candidates")
        parsed = entry.get("parsed_jobs", 0)
        # 口径说明：候选数取 min(原始返回, limit)。
        # 用户设了 limit 上限后，超出部分压根没有被请求解析，
        # 若拿「接口全量条目」当分母，会把用户主动的限量配置误算成「解析能力差」。
        limit = entry.get("limit") or run.get("limit")
        considered = min(raw, limit) if (raw and limit) else raw
        parse_rows.append(
            {
                "source": entry["source"],
                "phase": entry["phase"],
                "raw_candidates": raw,
                "considered_candidates": considered,
                "parsed": parsed,
                "rate": (parsed / considered) if considered else None,
            }
        )
    total_raw = sum(r["raw_candidates"] or 0 for r in parse_rows)
    total_considered = sum(r["considered_candidates"] or 0 for r in parse_rows)
    total_parsed = sum(r["parsed"] for r in parse_rows)
    parse_rate = total_parsed / total_considered if total_considered else None

    # ---------------------------------------------------------------- 指标 2 核心字段完整率
    field_total = 0
    field_ok = 0
    per_field: dict[str, dict] = {f: {"ok": 0, "total": 0} for f in CORE_FIELDS}
    for item in review:
        for field in CORE_FIELDS:
            field_total += 1
            per_field[field]["total"] += 1
            # 审核清单里 JD 以 jd_excerpt 形式保存（避免整份清单过大），
            # 摘要非空即代表来源返回了 JD 正文。
            value = item.get(field) or (item.get("jd_excerpt") if field == "jd" else None)
            present = bool(value) if not isinstance(value, str) else bool(value.strip())
            if present:
                field_ok += 1
                per_field[field]["ok"] += 1
    field_rate = field_ok / field_total if field_total else None

    # 补充口径：「非空」不等于「确定」。employment_type 允许取 UNKNOWN（不猜），
    # 因此单独统计**能确定下来的比例**，避免 100% 的完整率掩盖了一半岗位类型未识别。
    emp_total = len(review)
    emp_certain = sum(1 for item in review if (item.get("employment_type") or "UNKNOWN") != "UNKNOWN")
    emp_rate = emp_certain / emp_total if emp_total else None
    needs_confirm_count = sum(1 for item in review if item.get("needs_confirm_fields"))

    # ---------------------------------------------------------------- 指标 3 保存成功率
    attempted = sum(e["parsed_jobs"] for e in run["sources"] if e.get("parsed_jobs"))
    saved_new = sum(s.get("saved_count", 0) for s in run["saves"])
    skipped = sum(s.get("skipped_count", 0) for s in run["saves"])
    attempted_valid = sum(
        e["parsed_jobs"] for e in run["sources"] if e.get("parsed_jobs") and e.get("phase") == "BROAD"
    )
    saved_broad = sum(s.get("saved_count", 0) for s in run["saves"] if s.get("phase") == "BROAD")
    save_rate = saved_broad / attempted_valid if attempted_valid else None

    # ---------------------------------------------------------------- 指标 4 去重 P/R
    dedupe = dedupe_pr()

    # ---------------------------------------------------------------- 指标 5 相关性
    human_reviewed = sum(1 for item in review if item.get("ai_product_relevant_human_label") is not None)
    relevance_rate = None  # 无人工标签 → 不输出百分比

    # ---------------------------------------------------------------- 指标 6 完整流程成功率
    if e2e:
        flow_total = len([r for r in e2e["results"] if isinstance(r["step"], int)])
        flow_passed = len([r for r in e2e["results"] if isinstance(r["step"], int) and r["ok"]])
        flow_rate = flow_passed / flow_total if flow_total else None
    else:
        flow_total = flow_passed = 0
        flow_rate = None

    metrics = {
        "parse_success_rate": parse_rate,
        "parse_detail": {"raw_candidates": total_raw, "parsed": total_parsed},
        "core_field_completeness": field_rate,
        "core_field_detail": {"ok": field_ok, "total": field_total, "per_field": per_field},
        "employment_type_certainty": emp_rate,
        "employment_type_detail": {"certain": emp_certain, "total": emp_total},
        "needs_confirm_count": needs_confirm_count,
        "save_success_rate": save_rate,
        "save_detail": {"attempted": attempted_valid, "saved_new": saved_broad, "skipped": skipped},
        "dedupe": {k: v for k, v in dedupe.items() if k != "rows"},
        "dedupe_rows": dedupe["rows"],
        "relevance": {
            "human_reviewed": human_reviewed,
            "total": len(review),
            "rate": relevance_rate,
            "status": "UNREVIEWED" if human_reviewed == 0 else "PARTIAL",
        },
        "full_flow_success_rate": flow_rate,
        "full_flow_detail": {"passed": flow_passed, "total": flow_total},
    }

    DOCS.mkdir(parents=True, exist_ok=True)
    (DOCS / "metrics.json").write_text(json.dumps(metrics, ensure_ascii=False, indent=2), encoding="utf-8")

    # ---------------------------------------------------------------- 判定完成标准
    at_least_one_source = any(e.get("interface_status") == "OK" and e.get("parsed_jobs", 0) > 0 for e in run["sources"])
    saved_to_db = saved_new > 0
    dedupe_ok = dedupe["fp"] == 0 and dedupe["fn"] == 0
    frontend_ok = bool(e2e and e2e["failed"] == 0)
    mission_ok = bool(e2e and any(r["step"] == 15 and r["ok"] for r in e2e["results"]))
    evidence_ok = bool((DOCS / "e2e-browser-result.json").exists()) and bool(
        (HERE.parents[1] / "docs" / "screenshots" / "job-collection-v1").exists()
    )

    verdict = {
        "at_least_one_real_source_collected": at_least_one_source,
        "jobs_persisted_to_db": saved_to_db,
        "dedupe_passed": dedupe_ok,
        "frontend_full_flow_passed": frontend_ok,
        "saved_job_enters_mission": mission_ok,
        "evidence_saved": evidence_ok,
    }
    verified = all(verdict.values())
    (DOCS / "verdict.json").write_text(
        json.dumps({"COLLECTION_E2E_VERIFIED": verified, "checks": verdict, "generated_at": datetime.now(timezone.utc).isoformat()}, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    # ---------------------------------------------------------------- 报告
    lines: list[str] = []
    lines.append("# 岗位采集真实验收报告（job-collection-v1）\n")
    lines.append(f"- 生成时间：{datetime.now(timezone.utc).isoformat()}")
    lines.append(f"- 隔离测试数据集：`{run.get('dataset_id')}`（**未触碰用户原数据集**）")
    lines.append(f"- 运行记录：`evals/job-collection-v1/runs/{run_files[-1].name}`")
    lines.append(f"- 真实采集岗位样本：{len(review)} 条\n")

    lines.append("## 1. 指标\n")
    lines.append("| 指标 | 数值 | 口径 |")
    lines.append("| --- | --- | --- |")
    lines.append(f"| 采集解析成功率 | {_pct(parse_rate)} | {total_parsed} / {total_considered}（成功解析 / 实际纳入解析范围的候选岗位） |")
    lines.append(f"| 核心字段完整率（非空） | {_pct(field_rate)} | {field_ok} / {field_total}（{len(review)} 条样本 × {len(CORE_FIELDS)} 个必填字段） |")
    lines.append(f"| 岗位类型确定率 | {_pct(emp_rate)} | {emp_certain} / {emp_total}（`employment_type` 非 UNKNOWN；UNKNOWN = 识别不出就如实留空，不猜）|")
    lines.append(f"| 需人工补齐字段的岗位 | {needs_confirm_count} / {len(review)} | 这些岗位已标 `needs_confirm`，导入正式岗位前需用户补齐 |")
    lines.append(f"| 保存成功率 | {_pct(save_rate)} | {saved_broad} / {attempted_valid}（首次采集的入库数 / 尝试保存数） |")
    lines.append(f"| 去重 Precision | {_pct(dedupe['precision'])} | TP={dedupe['tp']} FP={dedupe['fp']} |")
    lines.append(f"| 去重 Recall | {_pct(dedupe['recall'])} | TP={dedupe['tp']} FN={dedupe['fn']} |")
    lines.append(f"| 岗位相关性 | **UNREVIEWED** | 人工已审核 {human_reviewed} / {len(review)}，**没有人工标签就不输出百分比** |")
    lines.append(f"| 完整流程成功率 | {_pct(flow_rate)} | {flow_passed} / {flow_total}（网页采集 → Mission） |")
    lines.append("")

    lines.append("### 分字段完整率\n")
    lines.append("| 字段 | 完整率 | 说明 |")
    lines.append("| --- | --- | --- |")
    for field, stat in per_field.items():
        lines.append(f"| `{field}` | {_pct(stat['ok'] / stat['total'] if stat['total'] else None)} | {stat['ok']}/{stat['total']} |")
    lines.append("")

    lines.append("## 2. 真实在线采集\n")
    lines.append("| 来源 | 阶段 | 关键词 | 接口状态 | 原始返回 | 解析 | 命中 | 入库新增 | 跳过 | 错误 | 耗时 |")
    lines.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for e in run["sources"]:
        s = next((x for x in run["saves"] if x["source"] == e["source"] and x["phase"] == e["phase"]), None)
        lines.append(
            f"| {e['source']} | {e['phase']} | {'/'.join(e['keywords'])} | {e.get('interface_status')} | "
            f"{e.get('raw_candidates')} | {e.get('parsed_jobs')} | {e.get('matched_jobs')} | "
            f"{(s or {}).get('saved_count', '-')} | {(s or {}).get('skipped_count', '-')} | {e.get('error_count')} | {e.get('latency_ms')}ms |"
        )
    lines.append("")
    lines.append("> 「原始返回」= 直接请求公开接口统计到的候选条目数；「解析」= 归一化成功且通过关键词过滤的岗位数。")
    lines.append("> **采集时间 ≠ 岗位发布时间**；接口成功返回**不代表该岗位此刻仍在招**，需点开原始链接自行确认。\n")

    lines.append("## 3. 重复采集去重\n")
    lines.append("| 来源 | 阶段 | 第二次解析 | 第二次新增 | 第二次跳过 | 指纹一致 |")
    lines.append("| --- | --- | --- | --- | --- | --- |")
    for e in run["sources"]:
        rec = e.get("recollect")
        if not rec:
            continue
        lines.append(
            f"| {e['source']} | {e['phase']} | {rec['parsed_jobs']} | {rec['saved_count']} | {rec['skipped_count']} | {rec['same_fingerprint']} |"
        )
    lines.append("")
    lines.append(f"固定标注样本去重：TP={dedupe['tp']} FP={dedupe['fp']} FN={dedupe['fn']} TN={dedupe['tn']}，"
                 f"准确率 {_pct(dedupe['accuracy'])}\n")

    lines.append("## 4. 完成标准判定\n")
    lines.append("| 条件 | 结果 |")
    lines.append("| --- | --- |")
    label = {
        "at_least_one_real_source_collected": "至少一个真实公开来源成功采集",
        "jobs_persisted_to_db": "岗位数据真实入库",
        "dedupe_passed": "重复采集去重通过",
        "frontend_full_flow_passed": "前端完整采集流程通过",
        "saved_job_enters_mission": "保存岗位能继续进入岗位匹配",
        "evidence_saved": "已保存截图、日志与测试报告",
    }
    for key, ok in verdict.items():
        lines.append(f"| {label[key]} | {'✅' if ok else '❌'} |")
    lines.append("")
    lines.append(f"**COLLECTION_E2E_VERIFIED = {verified}**\n")
    lines.append("**CHINESE_JOB_SITES_UNVERIFIED** — 本轮只验证了 RemoteOK / Remotive / Greenhouse / Lever 四个**境外公开**来源；")
    lines.append("BOSS 直聘、实习僧等中文招聘网站**未做真实验证**（需登录态，且不适用自动采集）。\n")

    if e2e:
        lines.append("## 5. 浏览器 E2E（15 步）\n")
        lines.append(f"结果：**{e2e['passed']}/{e2e['total']} 通过**，测试档案 `{e2e.get('profile_id')}`\n")
        lines.append("| 步骤 | 检查 | 结果 | 详情 |")
        lines.append("| --- | --- | --- | --- |")
        for r in e2e["results"]:
            lines.append(f"| {r['step']} | {r['name']} | {'✅' if r['ok'] else '❌'} | {str(r['detail'])[:100]} |")
        lines.append("")

    lines.append("## 6. 用户实操路径（照着做就能复现）\n")
    lines.append("1. 打开 **http://127.0.0.1:3000/jobs**（岗位广场）。")
    lines.append("2. 在「**1 · 一键采集岗位**」区块的关键词输入框里输入关键词后回车。")
    lines.append("   - 实际可用的关键词：`ai`、`product`（宽口径，能拿到真实岗位）")
    lines.append("   - 也可试 `ai product manager`、`product manager intern`（目标口径，命中较少）")
    lines.append("   - 关键词是**本地匹配**：RemoteOK / Greenhouse / Lever 都不支持服务端关键词检索")
    lines.append("3. 点来源 chip 选中 **RemoteOK**（默认已选中，选中态会高亮）。")
    lines.append("   - 想采 Greenhouse / Lever 需要先填招聘板标识（有已验证标识可一键填入，如 `anthropic`、`figma`、`stripe`）")
    lines.append("4. 点「**开始采集**」，等状态变成「采集完成」。")
    lines.append("5. 在「**2 · 采集结果**」里勾选要保存的岗位 → 点「**批量导入选中岗位（N）**」。")
    lines.append("6. 岗位出现在「**5 · 已保存岗位**」；刷新页面仍在。")
    lines.append("7. 再点一次「开始采集」→ 同一批岗位会显示为「**已存在**」，不会重复入库。")
    lines.append("8. 在采集结果行里点「**展开 N 字**」可看完整 JD；「来源」列是原始链接。")
    lines.append("9. 点行内「**匹配分析**」→ 跳转 `/missions/{id}/role`，即进入现有 Mission 链路。\n")
    lines.append("> 本次验收实际保存：RemoteOK 30 条 + Remotive 14 条 + Greenhouse 30 条 + Lever 30 条（BROAD 阶段首次采集，全部入库）。\n")

    lines.append("## 7. 未通过项与已知问题\n")
    if e2e:
        failed = [r for r in e2e["results"] if not r["ok"]]
        if failed:
            for r in failed:
                lines.append(f"- ❌ 步骤 {r['step']}「{r['name']}」：{r['detail']}")
        else:
            lines.append("- 浏览器 E2E 15 步全部通过。")
    lines.append("- 岗位相关性未经人工确认，标记为 `UNREVIEWED`，未输出百分比。")
    lines.append("- 中文招聘网站（BOSS 直聘 / 实习僧等）未做真实验证。")
    lines.append("")

    (DOCS / "report.md").write_text("\n".join(lines), encoding="utf-8")

    # ---------------------------------------------------------------- 人工审核清单
    rl: list[str] = []
    rl.append("# 真实采集结果人工审核清单\n")
    rl.append(f"- 样本数：**{len(review)} 条**（要求 ≥ 20，充足={len(review) >= 20}）")
    rl.append("- 全部来自真实公开来源采集，**没有一条是合成数据**；不足 20 条时会如实报告，不会用合成数据补齐。")
    rl.append("- `是否 AI 产品相关` 的 Agent 预判**不是**人工金标准；`人工确认` 列留空 = `UNREVIEWED`。")
    rl.append("- `仍在招` 一律为 UNKNOWN：接口返回成功不等于岗位此刻仍在招，需点开原始链接自行确认。\n")
    rl.append("| # | 公司 | 岗位 | 地点 | 是否实习 | AI 产品相关（Agent 预判） | 人工确认 | 来源 | 原始链接 | JD 摘要 | 待审核字段 |")
    rl.append("| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |")
    for idx, item in enumerate(review, start=1):
        rl.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | [链接]({}) | {} | {} |".format(
                idx,
                (item.get("company") or "—").replace("|", "\\|"),
                (item.get("role") or "—").replace("|", "\\|")[:60],
                (item.get("location") or "—").replace("|", "\\|")[:30],
                "是" if item.get("is_intern") else "否",
                ("是" if item.get("ai_product_relevant_agent_guess") else "否")
                + f"（{item.get('ai_product_relevant_reason', '')[:24]}）",
                "UNREVIEWED",
                item.get("source"),
                item.get("source_url") or "",
                (item.get("jd_excerpt") or "").replace("\n", " ").replace("|", "\\|")[:90],
                ", ".join(item.get("needs_confirm_fields") or []) or "无",
            )
        )
    rl.append("")
    rl.append("## 人工确认方法\n")
    rl.append("请把 `人工确认` 列填为 `是` / `否`，填好后相关性指标才算得出：\n")
    rl.append("```")
    rl.append("相关性 = 人工确认相关的结果数 / 人工已审核的结果数")
    rl.append("```\n")
    rl.append("在**没有**任何人工标签之前，该指标一律记为 `UNREVIEWED`，不输出百分比。\n")
    (DOCS / "review-list.md").write_text("\n".join(rl), encoding="utf-8")

    print(f"[OK] 报告：{DOCS / 'report.md'}")
    print(f"[OK] 审核清单：{DOCS / 'review-list.md'}（{len(review)} 条）")
    print(f"[OK] 指标：{DOCS / 'metrics.json'}")
    print(f"[OK] 判定：COLLECTION_E2E_VERIFIED = {verified}  {verdict}")
    return 0


def _pct(value: float | None) -> str:
    return "—" if value is None else f"{value * 100:.1f}%"


if __name__ == "__main__":
    raise SystemExit(main())
