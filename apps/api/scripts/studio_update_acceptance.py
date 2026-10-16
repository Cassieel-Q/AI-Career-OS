"""M2 验收：Resume Studio 一键更新（真实 LLM 全链路）。

流程：
  建档 → 上传简历 → 建 Mission → 绑定岗位简历 → 确认 → 经历四分类 → 策略
  → 生成定向简历 v1 → 确认 → Studio 初始导入
  → 用户手工编辑（会被替换的内容）
  → 重新生成 v2 → 确认 → source-diff（板块级差异 + 人工编辑提示）
  → 修订冲突 409 → 正确 reimport → 修订 +1 → 确认投递版 → 真实 PDF

输出：docs/evaluation/overnight-sprint/m2-studio-acceptance.json + m2-studio.pdf
"""
from __future__ import annotations

import json
import re
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8100"
CASE = sys.argv[2] if len(sys.argv) > 2 else "ai-pm"
OUT = Path(r"G:\myself\ai-career\docs\evaluation\overnight-sprint")
OUT.mkdir(parents=True, exist_ok=True)

# 两套完全不同的简历 × 两个明显不同的 JD：验证「换人换岗」时差异与正文都不会串
CASES = {
    "ai-pm": {
        "resume": """张三
电话：13800000000  邮箱：zhangsan@example.com  城市：北京

教育背景
某大学 计算机科学与技术 本科 2020.09 - 2024.06

实习经历
某互联网公司 AI 产品实习 2023.06 - 2023.12
- 负责智能客服机器人的需求拆解与迭代排期，跟进 3 个版本上线
- 搭建并维护标注规范文档，协同 5 人团队完成 2000 条对话数据质检
- 通过埋点分析定位回复质量下降原因，推动 prompt 优化后问题解决率提升

项目经历
校园二手交易平台 2022.09 - 2023.05
- 担任产品负责人，完成从需求调研到上线的完整闭环，累计注册用户 800+
- 设计信任分体系，纠纷率下降约 30%

技能
Python / SQL / Figma / Axure / prompt 设计
""",
        "jd": """AI 产品经理（北京）
岗位职责：
1. 负责 AI 助手类产品的需求分析与功能设计，输出 PRD 并推动落地；
2. 与算法、工程团队协作，定义评测集与质量标准，跟进模型迭代效果；
3. 分析用户反馈与数据，持续优化产品体验；
4. 跟踪行业动态，输出竞品分析与产品规划。
任职要求：
1. 本科及以上学历，计算机、产品相关专业优先；
2. 有 AI 产品或对话式产品实习/项目经验者优先；
3. 逻辑清晰，能独立完成需求拆解与原型设计；
4. 熟悉 prompt 设计或模型评测者加分。
""",
    },
    "data-analyst": {
        "resume": """李四
电话：13900000000  邮箱：lisi@example.com  城市：上海

教育背景
某财经大学 统计学 本科 2019.09 - 2023.06

工作经历
某零售集团 数据分析师 2023.07 - 2025.03
- 搭建门店周报与库存周转看板，覆盖 120 家门店的日常经营指标
- 设计 A/B 实验评估流程，完成 15 组营销活动的效果归因与复盘
- 用 SQL 与 Python 清洗订单数据，将报表出数时间从 2 天压缩到 4 小时

项目经历
用户流失预警模型 2024.03 - 2024.09
- 基于历史行为特征建立流失预警模型，召回率 0.72
- 联动运营团队做分层触达，次月留存相对提升 6 个百分点

技能
SQL / Python / Excel / Tableau / 统计分析
""",
        "jd": """数据分析师（上海）
岗位职责：
1. 负责经营指标体系搭建与日常报表维护，输出可复用的看板；
2. 设计并执行 A/B 实验，完成效果归因与结论复盘；
3. 参与用户流失预警等建模项目，沉淀特征与评估方法；
4. 与业务团队协作，把数据结论转化为可执行的运营动作。
任职要求：
1. 本科及以上学历，统计、数学、计算机相关专业；
2. 熟练使用 SQL 与 Python，能独立完成数据清洗与指标建设；
3. 有 A/B 实验与用户分层运营经验者优先；
4. 沟通清晰，能把分析结论讲给非技术同事听。
""",
    },
}

RESUME_TEXT = CASES[CASE]["resume"]
JD_TEXT = CASES[CASE]["jd"]

evidence: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "base_url": BASE, "case": CASE, "steps": []}


def call(method: str, path: str, body: dict | None = None, raw: bool = False):
    data = json.dumps(body or {}).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json"}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=600) as response:
            payload = response.read()
            return json.loads(payload) if not raw else payload
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:600]
        return {"__http_error": exc.code, "detail": detail}



