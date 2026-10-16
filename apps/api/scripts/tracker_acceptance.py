"""M3 验收：求职管理补齐（真实 LLM 全链路）。

流程：
  建档 → 上传简历 → 建 Mission → 改写 → 确认 Studio
  → 新建投递记录（绑定 mission + JD 来源）
  → 绑定简历版本（版本 ID + Studio 修订号 + PDF 快照）
  → 下载快照（回答「我当初投的是哪份简历」）
  → 生成打招呼话术（简洁/详细，只引用真实事实，不自动发送）
  → 用户编辑话术 → 保存
  → 状态推进 / 退回
  → 创建提醒 → 看板聚合（阶段数量 / 版本使用记录 / 最近面试 / 提醒）

输出：docs/evaluation/overnight-sprint/m3-tracker-acceptance.json
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
OUT = Path(r"G:\myself\ai-career\docs\evaluation\overnight-sprint")
OUT.mkdir(parents=True, exist_ok=True)

RESUME_TEXT = """赵六
电话：13600000000  邮箱：zhaoliu@example.com  城市：杭州

教育背景
某大学 信息管理 本科 2020.09 - 2024.06

实习经历
某电商公司 数据运营实习 2023.07 - 2023.12
- 维护商品运营日报，覆盖 GMV、转化率等 12 个核心指标
- 用 SQL 抽取异常订单数据，协助定位 3 次线上问题
- 整理运营 SOP 文档，新人上手时间从 2 周缩短到 3 天

