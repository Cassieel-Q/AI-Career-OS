# Overnight Sprint 进度

分支：`feature/resumeforge-overnight`（基于 `feature/resumeforge-48h` 的 `d027426`）

## M1 · 网页一键采集（任务化）

状态：**DONE_VERIFIED**（后端 8 用例验收脚本 + 浏览器 E2E 8/8）

### 本轮新增/修复

- 采集改为**任务接口**：`POST /api/v1/profiles/{id}/job-ingest/collect-runs`（立即返回 task_id），
  `GET /api/v1/job-ingest/collect-runs/{task_id}` 轮询，`POST .../cancel` 取消。
  任务状态机：`IDLE / RUNNING / COMPLETED / PARTIAL / FAILED / CANCELLED`。
- 结果状态：`NEW / DUPLICATE / UPDATED / NEEDS_REVIEW / FAILED`，由 `classify_collected`
  与岗位库逐条比对得出（正文指纹 `content_hash` = role+location+落库文本，去 URL 与来源随机串）。
- 统计条拆分「抓到 / 筛选后 / 新增 / 已存在 / 有更新 / 待确认 / 不可用 / 可保存」，
  不再把「抓到 100 条」与「保存 100 个」混为一谈。
- 新增第 4 个公开来源 **Remotive**（服务端关键词检索）；适配器契约
  `ADAPTER_SPECS`：capabilities（如实声明：目前所有来源都不支持服务端城市/实习过滤，`filter_mode=local`）、
  validate（缺 board token 明确报错）、health_check（真实请求一次）。
  `GET /api/v1/job-ingest/adapters`、`POST /api/v1/job-ingest/adapters/{source}/health-check`。
- HTTP 层加节流（同源最小间隔）、重试（429/5xx 退避）、整轮时间上限（超时标 TIMEOUT/PARTIAL）。
- 前端：任务状态徽章、实时进度、取消按钮、结果状态列、来源「自检」按钮、
  Greenhouse/Lever 已验证预设一键填入（`stripe/airbnb/anthropic/figma/databricks/discord/reddit/roblox/coinbase/thoughtworks/elastic/scaleai/figureai`；
  Lever：`leverdemo/palantir/spotify`）、保存时可选「同时更新有更新的已有岗位」。
- 已保存行无指纹的历史数据：回填指纹后可正确参与去重。

### 修掉的真实缺陷

1. RemoteOK JD 内嵌随机串（`RMS4yMDMuMTEwLjIz` 反垃圾标记）→ 每次采集都误判 UPDATED。
   修复：`stable_text()` 去随机 token 后再哈希。
2. `save-collected` 二次保存同岗位时 `db.get(UUID列, 字符串id)` 抛
   `'str' object has no attribute 'hex'` → 页面显示 Failed to fetch（500）。
   修复：`_load_duplicate_row` 先转 UUID；补回归测试。
3. 统计在 `classify_collected` 之前计算 → new/duplicate 恒为 0。修复：`recompute_result_totals` 在标注后重算。
4. Remotive `job_type` 未映射 → 全职岗位被标 UNKNOWN。

### 证据

- `docs/evaluation/overnight-sprint/m1-collect-acceptance.json`（8 个用例：真实采集/去重/空结果/来源404/字段缺失NEEDS_REVIEW/城市过滤排除/用户取消/保存后导入Mission）
- `docs/screenshots/overnight-m1/01..06.png` + `e2e-result.json`（浏览器 E2E 8/8）
- 测试：`tests/test_job_collect_tasks.py`（19 项）+ `tests/test_job_collection.py`（23 项）

### 复现命令

```powershell
cd apps/api; .venv\Scripts\python -m pytest tests/test_job_collect_tasks.py tests/test_job_collection.py -q
cd apps\api; .venv\Scripts\python scripts\collect_acceptance.py http://127.0.0.1:8100 <profile_id>
cd apps\web; node scripts\e2e-overnight-m1.cjs
```
