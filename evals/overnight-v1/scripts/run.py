"""运行 overnight-v1 基准：A/B baseline（Direct LLM vs AI Career OS）。

用法：
    python scripts/run.py [--api http://127.0.0.1:8100]

- 路径 B（AI Career OS）：走本地服务的完整管道（/resumes/text + job-missions + target-resumes）；
- 路径 A（Direct LLM）：直接把「简历要点 + JD」发给裸模型（BASELINE_DIRECT_LLM 配置），要求改写；
- **诚实性规则**：任一路径不可用（服务未启动 / 模型未配置）时，
  该路径所有案例标 `NOT_RUN`，**绝不伪造结果**。

输出：results/run-<时间戳>.json
"""
from __future__ import annotations

import argparse
import json
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
RESULTS = ROOT / "results"

import os

DIRECT_LLM_BASE_URL = os.getenv("BASELINE_DIRECT_LLM_BASE_URL", "").strip()
DIRECT_LLM_API_KEY = os.getenv("BASELINE_DIRECT_LLM_API_KEY", "").strip()
DIRECT_LLM_MODEL = os.getenv("BASELINE_DIRECT_LLM_MODEL", "").strip()


def http_json(method: str, url: str, body: dict | None = None, headers: dict | None = None, timeout: int = 600):
    data = json.dumps(body or {}).encode() if body is not None else None
    request = urllib.request.Request(url, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            return response.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as exc:
        return exc.code, {"detail": exc.read().decode("utf-8", "replace")[:400]}
    except urllib.error.URLError as exc:
        return 0, {"detail": str(exc)}


def direct_llm_rewrite(resume_text: str, jd_text: str) -> dict:
    """Baseline A：把简历 + JD 直接丢给裸模型，无事实锚定/无四分类/无防注入护栏。"""
    if not (DIRECT_LLM_BASE_URL and DIRECT_LLM_API_KEY and DIRECT_LLM_MODEL):
        return {"status": "NOT_RUN", "reason": "未配置 BASELINE_DIRECT_LLM_* 环境变量"}
    prompt = (
        "你是简历改写助手。下面是一份简历和一份 JD，请逐条改写简历要点，使其更匹配 JD，"
        "输出 JSON：{\"rewrites\":[{\"original\":\"...\",\"rewritten\":\"...\"}]}。\n\n"
        f"【简历】\n{resume_text}\n\n【JD】\n{jd_text}"
    )
    status, response = http_json(
        "POST",
        DIRECT_LLM_BASE_URL.rstrip("/") + "/chat/completions",
        {"model": DIRECT_LLM_MODEL, "messages": [{"role": "user", "content": prompt}], "temperature": 0.2},
        headers={"Authorization": f"Bearer {DIRECT_LLM_API_KEY}"},
    )
    if status != 200:
        return {"status": "NOT_RUN", "reason": f"模型调用失败 HTTP {status}"}
    try:
        content = response["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return {"status": "NOT_RUN", "reason": "模型响应结构异常"}
    return {"status": "OK", "raw_output": content}


def ai_career_os_rewrite(api: str, resume_text: str, jd_text: str) -> dict:
    """Baseline B：走 AI Career OS 完整管道。"""
    status, profile = http_json("POST", f"{api}/api/v1/profiles/draft")
    if status not in {200, 201}:
        return {"status": "NOT_RUN", "reason": f"服务不可用 HTTP {status}"}
    profile_id = profile.get("profile_id") or profile.get("id")
    http_json("POST", f"{api}/api/v1/profiles/{profile_id}/resumes/text", {"raw_text": resume_text})
    http_json("POST", f"{api}/api/v1/profiles/{profile_id}/confirm")
    status, mission = http_json("POST", f"{api}/api/v1/profiles/{profile_id}/job-missions", {"raw_text": jd_text})
    if status != 201:
        return {"status": "NOT_RUN", "reason": f"创建 Mission 失败 HTTP {status}: {json.dumps(mission, ensure_ascii=False)[:200]}"}
    mission_id = mission.get("mission_id") or mission.get("id")
    for _ in range(60):
        status, state = http_json("GET", f"{api}/api/v1/job-missions/{mission_id}")
        if state.get("workflow_state") not in {"JOB_ANALYZING", "JD_REQUIRED", "CREATING"}:
            break
        time.sleep(3)
    http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/continue-to-resume")
    status, _ = http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/resumes/text", {"raw_text": resume_text})
    if status not in {200, 201}:
        return {"status": "NOT_RUN", "reason": f"上传岗位简历失败 HTTP {status}"}
    status, _ = http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/confirm-resume-source", {"mode": "paste", "update_master": False})
    if status not in {200, 201}:
        return {"status": "NOT_RUN", "reason": f"确认简历来源失败 HTTP {status}"}
    # 重要：不代系统做四分类。系统自己生成什么就记录什么；
    # 基准脚本若强行把每条经历写成 KEEP_AND_HIGHLIGHT，等于替被测系统作答，评分就失去意义。
    system_selection_raw = None
    status, selection = http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/experience-selection/generate", {})
    if status in {200, 201}:
        items = selection.get("selections") or selection.get("items") or []
        system_selection_raw = [
            {"experience_id": item.get("experience_id"), "decision": item.get("decision"), "confidence": item.get("confidence")}
            for item in items
        ]
        # 只做「确认」动作，逐条沿用系统给出的 decision（缺失时回退 KEEP，并在记录里标注）
        http_json("PUT", f"{api}/api/v1/job-missions/{mission_id}/experience-selection?confirm=true", {
            "selections": [
                {
                    "experience_id": item.get("experience_id"),
                    "decision": item.get("decision") or "KEEP",
                    "why": "benchmark-confirm",
                    "confidence": item.get("confidence") if item.get("confidence") is not None else 0.8,
                }
                for item in items
            ]
        })
    http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/resume-strategy", {})
    http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/confirm-strategy", {})
    status, target = http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/target-resumes", {})
    if status != 201 and status != 200:
        return {"status": "NOT_RUN", "reason": f"生成定向简历失败 HTTP {status}: {json.dumps(target, ensure_ascii=False)[:200]}"}
    # 逐条接受非合成要点（模拟用户确认），否则确认环节会拒绝
    trs = http_json("GET", f"{api}/api/v1/job-missions/{mission_id}/target-resumes")[1]
    items = trs if isinstance(trs, list) else trs.get("items", [])
    latest = max(items, key=lambda item: item.get("version", 0)) if items else {}
    for bullet in latest.get("bullets") or []:
        flags = {str(v).upper() for v in (bullet.get("risk_flags") or [])}
        if "SYNTHETIC_PROJECT" in flags:
            continue
        http_json("PATCH", f"{api}/api/v1/target-resume-bullets/{bullet['id']}", {"status": "ACCEPTED", "fact_confirmed": True})
    status, _ = http_json("POST", f"{api}/api/v1/job-missions/{mission_id}/confirm-target-resume", {})
    if status not in {200, 201}:
        return {"status": "NOT_RUN", "reason": f"确认定向简历失败 HTTP {status}"}
    bullets = []
    for bullet in latest.get("bullets") or []:
        bullets.append({
            "original": bullet.get("original_text"),
            "rewritten": bullet.get("suggested_text") or bullet.get("final_text"),
            "status": bullet.get("status"),
            "risk_flags": bullet.get("risk_flags") or [],
        })
    return {
        "status": "OK",
        "bullets": bullets,
        "mission_id": str(mission_id),
        "system_selection_raw": system_selection_raw,
    }


# 占位 JD：必须 >= 服务的 raw_text 最小长度（20），否则会把「简历通道」的用例误判为系统不可用。
_PLACEHOLDER_JD = (
    "产品经理（北京）\n"
    "岗位职责：负责产品需求调研、方案设计与迭代推进。\n"
    "任职要求：本科及以上学历，具备良好的沟通与数据分析能力。"
)


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--api", default="http://127.0.0.1:8100")
    parser.add_argument("--limit", type=int, default=0, help="只跑前 N 个改写案例（0=全部）")
    args = parser.parse_args()

    jobs = {jd["id"]: jd for jd in json.loads((DATA / "jobs.json").read_text(encoding="utf-8"))}
    resumes = {rs["id"]: rs for rs in json.loads((DATA / "resumes.json").read_text(encoding="utf-8"))}
    rewrites = json.loads((DATA / "rewrite_cases.json").read_text(encoding="utf-8"))
    bad_cases = json.loads((DATA / "bad_cases.json").read_text(encoding="utf-8"))
    if args.limit:
        rewrites = rewrites[: args.limit]

    RESULTS.mkdir(exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    run_record = {
        "run_at": datetime.now(timezone.utc).isoformat(),
        "api": args.api,
        "dataset": "overnight-v1",
        "baseline_a": [],
        "baseline_b": [],
        "bad_cases": [],
    }

    # --- Baseline B：AI Career OS（按配对跑，一次 Mission 覆盖该配对的 3 条案例）---
    pairs_seen: dict[str, dict] = {}
    for case in rewrites:
        pairs_seen.setdefault(case["pair_id"], case)
    for pair_id, case in sorted(pairs_seen.items()):
        resume = resumes[case["resume_id"]]
        jd = jobs[case["jd_id"]]
        print(f"[B] {pair_id} rs={case['resume_id']} jd={case['jd_id']} ...", flush=True)
        result = ai_career_os_rewrite(args.api, resume["raw_text"], jd["raw_text"])
        run_record["baseline_b"].append({"pair_id": pair_id, "resume_id": case["resume_id"], "jd_id": case["jd_id"], **result})

    # --- Baseline A：Direct LLM（同样按配对）---
    for pair_id, case in sorted(pairs_seen.items()):
        resume = resumes[case["resume_id"]]
        jd = jobs[case["jd_id"]]
        print(f"[A] {pair_id} ...", flush=True)
        result = direct_llm_rewrite(resume["raw_text"], jd["raw_text"])
        run_record["baseline_a"].append({"pair_id": pair_id, "resume_id": case["resume_id"], "jd_id": case["jd_id"], **result})

    # --- Bad Cases（对抗/安全）：B 路径处理，记录系统行为 ---
    for case in bad_cases:
        resume = resumes["rs-01"]
        jd_text = case["payload"] if case["input_channel"] in {"JD", "BOTH"} else _PLACEHOLDER_JD
        resume_text = case["payload"] if case["input_channel"] == "RESUME" else resume["raw_text"]
        if case["input_channel"] == "BOTH":
            resume_text = resume["raw_text"] + "\n" + case["payload"]
        print(f"[BC] {case['id']} {case['category']} ...", flush=True)
        result = ai_career_os_rewrite(args.api, resume_text, jd_text)
        # 「预期被拒绝」的用例（如空 JD）：系统返回 4xx 本身就是正确的安全行为，
        # 不能因为跑不到后续步骤就记成 NOT_RUN——那等于把没执行当成通过。
        if result.get("status") == "NOT_RUN" and case.get("expects_rejection") and "HTTP 4" in (result.get("reason") or ""):
            result = {"status": "REJECTED", "reason": result["reason"], "rejected_as_expected": True}
        run_record["bad_cases"].append({"id": case["id"], "category": case["category"], **result})

    out = RESULTS / f"run-{stamp}.json"
    out.write_text(json.dumps(run_record, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
    print(f"\n运行记录：{out}")
    print("下一步：python scripts/score.py " + str(out))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
