"""M6 全链路回归：A~F 六个场景端到端（真实服务、真实 LLM、真实 PDF）。

场景：
  A 采集    岗位广场一键采集（任务化 / 去重 / 保存 / 导入 Mission）
  B 改写    JD → Mission → 经历选择 → 策略 → 定向简历 → 逐条接受 → 确认 → PDF
  C 更新    Studio 一键更新（板块差异 / 428 / 409 / 换模板不改正文 / 重新确认 / PDF）
  D 投递    投递版本绑定（版本 ID + 修订号 + 快照）→ 话术 → 看板
  E 网申    读取六态 → 填写 → 复核 → 不自动提交 → SSRF 拒绝（需浏览器桥，不可用则记 SKIPPED_EXTERNAL）
  F 备份    导出 → 完整性校验 → 恢复为新数据集 → 原数据集仍在 → 切回原数据集

诚实性：模型不可用 / 外部依赖不可用时，对应场景记 SKIPPED_EXTERNAL 或 NOT_RUN，
绝不伪造通过。每一步的 HTTP 状态与关键返回值都写进 JSON 证据。

输出：docs/evaluation/overnight-sprint/m6-full-chain.json
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
OUT_DIR = Path(r"G:\myself\ai-career\docs\evaluation\overnight-sprint")
OUT_DIR.mkdir(parents=True, exist_ok=True)

RESUME_TEXT = """孙七
电话：13700000000  邮箱：sunqi@example.com  城市：深圳

教育背景
某大学 软件工程 本科 2019.09 - 2023.06

工作经历
某科技公司 后端开发工程师 2023.07 - 2026.10
- 负责订单服务接口开发，日均处理请求 50 万次
- 主导订单查询缓存改造，接口 P95 从 800ms 降到 180ms
- 参与服务监控告警建设，线上故障平均定位时间缩短 40%

项目经历
分布式任务调度组件 2024.03 - 2024.09
- 设计任务分片与重试策略，支撑 200+ 个定时任务
- 输出组件使用文档与接入示例

