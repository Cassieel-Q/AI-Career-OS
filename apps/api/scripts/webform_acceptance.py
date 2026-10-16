"""M4 验收：网申填表真实兼容性与安全（真实浏览器桥 + 真实本地表单页）。

流程：
  1) 建档 + 真实 LLM 抽取 + 确认（保证 profile.full_name/phone/email/city 有值）
  2) 启动受控浏览器会话 → 打开本地测试表单（http://127.0.0.1:8123/index.html）
  3) 读取表单 → 规则匹配（纯规则，模型不可用不影响）→ 断言六态分布
  4) 执行填写（只提交 MATCHED 的字段）
  5) 重新读取 → 断言：文本/邮箱/电话/城市/学历下拉/毕业时间/专业已填；
     密码 / 验证码 / 复选框 / 文件上传 / 禁用控件未被填写；
     提交按钮未被点击（页面仍是表单页）。
  6) SSRF：通过 API 请求内网地址 → 422 拒绝

输出：docs/evaluation/overnight-sprint/m4-webform-acceptance.json
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
FORM_URL = "http://127.0.0.1:8123/index.html"
OUT = Path(r"G:\myself\ai-career\docs\evaluation\overnight-sprint")
OUT.mkdir(parents=True, exist_ok=True)

RESUME_TEXT = """周八
电话：13400000000  邮箱：zhouba@example.com  城市：成都

教育背景
某大学 市场营销 本科 2020.09 - 2024.06

实习经历
某快消公司 品牌运营实习 2023.06 - 2023.12
- 负责小红书内容排期，累计产出 60 篇笔记
- 联动达人完成新品测评，曝光 12 万