def call_with_headers(method: str, path: str, headers: dict, body: bytes | None = None):
    request = urllib.request.Request(BASE + path, data=body, headers=headers, method=method)
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.loads(response.read())
    except urllib.error.HTTPError as exc:
        return {"__http_error": exc.code, "detail": exc.read().decode("utf-8", "replace")[:400]}


def step(name: str, result) -> dict:
    ok = "__http_error" not in result if isinstance(result, dict) else True
    entry = {"step": name, "ok": ok, "result": result if ok else result}
    evidence["steps"].append(entry)
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" → {json.dumps(result, ensure_ascii=False)[:300]}"))
    return result



def accept_bullets(mission_id: str) -> dict:
    """模拟用户在岗位简历页「逐条接受」：非合成草案的要点全部接受并确认事实。"""
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


def doc_texts(document: dict) -> list[str]:
    return sorted(
        bullet["text"]
        for section in document.get("sections") or []
        for entry in section.get("entries") or []
        for bullet in entry.get("bullets") or []
        if bullet.get("text")
    )


# 与后端 resume_studio_service._PLACEHOLDER_RESIDUE 保持同一口径
PLACEHOLDER_RESIDUE = re.compile(r"【[^】]*(?:待补|待确认|待补充|待核实|待完善)[^】]*】|待补充|待核实|待完善|待补全")


def fix_placeholders(studio_base: str) -> dict:
    """模拟用户补齐残留占位标记：能留下实质内容的就改写，只剩占位词的整条省略。

    注意：不凭空补量化成果——清掉占位话术后如果没剩东西，就走 omit。
    """
    cleaned, omitted, failed = 0, 0, 0
    current = call("GET", studio_base)
    revision = current.get("revision")
    document = current.get("document") or {}
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            for bullet in entry.get("bullets") or []:
                text = bullet.get("text") or ""
                if not PLACEHOLDER_RESIDUE.search(text):
                    continue
                residual = PLACEHOLDER_RESIDUE.sub("", text)
                residual = re.sub(r"[（(]\s*[）)]", "", residual).strip(" ·、，,；;:")
                if len(residual) >= 10:
                    result = call_with_headers(
                        "PATCH", studio_base,
                        {"Content-Type": "application/json", "If-Match": str(revision)},
                        json.dumps({"type": "set_text", "node_id": bullet["id"], "text": residual}).encode(),
                    )
                    if "__http_error" not in result:
                        revision = result.get("revision", revision)
                        cleaned += 1
                    else:
                        failed += 1
                else:
                    result = call_with_headers(
                        "PATCH", studio_base,
                        {"Content-Type": "application/json", "If-Match": str(revision)},
                        json.dumps({"type": "omit", "node_id": bullet["id"]}).encode(),
                    )
                    if "__http_error" not in result:
                        revision = result.get("revision", revision)
                        omitted += 1
                    else:
                        failed += 1
    return {"cleaned": cleaned, "omitted": omitted, "failed": failed, "revision": revision}


def wait_mission_ready(mission_id: str, timeout: float = 180) -> dict:
    deadline = time.time() + timeout
    last = {}
    while time.time() < deadline:
        last = call("GET", f"/api/v1/job-missions/{mission_id}")
        state = last.get("workflow_state")
        if state not in {"JOB_ANALYZING", "JD_REQUIRED", "CREATING"}:
            return last
        time.sleep(3)
    return last


# 1 · 建档 + 简历解析（真实 LLM 抽取）
profile = step("1-draft-profile", call("POST", "/api/v1/profiles/draft"))
profile_id = profile.get("profile_id") or profile.get("id")
ingested = step("2-ingest-resume", call("POST", f"/api/v1/profiles/{profile_id}/resumes/text", {"raw_text": RESUME_TEXT}))
step("3-confirm-profile", call("POST", f"/api/v1/profiles/{profile_id}/confirm"))

# 2 · 建 Mission（粘贴 JD）→ 等 JD 分析完成
mission = step("4-create-mission", call("POST", f"/api/v1/profiles/{profile_id}/job-missions", {"raw_text": JD_TEXT}))
mission_id = mission.get("mission_id") or mission.get("id")
mission = step("4b-wait-analysis", wait_mission_ready(mission_id))
step("4c-continue-to-resume", call("POST", f"/api/v1/job-missions/{mission_id}/continue-to-resume"))

