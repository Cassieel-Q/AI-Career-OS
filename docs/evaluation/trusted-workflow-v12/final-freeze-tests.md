# FINAL FREEZE 测试结果（2026-10-19）

> 本文件记录冻结前的真实执行结果。**没有跑过的项一律标 `NOT_RUN`，没有人工金标准的项一律 `UNRATED`。**
> 旧文档（`test-results.md`）里的数字对应 2026-10-18 的 HEAD `3348fd3`，不要混用。

## 一、总览

| 项目 | 命令 | 结果 |
| --- | --- | --- |
| 后端全量 | `apps/api: .venv/Scripts/python -m pytest -q` | **1140 passed / 6 failed / 5 skipped**（197.7s） |
| 前端单测 | `apps/web: npm test` | **276 passed / 0 failed** |
| TypeScript | `apps/web: npx tsc --noEmit` | **0 error** |
| 生产构建 | `apps/web: NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8100 npm run build` | **EXIT=0**（编译 + 类型检查通过） |
| 浏览器 E2E | `node docs/.../browser/e2e-trusted-workflow.cjs` | **43/43 通过**（7 条主流程，production build 上跑）见 `browser-e2e.md` |
| 闸门 A/B 重放 | `python evals/benchmark/scripts/gate_replay.py` | 见 `gate-replay.md`（模型调用 0 次） |
| 备份/恢复 | 真实 API：导出 → inspect → restore → 激活 → 比对计数 | **通过**（见下） |

## 二、与基线对比（关键）

基线（`main`，`a033b21`）后端同样为 **7 项**失败。本轮修掉 1 项，**新增失败 0**：

| 用例 | 基线 | 现在 | 说明 |
| --- | --- | --- | --- |
| `test_target_jobs::test_claim_analysis_fingerprint_requires_regeneration_after_profile_change` | FAILED | **PASSED（已改造）** | 旧断言要求 409，实现却是「静默刷新指纹」——等于把旧分析伪装成新鲜结果。已改为「只标记不替换」（`stale=True` + 原因），并补空主张必 409 的对照用例 |

### 剩余 6 项失败：风险分类

| 用例 | 失败原因 | 是否影响事实可信 / 投递版本 / 数据安全 | 结论 |
| --- | --- | --- | --- |
| `test_claim_provider::test_claim_provider_normalizes_partial_claim_schema` | 降级文案断言（`做过` 前缀 vs 原句） | 否 | 保留在已知问题 |
| `test_gap_analysis::test_gap_analysis_uses_confirmed_profile_and_allowed_states` | 能力簇名称本地化后找不到英文键（StopIteration） | 否 | 保留 |
| `test_market_profile::...grounded_capability_clusters...` | 期望英文 `Technical capability`，实际中文 `技术能力` | 否 | 保留 |
| `test_priorities::test_priority_algorithm_is_stable_and_caps_now` | 期望 `Product execution`，实际 `产品落地` | 否 | 保留 |
| `test_resume_reliability::test_repeated_education_merge_preserves_optional_fields_and_courses` | 教育经历去重合并后条数 2 ≠ 1 | 否（解析质量，不影响事实签名/投递/数据） | 保留 |
| `test_roadmap::test_four_week_roadmap_is_persisted_with_actionable_tasks` | 同能力簇中文/英文标签 | 否 | 保留 |

四项（gap_analysis / market_profile / priorities / roadmap）根因相同：能力簇名称已本地化成中文，
测试仍断言英文。属历史遗留的断言口径问题，不影响用户可见功能。

## 三、17 条主流程覆盖