技能
SQL / Python / Excel / 数据看板
"""

JD_TEXT = """数据运营专员（杭州）
岗位职责：
1. 负责日常经营数据的监控与报表维护；
2. 配合运营活动做数据抽取与效果复盘；
3. 维护运营流程文档，提升协作效率。
任职要求：
1. 本科及以上学历，专业不限；
2. 熟练使用 SQL 与 Excel；
3. 做事细致，有文档习惯者优先。
"""

evidence: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "base_url": BASE, "steps": []}


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, raw: bool = False):
    data = json.dumps(body or {}).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = response.read()
            if raw:
                return payload
            return json.loads(payload) if payload else {}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        return {"__http_error": exc.code, "detail": detail}


def step(name: str, result, extra_ok=None) -> dict:
    ok = "__http_error" not in result if isinstance(result, dict) else True
    if ok and extra_ok is not None:
        ok = bool(extra_ok(result))
    evidence["steps"].append({"step": name, "ok": ok, "result": result})
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" → {json.dumps(result, ensure_ascii=False)[:300]}"))
    return result


def wait_mission_ready(mission_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = call("GET", f"/api/v1/job-missions/{mission_id}")
        if last.get("workflow_state") not in {"JOB_ANALYZING", "JD_REQUIRED", "CREATING"}:
            return last
        time.sleep(3)
    return last


def accept_bullets(mission_id: str) -> dict:
    trs = call("GET", f"/api/v1/job-missions/{mission_id}/target-resumes")
    latest = max(trs if isinstance(trs, list) else trs.get("items", []), key=lambda item: item.get("version", 0))
    accepted, skipped = 0, 0
    for bullet in latest.get("bullets") or []:
        flags = {str(value).upper() for value in (bullet.get("risk_flags") or [])}
        if "SYNTHETIC_PROJECT" in flags:
            skipped += 1
            continue
        result = call("PATCH", f"/api/v1/target-resume-bullets/{bullet['id']}", {"status": "ACCEPTED", "fact_confirmed": True})
        if "__http_error" not in result:
            accepted += 1
        else:
            skipped += 1
    return {"version": latest.get("version"), "accepted": accepted, "skipped": skipped}


# 1 · 建档 + Mission 全流程到 Studio 确认
profile = step("1-draft-profile", call("POST", "/api/v1/profiles/draft"))
profile_id = profile.get("profile_id") or profile.get("id")
call("POST", f"/api/v1/profiles/{profile_id}/resumes/text", {"raw_text": RESUME_TEXT})
call("POST", f"/api/v1/profiles/{profile_id}/confirm")
mission = call("POST", f"/api/v1/profiles/{profile_id}/job-missions", {"raw_text": JD_TEXT})
mission_id = mission.get("mission_id") or mission.get("id")
call("GET", f"/api/v1/job-missions/{mission_id}") and wait_mission_ready(mission_id)
call("POST", f"/api/v1/job-missions/{mission_id}/continue-to-resume")
call("POST", f"/api/v1/job-missions/{mission_id}/resumes/text", {"raw_text": RESUME_TEXT})
call("POST", f"/api/v1/job-missions/{mission_id}/confirm-resume-source", {"mode": "paste", "update_master": False})
selection = call("POST", f"/api/v1/job-missions/{mission_id}/experience-selection/generate", {})
payload = {"selections": [
    {"experience_id": item.get("experience_id"), "decision": "KEEP_AND_HIGHLIGHT", "why": "与 JD 的数据/报表/文档要求直接相关", "confidence": 0.8}
    for item in (selection.get("selections") or selection.get("items") or [])
]}
call("PUT", f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true", payload)
call("POST", f"/api/v1/job-missions/{mission_id}/resume-strategy", {})
call("POST", f"/api/v1/job-missions/{mission_id}/confirm-strategy", {})
call("POST", f"/api/v1/job-missions/{mission_id}/target-resumes", {})
step("2-accept-bullets", accept_bullets(mission_id))
step("3-confirm-target-resume", call("POST", f"/api/v1/job-missions/{mission_id}/confirm-target-resume", {}))
studio_base = f"/api/v1/job-missions/{mission_id}/resume-studio"
doc = call("GET", studio_base)
confirmed = call("POST", f"{studio_base}/confirm", {}, headers={"If-Match": str(doc.get("revision"))})
step("4-confirm-studio", confirmed)

# 2 · 新建投递记录（绑定 mission + JD 来源）
application = step(
    "5-create-application",
    call("POST", f"/api/v1/profiles/{profile_id}/applications", {
        "company": "某电商集团", "role": "数据运营专员", "location": "杭州", "channel": "招聘网站",
        "mission_id": mission_id, "jd_source": "粘贴 JD",
    }),
)
application_id = application.get("id")

# 3 · 绑定简历版本 → 版本 ID + 修订号 + PDF 快照
bound = step("6-bind-resume", call("POST", f"/api/v1/applications/{application_id}/bind-resume", {}))
step(
    "7-bind-records-version-and-revision",
    bound,
    lambda r: r.get("resume_version_id") and r.get("studio_revision") == confirmed.get("revision") and r.get("has_pdf_snapshot"),
)

# 4 · 下载快照：回答「我当初投的是哪份简历」
snapshot = call("GET", f"/api/v1/applications/{application_id}/resume-snapshot", raw=True)
snapshot_ok = isinstance(snapshot, bytes) and snapshot[:4] == b"%PDF"
if snapshot_ok:
    (OUT / "m3-delivery-snapshot.pdf").write_bytes(snapshot)
print(("PASS" if snapshot_ok else "FAIL") + f" 8-download-snapshot ({len(snapshot) if snapshot_ok else 0} bytes)")
evidence["steps"].append({"step": "8-download-snapshot", "ok": snapshot_ok, "result": {"bytes": len(snapshot) if snapshot_ok else 0}})

# 5 · 打招呼话术：生成 → 不编造检查 → 编辑 → 保存
greeted = step("9-generate-greeting", call("POST", f"/api/v1/applications/{application_id}/greeting"))
short_text = greeted.get("greeting_short") or ""
long_text = greeted.get("greeting_long") or ""
step(
    "10-greeting-grounded",
    {"short_len": len(short_text), "long_len": len(long_text), "short_head": short_text[:80]},
    lambda r: "数据运营专员" in short_text and "某电商集团" in long_text,
)
edited = step(
    "11-edit-greeting",
    call("PATCH", f"/api/v1/applications/{application_id}", {"greeting_short": "您好，我对数据运营专员岗位很感兴趣，简历已附上，期待沟通。"}),
)
step("11b-edit-saved", edited, lambda r: r.get("greeting_short") == "您好，我对数据运营专员岗位很感兴趣，简历已附上，期待沟通。")

# 6 · 状态推进 / 退回
step("12-advance-status", call("PATCH", f"/api/v1/applications/{application_id}", {"status": "APPLIED"}), lambda r: r.get("status") == "APPLIED")
step("12b-retreat-status", call("PATCH", f"/api/v1/applications/{application_id}", {"status": "PENDING"}), lambda r: r.get("status") == "PENDING")
call("PATCH", f"/api/v1/applications/{application_id}", {"status": "APPLIED"})

# 7 · 提醒 + 面试记录
reminder = step("13-create-reminder", call("POST", f"/api/v1/profiles/{profile_id}/reminders", {"title": "跟进某电商集团 HR", "due_at": "2026-10-25T09:00:00Z"}))
interview = step(
    "14-create-interview-record",
    call("POST", f"/api/v1/profiles/{profile_id}/interview-records", {
        "company": "某电商集团", "role": "数据运营专员", "interview_round": "一面", "interviewed_on": "2026-10-18",
        "notes": "SQL 手写题 + 数据看板项目复盘",
        "items": [
            {"question": "写一个 SQL：查每个品类近 30 天的销量 Top3 商品", "my_answer": "用窗口函数 row_number() over (partition by 品类 order by 销量 desc) 取前 3"},
            {"question": "讲一个你维护数据看板的例子", "my_answer": "维护商品运营日报，覆盖 GMV、转化率等 12 个核心指标"},
        ],
    }),
)

# 8 · 看板聚合
board = step("15-board", call("GET", f"/api/v1/profiles/{profile_id}/applications/board"))
step(
    "16-board-assertions",
    {
        "total": board.get("total"),
        "applied_count": (board.get("columns") or {}).get("APPLIED", {}).get("count"),
        "version_usage": board.get("version_usage"),
        "reminders": board.get("reminders"),
        "reminder_note": board.get("reminder_note"),
    },
    lambda r: r.get("total") == 1
    and (r.get("applied_count") == 1)
    and any(u.get("used_by") for u in r.get("version_usage") or [])
    and any(item.get("title") == "跟进某电商集团 HR" for item in r.get("reminders") or [])
    and "不" in (r.get("reminder_note") or ""),
)

evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
evidence["mission_id"] = mission_id
evidence["application_id"] = application_id
target = OUT / "m3-tracker-acceptance.json"
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
failed = [item for item in evidence["steps"] if not item["ok"]]
print(f"\n证据文件：{target}；失败步骤：{len(failed)}")