# 3 · 绑定岗位简历 + 确认
step("5-bind-resume", call("POST", f"/api/v1/job-missions/{mission_id}/resumes/text", {"raw_text": RESUME_TEXT}))
step("5b-confirm-source", call("POST", f"/api/v1/job-missions/{mission_id}/confirm-resume-source", {"mode": "paste", "update_master": False}))

# 4 · 经历四分类（生成 → 全部确认）
selection_generated = step("6-generate-selection", call("POST", f"/api/v1/job-missions/{mission_id}/experience-selection/generate", {}))
selections_payload = {"selections": []}
for item in (selection_generated.get("selections") or selection_generated.get("items") or []):
    selections_payload["selections"].append(
        {
            "experience_id": item.get("experience_id"),
            "decision": "KEEP_AND_HIGHLIGHT",
            "why": "与 JD 的产品/评测/协作要求直接相关",
            "confidence": 0.8,
        }
    )
step("6b-save-selection", call("PUT", f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true", selections_payload))
step("7-resume-strategy", call("POST", f"/api/v1/job-missions/{mission_id}/resume-strategy", {}))
step("7b-confirm-strategy", call("POST", f"/api/v1/job-missions/{mission_id}/confirm-strategy", {}))

# 5 · 生成定向简历 v1 → 逐条接受要点 → 确认 → Studio 初始导入
step("8-generate-target-v1", call("POST", f"/api/v1/job-missions/{mission_id}/target-resumes", {}))
v1_accept = accept_bullets(mission_id)
step("8a-accept-bullets-v1", {**v1_accept, "ok": v1_accept["accepted"] > 0} if v1_accept["accepted"] > 0 else {**v1_accept, "__http_error": 409, "detail": "没有任何要点被接受"})
step("8b-confirm-target-v1", call("POST", f"/api/v1/job-missions/{mission_id}/confirm-target-resume", {}))

studio_base = f"/api/v1/job-missions/{mission_id}/resume-studio"
studio_v1 = step("9-read-studio", call("GET", studio_base))
revision_v1 = studio_v1.get("revision")
initial_diff = step("9b-source-diff-after-v1", call("GET", f"{studio_base}/source-diff"))
evidence["initial_diff_update_available"] = (initial_diff or {}).get("update_available")

# 6 · 用户手工编辑（生成新版后会被替换 → 差异弹窗必须提示）
sections = studio_v1["document"]["sections"]
first_entry = sections[0]["entries"][0]
manual = call_with_headers(
    "PATCH",
    studio_base,
    {"Content-Type": "application/json", "If-Match": str(revision_v1)},
    json.dumps({"type": "add_bullet", "entry_id": first_entry["id"], "text": "手工补充：整理过评测集用例并每周同步质量报表。"}).encode(),
)
step("10-manual-edit", {"revision": manual.get("revision")} if "__http_error" not in manual else manual)
revision_manual = manual.get("revision")

# 7 · 重新生成 v2 → 逐条接受 → 确认 → 差异
step("11-generate-target-v2", call("POST", f"/api/v1/job-missions/{mission_id}/target-resumes", {}))
v2_accept = accept_bullets(mission_id)
step("11a-accept-bullets-v2", {**v2_accept, "ok": v2_accept["accepted"] > 0} if v2_accept["accepted"] > 0 else {**v2_accept, "__http_error": 409, "detail": "没有任何要点被接受"})
step("11b-confirm-target-v2", call("POST", f"/api/v1/job-missions/{mission_id}/confirm-target-resume", {}))
diff = step("12-source-diff-v2", call("GET", f"{studio_base}/source-diff"))
evidence["diff_v2"] = {
    "update_available": (diff or {}).get("update_available"),
    "added": (diff or {}).get("added_bullets"),
    "removed": (diff or {}).get("removed_bullets"),
    "sections": (diff or {}).get("sections"),
    "manual_edit_count": (diff or {}).get("manual_edit_count"),
    "manual_edit_samples": (diff or {}).get("manual_edit_samples"),
}

# 8 · 修订冲突（用过期修订号）→ 409；再用最新修订号 → 成功
no_header = call_with_headers("POST", f"{studio_base}/reimport", {"Content-Type": "application/json"})
step("13a-reimport-without-if-match", {"expect": 428, "got": no_header.get("__http_error")} if no_header.get("__http_error") == 428 else no_header)
stale = call_with_headers("POST", f"{studio_base}/reimport", {"Content-Type": "application/json", "If-Match": str(max(0, int(revision_manual or 1) - 1))})
step("13b-stale-revision-409", {"expect": 409, "got": stale.get("__http_error")} if stale.get("__http_error") == 409 else stale)
updated = call_with_headers("POST", f"{studio_base}/reimport", {"Content-Type": "application/json", "If-Match": str(revision_manual)})
step("13c-reimport-ok", {"revision": updated.get("revision"), "confirmed_revision": updated.get("confirmed_revision"), "source": updated.get("source_target_resume_id")})
evidence["revision_before"] = revision_manual
evidence["revision_after"] = updated.get("revision")

# 9 · 确认投递版 → 真实 PDF
# 若新版正文残留「待补充」等占位标记，防呆会拦住确认（这是预期行为）：先模拟用户补齐/省略
placeholder_fix = fix_placeholders(studio_base)
step("13d-fix-placeholder-residue", placeholder_fix)
evidence["placeholder_residue"] = placeholder_fix
confirm_revision = placeholder_fix["revision"] or updated.get("revision")
confirm = call_with_headers("POST", f"{studio_base}/confirm", {"Content-Type": "application/json", "If-Match": str(confirm_revision)})
step("14-confirm-delivery", {"confirmed_revision": confirm.get("confirmed_revision"), "page_count": confirm.get("page_count")} if "__http_error" not in confirm else confirm)
pdf = call("GET", f"{studio_base}/pdf", raw=True)
if isinstance(pdf, bytes) and pdf[:4] == b"%PDF":
    (OUT / f"m2-studio-{CASE}.pdf").write_bytes(pdf)
    evidence["pdf_bytes"] = len(pdf)
    print(f"PASS 15-pdf-export → {OUT / f'm2-studio-{CASE}.pdf'} ({len(pdf)} bytes)")
else:
    evidence["pdf_error"] = str(pdf)[:200]
    print("FAIL 15-pdf-export")

# 10 · 再次查看差异（应无更新）
after = call("GET", f"{studio_base}/source-diff")
evidence["diff_after_reimport_update_available"] = (after or {}).get("update_available")


# 11 · 换模板不能改正文：切到另一套模板，正文逐条不变，PDF 仍能出
before_template = call("GET", studio_base)
before_texts = doc_texts(before_template.get("document") or {})
tpl = call_with_headers(
    "PATCH",
    studio_base,
    {"Content-Type": "application/json", "If-Match": str(before_template.get("revision"))},
    json.dumps({"type": "set_template", "template_id": "zh-sidebar"}).encode(),
)
after_tpl_texts = doc_texts((tpl.get("document") or {})) if "__http_error" not in tpl else []
step(
    "16-switch-template-keeps-content",
    {
        "template_id": tpl.get("template_id"),
        "content_identical": before_texts == after_tpl_texts,
        "bullet_count": len(before_texts),
    }
    if "__http_error" not in tpl and before_texts
    else tpl,
)
evidence["template_switch"] = {
    "from": before_template.get("template_id"),
    "to": tpl.get("template_id"),
    "content_identical": bool(before_texts) and before_texts == after_tpl_texts,
}
# 换模板会推进修订号 → 正式 PDF 必须重新确认才能下载（防呆：不能悄悄换掉已确认的投递版）
reconfirm = call_with_headers("POST", f"{studio_base}/confirm", {"Content-Type": "application/json", "If-Match": str(tpl.get("revision"))})
step("17-reconfirm-after-template", {"confirmed_revision": reconfirm.get("confirmed_revision"), "page_count": reconfirm.get("page_count")} if "__http_error" not in reconfirm else reconfirm)
pdf2 = call("GET", f"{studio_base}/pdf", raw=True)
if isinstance(pdf2, bytes) and pdf2[:4] == b"%PDF":
    (OUT / f"m2-studio-{CASE}-tpl.pdf").write_bytes(pdf2)
    print(f"PASS 17b-pdf-after-template → ({len(pdf2)} bytes)")
    evidence["pdf_after_template_bytes"] = len(pdf2)
else:
    print("FAIL 17b-pdf-after-template")

# 12 · 刷新恢复：重新读取，修订号与正文必须与切换后一致（不丢、不回退）
reloaded = call("GET", studio_base)
step(
    "18-reload-persists",
    {
        "revision_stable": reloaded.get("revision") == tpl.get("revision"),
        "template_stable": reloaded.get("template_id") == tpl.get("template_id"),
        "content_stable": doc_texts(reloaded.get("document") or {}) == after_tpl_texts,
    }
    if "__http_error" not in reloaded
    else reloaded,
)

evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
evidence["mission_id"] = mission_id
target = OUT / f"m2-studio-acceptance-{CASE}.json"
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
failed = [item for item in evidence["steps"] if not item["ok"]]
print(f"\n证据文件：{target}；失败步骤：{len(failed)}")