| # | 主流程 | 证据 | 结果 |
| --- | --- | --- | --- |
| 1 | 无模型建档与简历原文编辑 | E2E 流程6；`test_local_profile_routes` | PASS |
| 2 | 测试 JD 导入 | E2E 流程1/3 | PASS |
| 3 | 岗位匹配及建议一致性 | `test_match_contract.py`（34 项） | PASS |
| 4 | 事实提取 / 用户核对 / 采纳状态分离 | `test_fact_trust.py`；E2E 流程2 | PASS |
| 5 | 经历字段受控修正 | `test_controlled_fact_correction.py`（19 项）；E2E 流程7（8 项） | PASS |
| 6 | 修改事实后相关分析过期 | 本轮修复；`test_target_jobs` 新契约 + `test_controlled_fact_correction` | PASS（本轮修复） |
| 7 | 三个岗位版本互相隔离 | E2E 流程3；`test_multi_job_version_consistency.py`（13 项） | PASS |
| 8 | Studio 18 套模板可用 | `list_templates()` → **18**；`test_template_layout.py` | PASS |
| 9 | 草稿 PDF 含 DRAFT 标识 | E2E 流程1；`test_resume_studio_routes.py` | PASS |
| 10 | 正式投递 PDF 通过事实与导出检查 | E2E 流程1（缺姓名 409 → 补姓名 → 通过） | PASS |
| 11 | 修改 Studio 后历史投递 PDF 不变 | E2E 流程4；快照哈希不变断言 | PASS |
| 12 | 面试使用对应投递版本 | E2E 流程4（`delivered=true`） | PASS |
| 13 | 清 LocalStorage 后可恢复档案 | E2E 流程5 | PASS |
| 14 | 顺顺 `list_jobs` / `list_applications` | `test_assistant_write_proposals.py` | PASS |
| 15 | 模型中心既有配置不回归 | `test_model_config.py`（96 项组合中） | PASS |
| 16 | 桌面图标启动应用 | 快捷方式存在；`career-app.ps1 -Action status` 实跑成功；2026-10-17 完整启停验收 17/17 | PASS（见下） |
| 17 | 数据备份与恢复不丢资料 | 本轮真跑：导出 105,631 字节 → inspect → 恢复为新数据集 → 计数一致 | PASS |

### 16 的补充说明（2026-10-19 12:48–12:56 实跑）

- 桌面快捷方式 `AI Career OS.lnk` / `停止 AI Career OS.lnk` 存在（2026-10-17 22:47 创建），
  指向 `scripts/local-app/career-app.ps1`；
- `career-app.ps1 -Action status`：正确报「后端/前端/浏览器桥 未运行，模式 production」；
- `career-app.ps1 -Action start`：
  - 浏览器桥 8770 就绪；
  - 后端 8100 就绪（`/health` 探活通过），数据目录 `C:\Users\覆水\AppData\Local\AICareerOS`；
  - 前端 **production 模式**自动落到 **3002**（3000/3001 已被其它项目占用，未强抢）；
  - Edge 独立窗口打开 `http://127.0.0.1:3002`；
- `career-app.ps1 -Action stop`：`[OK] 已停止（其他项目的服务未受影响）`；
  复查端口：本项目 8100/3002/8770 **全部释放**，其它项目的 **3000 与 8000 仍在监听**（未被误杀）。

> 注：启动器拉起的进程会随本工具的会话结束被回收，所以 HTTP 探测以启动器自带的就绪探活
> （「后端就绪 /health」「前端就绪」）为准；真实使用时由 Explorer 双击启动，进程常驻。
> 更完整的 start → start → stop → start 序列验收是 2026-10-17 的记录：
> **17/17 通过**（`docs/evaluation/boss-local-app/launcher-test.json`），启动器本轮未改动。

## 三之二、本轮回归暴露并修掉的 E2E 自身缺陷（不是产品缺陷）

跑回归时发现的 3 个问题全部出在测试脚本侧，已修，重跑 43/43：

| 现象 | 根因 | 处理 |
| --- | --- | --- |
| 流程3 三份岗位版少一份（修订号 map 缺键） | `confirm-target-resume` 409：改写要点未逐条接受（产品防空白简历的真实闸门） | 补 `acceptBullets()` 走 `PATCH /target-resume-bullets/{id}` |
| 流程7 页面上看不到「受控修正」入口 | 事实默认收起，且「简历」页档案 ID 来自 localStorage 而非 URL 参数（流程5 刚清过存储） | 先 `addInitScript` 写回档案 ID，再点开事实 |
| 失败时看不出是哪份岗位出问题 | `undefined` 被 `JSON.stringify` 静默丢键 | 修订号显式写 `null` |

> 这三条都不会改变产品行为；之前那次 39/43 是**测试脚本**没跟上产品真实流程，不是产品回归。

## 四、备份 / 恢复实测（隔离数据集）

```text
GET  /api/v1/backup/export            → 200, 105,631 字节
POST /api/v1/backup/inspect           → 200, 格式 ai-career-os-backup v1
POST /api/v1/backup/restore           → 200, 新数据集 ds26101911372117f2
POST /api/v1/local/datasets/{id}/activate → 200
GET  /api/v1/backup/summary           → 计数与恢复前完全一致：
     user_profiles 16 / education 16 / experiences 16 / profile_skills 61 /
     job_missions 30 / target_resumes 17 / target_resume_bullets 21 /
     resume_studio_documents 16 / job_applications 7 / resume_claims 6
```

**全程只碰隔离数据集**（`AI_CAREER_DATA_DIR=.runtime/e2e-v12`）；
用户真实数据目录 `%LOCALAPPDATA%\AICareerOS` 的 `active_dataset` 与 `career.db` 时间戳均未变化。