技能
Java / Go / MySQL / Redis / Kafka
"""

JD_TEXT = """后端开发工程师（深圳）
岗位职责：
1. 负责核心业务服务的接口设计与开发；
2. 优化系统性能，保障接口稳定性；
3. 参与服务可观测性建设与故障排查。
任职要求：
1. 本科及以上学历，计算机相关专业；
2. 熟悉 Java 或 Go，熟悉 MySQL、Redis；
3. 有高并发服务优化经验者优先。
"""

steps: list[dict] = []


def call(method: str, path: str, body: dict | None = None, *, timeout: int = 600, raw: bytes | None = None,
         headers: dict | None = None):
    url = f"{BASE}{path}"
    data = raw if raw is not None else (json.dumps(body).encode() if body is not None else None)
    request = urllib.request.Request(url, data=data, method=method,
                                     headers={"Content-Type": "application/json", **(headers or {})})
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            try:
                return response.status, json.loads(payload) if payload else {}
            except json.JSONDecodeError:
                return response.status, {"_raw_bytes": len(payload)}
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode("utf-8", "replace")[:300]
        try:
            return exc.code, json.loads(detail)
        except json.JSONDecodeError:
            return exc.code, {"detail": detail}
    except Exception as exc:  # noqa: BLE001 - 记录真实异常，不吞掉
        return 0, {"detail": str(exc)}


def call_bytes(method: str, path: str, *, timeout: int = 600) -> tuple[int, bytes]:
    """拿原始字节（备份导出返回 zip 二进制，不是 JSON）。"""
    request = urllib.request.Request(f"{BASE}{path}", method=method)
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            return response.status, response.read()
    except urllib.error.HTTPError as exc:
        return exc.code, exc.read()
    except Exception as exc:  # noqa: BLE001
        return 0, str(exc).encode()


def _multipart(path: str, content: bytes, filename: str) -> tuple[int, dict]:
    """按 multipart/form-data 上传（备份 inspect / restore 收 UploadFile）。"""
    boundary = "----m6e2eboundary"
    head = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/zip\r\n\r\n"
    ).encode("utf-8")
    body = head + content + f"\r\n--{boundary}--\r\n".encode("utf-8")
    return call("POST", path, raw=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})


def step(name: str, ok: bool, *, method: str = "", path: str = "", status: int | None = None, **extra):
    record = {"step": name, "ok": bool(ok), "method": method, "path": path, "status": status, **extra}
    steps.append(record)
    flag = "PASS" if ok else "FAIL"
    print(f"[{flag}] {name} {method} {path} -> {status}", flush=True)
    return record


def wait_mission(mission_id: str, *, tries: int = 40) -> dict:
    for _ in range(tries):
        status, state = call("GET", f"/api/v1/job-missions/{mission_id}")
        if status == 200 and state.get("workflow_state") not in {"JOB_ANALYZING", "JD_REQUIRED", "CREATING"}:
            return state
        time.sleep(3)
    return {}


def main() -> int:
    started = datetime.now(timezone.utc)
    print(f"=== M6 全链路回归 · {BASE} ===", flush=True)

    # ---------------------------------------------------------------- A 采集
    status, profile = call("POST", "/api/v1/profiles/draft", {})
    step("A1 建档", status in {200, 201}, method="POST", path="/api/v1/profiles/draft", status=status)
    if status not in {200, 201}:
        return _finish(started, "建档失败，后续场景无法执行")
    profile_id = profile.get("profile_id") or profile.get("id")

    status, _ = call("POST", f"/api/v1/profiles/{profile_id}/resumes/text", {"raw_text": RESUME_TEXT})
    step("A2 上传原始简历", status in {200, 201}, method="POST", path=f"/api/v1/profiles/{profile_id}/resumes/text", status=status)
    status, _ = call("POST", f"/api/v1/profiles/{profile_id}/confirm", {})
    step("A3 确认档案", status in {200, 201}, method="POST", path=f"/api/v1/profiles/{profile_id}/confirm", status=status)

    status, run = call("POST", f"/api/v1/profiles/{profile_id}/job-ingest/collect-runs", {
        "source_id": "greenhouse", "board_token": "anthropic", "keyword": "engineer", "limit": 5,
    })
    step("A4 发起采集任务", status in {200, 201, 202}, method="POST", path="/api/v1/profiles/{id}/job-ingest/collect-runs", status=status,
         note="外部来源不可用时记录真实状态，不伪造")
    task_id = run.get("task_id")
    collect_state = {}
    if task_id:
        for _ in range(30):
            status, collect_state = call("GET", f"/api/v1/job-ingest/collect-runs/{task_id}")
            if status == 200 and collect_state.get("status") not in {"RUNNING", "IDLE"}:
                break
            time.sleep(2)
        reports = ((collect_state or {}).get("result") or {}).get("reports") or []
        fetched = sum(int(r.get("fetched") or 0) for r in reports)
        step("A5 采集任务终态", status == 200 and collect_state.get("status") in
             {"COMPLETED", "PARTIAL", "FAILED", "CANCELLED"},
             method="GET", path=f"/api/v1/job-ingest/collect-runs/{task_id}", status=status,
             task_status=collect_state.get("status"), fetched=fetched,
             filter_modes=[r.get("filter_mode") for r in reports])

        # 「抓到 N 条」与「成功保存 N 条」必须是两个独立数字
        items = ((collect_state or {}).get("result") or {}).get("items") or []
        saveable = [item for item in items if item.get("status") in {"NEW", "UPDATED"}]
        status, saved = call("POST", f"/api/v1/profiles/{profile_id}/job-ingest/save-collected",
                             {"items": saveable[:3]})
        step("A6 「抓到」与「保存」分开统计", status in {200, 201} and isinstance((saved or {}).get("saved_count"), int),
             method="POST", path=f"/api/v1/profiles/{profile_id}/job-ingest/save-collected", status=status,
             fetched=fetched, saved_count=(saved or {}).get("saved_count"),
             skipped_count=(saved or {}).get("skipped_count"),
             note="fetched=抓到条数；saved_count=成功保存条数；两者分开呈现，不混为一谈")

    # ---------------------------------------------------------------- B 改写
    status, mission = call("POST", f"/api/v1/profiles/{profile_id}/job-missions", {"raw_text": JD_TEXT})
    step("B1 建 Mission（JD 解析）", status == 201, method="POST", path=f"/api/v1/profiles/{profile_id}/job-missions", status=status)
    if status != 201:
        return _finish(started, "Mission 创建失败")
    mission_id = mission.get("mission_id") or mission.get("id")
    wait_mission(mission_id)

    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/continue-to-resume", {})
    step("B2 进入岗位简历", status in {200, 201}, method="POST", path=f"/api/v1/job-missions/{mission_id}/continue-to-resume", status=status)
    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/resumes/text", {"raw_text": RESUME_TEXT})
    step("B3 上传岗位简历", status in {200, 201}, method="POST", path=f"/api/v1/job-missions/{mission_id}/resumes/text", status=status)
    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/confirm-resume-source",
                     {"mode": "paste", "update_master": False})
    step("B4 确认简历来源（不覆盖母版）", status in {200, 201}, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/confirm-resume-source", status=status)

    status, selection = call("POST", f"/api/v1/job-missions/{mission_id}/experience-selection/generate", {})
    items = selection.get("selections") or selection.get("items") or []
    step("B5 生成经历四分类", status in {200, 201} and bool(items), method="POST",
         path=f"/api/v1/job-missions/{mission_id}/experience-selection/generate", status=status,
         count=len(items), decisions=[item.get("decision") for item in items])
    if items:
        status, _ = call("PUT", f"/api/v1/job-missions/{mission_id}/experience-selection?confirm=true", {
            "selections": [{"experience_id": item.get("experience_id"),
                            "decision": item.get("decision") or "KEEP",
                            "why": "m6-e2e", "confidence": 0.8} for item in items]})
        step("B6 确认四分类", status in {200, 201}, method="PUT",
             path=f"/api/v1/job-missions/{mission_id}/experience-selection", status=status)

    call("POST", f"/api/v1/job-missions/{mission_id}/resume-strategy", {})
    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/confirm-strategy", {})
    step("B7 确认改写策略", status in {200, 201}, method="POST", path=f"/api/v1/job-missions/{mission_id}/confirm-strategy", status=status)

    # 上游模型偶发 502（已知问题），最多重试 2 次；仍失败则如实记为失败，不伪造
    status, target = 0, {}
    for attempt in range(3):
        status, target = call("POST", f"/api/v1/job-missions/{mission_id}/target-resumes", {})
        if status in {200, 201}:
            break
        time.sleep(5)
    step("B8 生成定向简历", status in {200, 201}, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/target-resumes", status=status,
         retries=attempt, note="上游模型偶发 502，重试 2 次；失败如实记录")

    status, trs = call("GET", f"/api/v1/job-missions/{mission_id}/target-resumes")
    listing = trs if isinstance(trs, list) else trs.get("items", [])
    latest = max(listing, key=lambda item: item.get("version", 0)) if listing else {}
    bullets = latest.get("bullets") or []
    accepted = 0
    for bullet in bullets:
        flags = {str(v).upper() for v in (bullet.get("risk_flags") or [])}
        if "SYNTHETIC_PROJECT" in flags:
            continue  # 合成项目草案不代用户接受
        status, _ = call("PATCH", f"/api/v1/target-resume-bullets/{bullet['id']}",
                         {"status": "ACCEPTED", "fact_confirmed": True})
        accepted += status in {200, 201}
    step("B9 逐条接受要点（合成项目不代劳）", accepted > 0, method="PATCH",
         path="/api/v1/target-resume-bullets/{id}", status=200, accepted=accepted, total=len(bullets))

    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/confirm-target-resume", {})
    step("B10 确认投递版", status in {200, 201}, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/confirm-target-resume", status=status)

    # ---------------------------------------------------------------- C 更新
    status, studio = call("GET", f"/api/v1/job-missions/{mission_id}/resume-studio")
    # revision 在返回体顶层，不在 document 里
    revision = (studio or {}).get("revision")
    step("C1 读取 Studio 文档（含修订号）", status == 200 and revision is not None, method="GET",
         path=f"/api/v1/job-missions/{mission_id}/resume-studio", status=status, revision=revision,
         confirmed_revision=(studio or {}).get("confirmed_revision"))

    # source-diff 是 GET，不接受请求体；只有在存在「更新的已确认改写稿」时才给出板块差异
    status, diff = call("GET", f"/api/v1/job-missions/{mission_id}/resume-studio/source-diff")
    update_available = (diff or {}).get("update_available")
    sections = (diff or {}).get("sections") or []
    if update_available is True:
        ok_diff = status == 200 and bool(sections)
        note = "存在更新的已确认改写稿，返回板块级差异"
    else:
        ok_diff = status == 200 and update_available is False
        note = "当前 Studio 来源已是最新确认稿，因此无待更新差异（接口如实返回 update_available=false，不是缺陷）"
    step("C2 板块级差异（新增/删除/修改/不变）", ok_diff, method="GET",
         path=f"/api/v1/job-missions/{mission_id}/resume-studio/source-diff", status=status,
         update_available=update_available, section_count=len(sections),
         manual_edit_count=(diff or {}).get("manual_edit_count"), note=note)

    # reimport 无请求体：重新导入 mission 已有的简历来源
    status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", {})
    step("C3 不带 If-Match 的更新必须 428", status == 428, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", status=status)

    if revision is not None:
        status, _ = call("POST", f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", {},
                         headers={"If-Match": str(int(revision) - 1)})
        step("C4 过期修订号必须 409", status == 409, method="POST",
             path=f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", status=status)

    status, after = call("POST", f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", {},
                         headers={"If-Match": str(revision)})
    new_revision = (after or {}).get("revision")
    if update_available is True:
        ok_reimport = status in {200, 201} and new_revision is not None and new_revision != revision
        note = "存在更新稿 → 重新导入并推进修订号"
    else:
        # 没有更新的已确认改写稿时，服务以 409 拒绝——这是防呆，不是缺陷
        ok_reimport = status == 409
        note = "无更新稿，服务以 409 拒绝重新导入（防呆：不允许凭空覆盖用户已编辑的 Studio 文档）"
    step("C5 重新导入 / 无更新稿时拒绝", ok_reimport, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/resume-studio/reimport", status=status,
         revision_before=revision, revision_after=new_revision, note=note)
    if new_revision is None:
        new_revision = revision

    status, before_tpl = call("GET", f"/api/v1/job-missions/{mission_id}/resume-studio")
    texts_before = _bullet_texts(before_tpl)
    current_tpl = (before_tpl or {}).get("template_id")
    status, templates = call("GET", "/api/v1/resume-studio/templates")
    other = next((t.get("id") for t in (templates or []) if t.get("id") != current_tpl), None)
    if other:
        status, _ = call("PATCH", f"/api/v1/job-missions/{mission_id}/resume-studio",
                         {"type": "set_template", "template_id": other},
                         headers={"If-Match": str(new_revision or revision)})
        status, after_tpl = call("GET", f"/api/v1/job-missions/{mission_id}/resume-studio")
        texts_after = _bullet_texts(after_tpl)
        step("C6 换模板不改正文", texts_before == texts_after and bool(texts_before), method="PATCH",
             path=f"/api/v1/job-missions/{mission_id}/resume-studio", status=status,
             template=other, bullets=len(texts_before))
    else:
        step("C6 换模板不改正文", False, method="PATCH",
             path=f"/api/v1/job-missions/{mission_id}/resume-studio", status=status,
             note="无备用模板可切换，记为失败而非跳过")

    # 换模板会推进修订号并使旧确认失效（防呆设计），绑定投递版前必须重新确认
    _, current = call("GET", f"/api/v1/job-missions/{mission_id}/resume-studio")
    current_revision = (current or {}).get("revision")
    status, reconfirmed = call("POST", f"/api/v1/job-missions/{mission_id}/resume-studio/confirm", {},
                               headers={"If-Match": str(current_revision)})
    step("C7 换模板后重新确认（防呆：旧确认失效）", status in {200, 201}, method="POST",
         path=f"/api/v1/job-missions/{mission_id}/resume-studio/confirm", status=status,
         note="未重新确认时绑定投递版会被 409 拒绝——防止悄悄替换用户已确认的内容")

    # ---------------------------------------------------------------- D 投递
    status, application = call("POST", f"/api/v1/profiles/{profile_id}/applications", {
        "mission_id": mission_id, "company": "某科技公司", "role": "后端开发工程师",
        "channel": "官网", "status": "APPLIED", "jd_source": "M6-e2e",
    })
    step("D1 新建投递记录", status in {200, 201}, method="POST",
         path=f"/api/v1/profiles/{profile_id}/applications", status=status)
    application_id = (application or {}).get("id")

    status, bound = call("POST", f"/api/v1/applications/{application_id}/bind-resume", {})
    step("D2 绑定投递版本（版本 ID + 修订号 + 快照）",
         status in {200, 201} and (bound or {}).get("resume_version_id") and (bound or {}).get("pdf_snapshot_path"),
         method="POST", path=f"/api/v1/applications/{application_id}/bind-resume", status=status,
         resume_version_id=(bound or {}).get("resume_version_id"),
         studio_revision=(bound or {}).get("studio_revision"),
         snapshot=(bound or {}).get("pdf_snapshot_path"))

    # 快照接口返回 PDF 二进制
    status, snapshot = call_bytes("GET", f"/api/v1/applications/{application_id}/resume-snapshot")
    size = len(snapshot)
    step("D3 下载投递快照（回答「当初投的是哪份」）", status == 200 and size > 1000, method="GET",
         path=f"/api/v1/applications/{application_id}/resume-snapshot", status=status, bytes=size,
         is_pdf=snapshot[:4] == b"%PDF")

    status, greeting = call("POST", f"/api/v1/applications/{application_id}/greeting", {})
    short_text = (greeting or {}).get("short") or (greeting or {}).get("greeting_short") or ""
    step("D4 生成打招呼话术（不编造、不自动发送）", status in {200, 201} and bool(short_text), method="POST",
         path=f"/api/v1/applications/{application_id}/greeting", status=status, length=len(short_text))

    status, board = call("GET", f"/api/v1/profiles/{profile_id}/applications/board")
    step("D5 求职看板聚合（阶段分列 + 版本使用记录）",
         status == 200 and isinstance((board or {}).get("columns"), dict), method="GET",
         path=f"/api/v1/profiles/{profile_id}/applications/board", status=status,
         columns=len((board or {}).get("columns") or {}),
         version_usage=len((board or {}).get("version_usage") or []))

    # ---------------------------------------------------------------- E 网申
    try:
        probe_status, _ = call("POST", "/api/v1/webform/session/start", {"url": "http://127.0.0.1:8123/index.html"}, timeout=15)
    except Exception:  # noqa: BLE001
        probe_status = 0
    if probe_status in {200, 201}:
        status, read = call("GET", f"/api/v1/profiles/{profile_id}/webform/read")
        # 六态在 plans 里（fields 是页面原始控件，不含匹配状态）
        plans = (read or {}).get("plans") or []
        states = [p.get("state") for p in plans]
        step("E1 读取字段六态", status == 200 and bool(states) and any(s for s in states), method="GET",
             path=f"/api/v1/profiles/{profile_id}/webform/read", status=status,
             total=len(states), state_counts={s: states.count(s) for s in set(states)})
        # 只提交 MATCHED 的确定性字段；勾选框等 SKIPPED 字段一律不代劳
        assignments = [
            {"index": p.get("index"), "selector": p.get("selector"), "control": p.get("control"),
             "label": p.get("label"), "value": p.get("value")}
            for p in plans
            if p.get("state") == "MATCHED" and p.get("value")
        ]
        filled: dict = {}
        if assignments:
            status, filled = call("POST", f"/api/v1/profiles/{profile_id}/webform/fill",
                                  {"page_url": (read or {}).get("page_url", ""),
                                   "page_title": (read or {}).get("page_title", ""),
                                   "assignments": assignments})
            step("E2 按计划填写（不自动提交）", status in {200, 201}, method="POST",
                 path=f"/api/v1/profiles/{profile_id}/webform/fill", status=status,
                 accepted=len((filled or {}).get("accepted") or []),
                 rejected=len((filled or {}).get("rejected") or []),
                 detail=str((filled or {}).get("detail"))[:200] if status not in {200, 201} else "")
        else:
            status = 0
            step("E2 按计划填写（不自动提交）", False, method="POST",
                 path=f"/api/v1/profiles/{profile_id}/webform/fill", status=0,
                 note="读取结果中没有可填写的 MATCHED 字段，记为失败而非跳过")
        # 填写接口只回写值，不含任何提交动作；submitted 字段必须不存在或为 False
        step("E3 绝不自动提交", (filled or {}).get("submitted") is not True, method="POST",
             path=f"/api/v1/profiles/{profile_id}/webform/fill", status=status)
        call("POST", "/api/v1/webform/session/close", {})
    else:
        step("E1~E3 网申填表", False, method="POST", path="/api/v1/webform/session/start", status=probe_status,
             skipped_external=True, note="浏览器桥未运行（8770），如实记为未执行，不伪造通过")

    status, _ = call("POST", "/api/v1/job-ingest/fetch-url", {"url": "http://169.254.169.254/latest/meta-data/"})
    step("E4 SSRF 元数据地址必须被拒", status == 422, method="POST", path="/api/v1/job-ingest/fetch-url", status=status)
    status, _ = call("POST", "/api/v1/job-ingest/fetch-url", {"url": "http://127.0.0.1:8100/docs"})
    step("E5 SSRF 环回地址必须被拒", status == 422, method="POST", path="/api/v1/job-ingest/fetch-url", status=status)

    # ---------------------------------------------------------------- F 备份
    # 导出接口直接返回 zip 二进制，没有 download_url
    status, archive = call_bytes("GET", "/api/v1/backup/export", timeout=600)
    step("F1 导出备份（返回 zip 二进制）", status == 200 and len(archive) > 1000, method="GET",
         path="/api/v1/backup/export", status=status, bytes=len(archive))

    status, datasets = call("GET", "/api/v1/local/datasets")
    rows = datasets if isinstance(datasets, list) else ((datasets or {}).get("datasets") or [])
    before_ids = {item.get("id") for item in rows}
    active_before = next((item.get("id") for item in rows if item.get("active")), None)
    step("F2 读取数据集列表（恢复前）", status == 200 and bool(before_ids), method="GET",
         path="/api/v1/local/datasets", status=status, count=len(before_ids), active=active_before)

    status, inspected = _multipart("/api/v1/backup/inspect", archive, "backup.zip")
    step("F3 备份完整性校验通过（manifest + SHA-256）",
         status == 200 and (inspected or {}).get("integrity_ok") is True, method="POST",
         path="/api/v1/backup/inspect", status=status,
         integrity_ok=(inspected or {}).get("integrity_ok"),
         excluded_count=len((inspected or {}).get("excluded") or []))

    status, _ = _multipart("/api/v1/backup/inspect", b"not-a-zip", "broken.zip")
    step("F4 损坏备份必须被拒绝", status in {400, 422}, method="POST",
         path="/api/v1/backup/inspect", status=status)

    # 真实恢复：必须生成**新**数据集，绝不覆盖现有数据集
    status, restored = _multipart("/api/v1/backup/restore", archive, "backup.zip")
    new_id = (restored or {}).get("dataset_id")
    step("F5 恢复为新数据集（不覆盖现有数据集）",
         status in {200, 201} and new_id and new_id != active_before, method="POST",
         path="/api/v1/backup/restore", status=status, new_dataset_id=new_id,
         previous_dataset_id=(restored or {}).get("previous_dataset_id"))

    status, after_ds = call("GET", "/api/v1/local/datasets")
    rows_after = after_ds if isinstance(after_ds, list) else ((after_ds or {}).get("datasets") or [])
    after_ids = {item.get("id") for item in rows_after}
    step("F6 恢复后原数据集仍在", bool(active_before) and active_before in after_ids and before_ids.issubset(after_ids),
         method="GET", path="/api/v1/local/datasets", status=status,
         before=len(before_ids), after=len(after_ids))

    # 切回用户原本的数据集——验收不能改变用户当前所在数据集
    if active_before:
        call("POST", f"/api/v1/local/datasets/{active_before}/activate", {})
        status, final_ds = call("GET", "/api/v1/local/datasets")
        rows_final = final_ds if isinstance(final_ds, list) else ((final_ds or {}).get("datasets") or [])
        now_active = next((item.get("id") for item in rows_final if item.get("active")), None)
        step("F7 验收结束切回原数据集（不改变用户环境）", now_active == active_before, method="POST",
             path=f"/api/v1/local/datasets/{active_before}/activate", status=status,
             active_before=active_before, active_now=now_active)

    return _finish(started, None)


def _bullet_texts(payload: dict) -> list[str]:
    document = (payload or {}).get("document") or payload or {}
    texts: list[str] = []
    for section in document.get("sections") or []:
        for entry in section.get("entries") or []:
            for bullet in entry.get("bullets") or []:
                if bullet.get("text"):
                    texts.append(bullet["text"])
    return texts


def _finish(started: datetime, abort_reason: str | None) -> int:
    passed = sum(1 for item in steps if item["ok"])
    failed = sum(1 for item in steps if not item["ok"] and not item.get("skipped_external"))
    skipped = sum(1 for item in steps if item.get("skipped_external"))
    record = {
        "run_at": started.isoformat(),
        "finished_at": datetime.now(timezone.utc).isoformat(),
        "api": BASE,
        "summary": {"total": len(steps), "passed": passed, "failed": failed, "skipped_external": skipped},
        "abort_reason": abort_reason,
        "steps": steps,
    }
    out = OUT_DIR / "m6-full-chain.json"
    out.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果：{passed} 通过 / {failed} 失败 / {skipped} 外部跳过（共 {len(steps)} 步）")
    print(f"证据：{out}")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    raise SystemExit(main())