技能
内容策划 / Excel / 数据看板
"""

evidence: dict = {"started_at": datetime.now(timezone.utc).isoformat(), "base_url": BASE, "form_url": FORM_URL, "steps": []}


def call(method: str, path: str, body: dict | None = None, headers: dict | None = None, raw: bool = False, timeout: int = 600):
    data = json.dumps(body or {}).encode() if body is not None else None
    request = urllib.request.Request(BASE + path, data=data, headers={"Content-Type": "application/json", **(headers or {})}, method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            if raw:
                return response.status, payload
            return response.status, (json.loads(payload) if payload else {})
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:400]
        return exc.code, {"__error": detail}


def step(name: str, ok: bool, result) -> None:
    evidence["steps"].append({"step": name, "ok": ok, "result": result})
    print(("PASS " if ok else "FAIL ") + name + ("" if ok else f" → {json.dumps(result, ensure_ascii=False)[:400]}"))


# 1 · 建档（真实 LLM 抽取姓名/电话/邮箱/城市/教育）
status, profile = call("POST", "/api/v1/profiles/draft")
profile_id = profile.get("profile_id") or profile.get("id")
call("POST", f"/api/v1/profiles/{profile_id}/resumes/text", {"raw_text": RESUME_TEXT})
call("POST", f"/api/v1/profiles/{profile_id}/confirm")
# 等抽取完成：full_name 出现即认为 facts 可用
facts_ready = False
for _ in range(40):
    status, facts = call("GET", f"/api/v1/profiles/{profile_id}/application-fill-facts")
    if facts.get("full_name"):
        facts_ready = True
        break
    time.sleep(3)
step("1-profile-facts-ready", facts_ready, {k: facts.get(k) for k in ("full_name", "phone", "email", "city")})

# 2 · 打开受控浏览器会话
status, opened = call("POST", "/api/v1/webform/session/start", {"url": FORM_URL})
step("2-session-start", status == 200, opened if status != 200 else {"ok": opened.get("ok"), "pageUrl": opened.get("pageUrl")})
if status != 200:
    status, opened = call("POST", "/api/v1/webform/session/open", {"url": FORM_URL})
else:
    status, opened = call("POST", "/api/v1/webform/session/open", {"url": FORM_URL})
step("2b-session-open", status == 200 and FORM_URL in str(opened.get("pageUrl", "")), opened if (status != 200 or FORM_URL not in str(opened.get("pageUrl", ""))) else {"pageUrl": opened.get("pageUrl")})

# 3 · 读取 + 匹配计划
status, plan = call("GET", f"/api/v1/profiles/{profile_id}/webform/read")
plans = plan.get("plans", [])
by_label = {item.get("label", "") + "|" + item.get("control", ""): item for item in plans}


def state_of(label, control=None):
    """按 label 定位计划；同名 label（页面文案被启发式误读时）用控件类型区分。"""
    for item in plans:
        if item.get("label", "") == label and (control is None or item.get("control") == control):
            return item.get("state")
    return None
summary = plan.get("summary", {})
step("3-read-plan", status == 200 and len(plans) >= 10, {"total": summary.get("total"), "by_support": summary.get("by_support")})

# 六态断言


checks = {
    "MATCHED:姓名": state_of("姓名", "text") == "MATCHED",
    "MATCHED:手机号码": state_of("手机号码") == "MATCHED",
    "MATCHED:电子邮箱": state_of("电子邮箱") == "MATCHED",
    "MATCHED:现居城市": state_of("现居城市") == "MATCHED",
    "MATCHED:最高学历(下拉)": state_of("最高学历") == "MATCHED",
    "MATCHED:毕业时间(month)": state_of("毕业时间") == "MATCHED",
    "MATCHED:所学专业": state_of("所学专业") == "MATCHED",
    "READ:自我介绍(低置信)": state_of("请用一段话介绍你自己（低置信度示例：规则不匹配，交由人工确认）") == "READ",
    "SKIPPED:禁用控件": state_of("系统编号（禁用控件示例）") == "SKIPPED",
    "SKIPPED:密码": state_of("设置查询密码（永不自动填写）") == "SKIPPED",
    "SKIPPED:验证码": state_of("短信验证码（永不自动填写）") == "SKIPPED",
    "SKIPPED:文件上传": state_of("上传简历附件（不支持自动上传）") == "SKIPPED",
    "SKIPPED:同意条款勾选": all(item.get("state") == "SKIPPED" for item in plans if item.get("control") == "checkbox"),
    "READ:内推人工号(name含code不误判)": state_of("内推人工号（标签不规范示例）") == "READ",
    "隐藏字段不可见": not any("内部跟踪号" in (item.get("label") or "") for item in plans),
}
step("4-plan-states", all(checks.values()), checks)
evidence["plan_summary"] = summary
evidence["plan_checks"] = checks

# 4 · 执行填写：只提交 MATCHED 字段（模拟用户在预览里确认这些字段）
fill_assignments = [
    {"index": item.get("index"), "selector": item.get("selector"), "control": item.get("control"), "label": item.get("label"), "value": item.get("value")}
    for item in plans
    if item.get("state") == "MATCHED" and item.get("value")
]
status, filled = call("POST", f"/api/v1/profiles/{profile_id}/webform/fill", {
    "page_url": plan.get("page_url", ""),
    "page_title": plan.get("page_title", ""),
    "assignments": fill_assignments,
})
step("5-fill", status == 200 and filled.get("summary", {}).get("filled", 0) >= 6, {
    "summary": filled.get("summary"),
    "note": filled.get("note"),
    "results": filled.get("results"),
    "assignments_sent": [item.get("label") for item in fill_assignments],
})
evidence["fill_summary"] = filled.get("summary")

# 5 · 重新读取验证
status, verify = call("GET", f"/api/v1/profiles/{profile_id}/webform/read")
vfields = {item.get("label"): item for item in verify.get("fields", [])}
vlist = [(item.get("label") or "", item.get("value", ""), item.get("control", "")) for item in verify.get("fields", [])]


def field_value(needle, control=None):
    """按 label 子串取值；同名 label（如被误标为「姓名」的 checkbox）只匹配指定控件类型。"""
    for label, value, ctrl in vlist:
        if needle in label and (control is None or ctrl == control):
            return value
    return ""


post_checks = {
    "姓名已填": "周八" in field_value("姓名", "text"),
    "同意条款未被代勾": field_value("同意", "checkbox") not in ("on", True),
    "手机已填": "13400000000" in field_value("手机"),
    "邮箱已填": "zhouba@example.com" in field_value("邮箱"),
    "城市已填": "成都" in field_value("城市"),
    "学历已选(本科)": "本科" in field_value("学历"),
    "专业已填": "市场营销" in field_value("专业"),
    "密码未填": field_value("密码") == "",
    "验证码未填": field_value("验证码") == "",
    "附件未填": field_value("上传简历附件") in ("", None),
    "禁用控件未被改动": field_value("系统编号") == "AUTO-9527",
}
step("6-verify-filled", all(post_checks.values()), post_checks)
evidence["post_checks"] = post_checks

# 6 · 提交按钮未被点击：页面 URL 仍是表单（不是 /submit）
still_form = verify.get("page_url", "").endswith("/index.html")
step("7-never-submitted", still_form, {"page_url": verify.get("page_url")})

# 7 · SSRF：粘贴内网链接 → 422
status, blocked = call("POST", "/api/v1/job-ingest/fetch-url", {"url": "http://169.254.169.254/latest/meta-data/"}, timeout=30)
step("8-ssrf-metadata-blocked", status == 422, {"status": status, "detail": str(blocked)[:200]})
status, blocked2 = call("POST", "/api/v1/job-ingest/fetch-url", {"url": "http://127.0.0.1:8100/api/v1/profiles"}, timeout=30)
step("9-ssrf-loopback-blocked", status == 422, {"status": status})

call("POST", "/api/v1/webform/session/close")

evidence["finished_at"] = datetime.now(timezone.utc).isoformat()
evidence["profile_id"] = profile_id
target = OUT / "m4-webform-acceptance.json"
target.write_text(json.dumps(evidence, ensure_ascii=False, indent=2, default=str), encoding="utf-8")
failed = [item for item in evidence["steps"] if not item["ok"]]
print(f"\n证据文件：{target}；失败步骤：{len(failed)}")
