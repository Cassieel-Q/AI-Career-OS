# AI Career OS · 通宵连续开发最终交付报告

分支：`feature/resumeforge-overnight`（基于 `feature/resumeforge-48h` 的 `d027426`）
基线提交链：`d027426 → bb5b140(M1) → 1c51fbc(M2) → c0d53ca(M3) → 3e4abea(M4) → (M5/M6 待提交)`
未合并 main，未删除任何历史、简历、数据库、附件或环境配置。

---

## 一、功能矩阵

| 里程碑 | 功能 | 状态 | 关键证据 |
|---|---|---|---|
| **M1** | 网页一键采集（任务化） | **DONE_VERIFIED** | 后端 8 用例验收 + 浏览器 E2E 8/8 |
| | 任务状态机 IDLE/RUNNING/COMPLETED/PARTIAL/FAILED/CANCELLED | DONE_VERIFIED | `m1-collect-acceptance.json` |
| | 结果状态 NEW/DUPLICATE/UPDATED/NEEDS_REVIEW/FAILED | DONE_VERIFIED | 同上 |
| | 「抓到 N 条」与「保存 N 条」分开 | DONE_VERIFIED | M6 A6 复验：`fetched` 与 `saved_count` 独立 |
| | 适配器统一契约 + 不谎报来源能力 | DONE_VERIFIED | `ADAPTER_SPECS`，`filter_mode=local` 如实暴露 |
| | 超时/限速/重试/取消 | DONE_VERIFIED | 取消用例真实生效 |
| **M2** | Studio 一键更新 | **DONE_VERIFIED** | 两份简历 × 两个 JD，各 30 步 0 失败 |
| | 板块级差异弹窗（新增/删除/修改/不变） | DONE_VERIFIED | `source-diff` 返回 sections + 人工编辑提示 |
| | 提示人工编辑可能被替换 | DONE_VERIFIED | `manual_edit_count` + 样本 |
| | 修订冲突 428/409 | DONE_VERIFIED | M6 C3/C4 复验 |
| | 换模板不改正文 | DONE_VERIFIED | M6 C6：正文逐条一致 |
| | 重新渲染 Typst / PDF | DONE_VERIFIED | 4 个真实 PDF（88,841 / 89,102 / 77,340 / 77,579 B） |
| | 保留可恢复历史修订 | DONE_VERIFIED | 刷新恢复修订/模板/正文 |
| **M3** | 求职管理补齐 | **DONE_VERIFIED** | 验收 18 步 0 失败 + E2E 14/14 |
| | 打招呼话术（简洁/详细/可编辑/可复制） | DONE_VERIFIED | 确定性模板，不调用模型，不编造，**不自动发送** |
| | 投递版本绑定（回答「当初投的是哪份」） | DONE_VERIFIED | 版本 ID + Studio 修订号 + PDF 快照 |
| | 面试与提醒（应用内） | DONE_VERIFIED | 复用既有库，不建第二套事实来源 |
| | 求职看板 | DONE_VERIFIED | 阶段分列 + 版本使用记录 + 最近面试 + 待办 |
| **M4** | 网申填表兼容性与安全 | **DONE_VERIFIED** | 真实浏览器桥 + 本地表单 11 步 0 失败 |
| | 字段六态 READ/MATCHED/CONFIRMED/FILLED/SKIPPED/FAILED | DONE_VERIFIED | 14 项六态断言 |
| | 先规则匹配、低置信再调模型 | DONE_VERIFIED | 匹配层纯规则，无模型调用 |
| | 安全边界（不填密码/验证码/支付、不自动提交） | DONE_VERIFIED | 填写后截图：敏感项留空、提交按钮未动 |
| | SSRF 防护 | DONE_VERIFIED | 元数据/环回/私网全部 422，逐跳复检 |
| **M5** | Benchmark 数据集与脚本 | **DONE_VERIFIED** | 全量真实跑通 |
| | 30 JD / 10 简历 / 30 配对 / 90 改写 / 15 对抗用例 | DONE_VERIFIED | `validate.py` 通过，类别覆盖 7/7 |
| | A/B baseline（Direct LLM vs AI Career OS） | **PARTIAL** | B 路径 30/30 执行；A 路径 30/30 **NOT_RUN**（未配置模型密钥，如实标注未伪造） |
| | 人工标注规范与模板 | DONE_VERIFIED | `annotations/GUIDELINES.md` + `template.json` |
| | 最终准确率结论 | **BLOCKED_EXTERNAL** | 需人工按规范标注 90 条改写后才能出；机械评分不冒充人工标注 |
| **M6** | 全链路回归 | **DONE_VERIFIED** | A~F 六场景 **40 步 0 失败** |
| | 安全测试（12 类边界） | DONE_VERIFIED | `test_security_boundaries.py` 31 项全绿 |
| | 隔离 production build | DONE_VERIFIED | `BUILD_EXIT=0`（G 盘 EPERM 属环境问题） |

---

## 二、你可以亲自执行的验收步骤

### 0. 启动环境（必须带 `AI_CAREER_DATA_DIR`，否则会回退 `DATABASE_URL` 导致 500）

```powershell
cd G:\myself\ai-career\apps\api
$env:AI_CAREER_DATA_DIR = "$env:LOCALAPPDATA\AICareerOS"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100

cd G:\myself\ai-career\apps\web
npm run dev        # 前端
```

浏览器桥（网申/采集需要，端口 8770）与本地测试表单（8123）：

```powershell
cd G:\myself\ai-career\apps\web
$env:NODE_PATH = "C:\Users\覆水\.workbuddy\binaries\node\workspace\node_modules"
node scripts\browser-bridge.cjs

cd G:\myself\ai-career\docs\evaluation\webform-testpage
python -m http.server 8123 --bind 127.0.0.1
```

### 1. 一键采集（M1）

打开「岗位广场」→ 选来源（Greenhouse 预设如 `anthropic`）→ 填关键词 → 开始采集。
看四个数字：**抓到 / 筛选后 / 新增 / 已存在**。再采一次同一条件，应大量变为「已存在（DUPLICATE）」。

回放验收：`cd apps\api; .venv\Scripts\python scripts\collect_acceptance.py http://127.0.0.1:8100 <profile_id>`

### 2. Studio 一键更新（M2）—— 最值得亲手看的一段

```powershell
cd apps\api; .venv\Scripts\python scripts\studio_update_acceptance.py http://127.0.0.1:8100 ai-pm
cd apps\api; .venv\Scripts\python scripts\studio_update_acceptance.py http://127.0.0.1:8100 data-analyst
```

界面上：出现新版提示 → 点「查看差异」看到**板块级**表格（新增/移除/保留）→
若你手工改过内容会看到黄色警告 → 选「确认更新」→ 修订号 +1 → 导出 PDF。
然后换一个模板，正文应当**一个字都不变**，但需要重新确认才能下载正式 PDF。

### 3. 投递版本绑定（M3）—— 回答「我当初投的是哪份简历」

求职管理页新建投递 → 点「绑定简历版本」→ 显示 `vN · rM`（简历版本 + Studio 修订号）→
点「下载快照」拿到当时投递的 PDF。随后可生成打招呼话术（可编辑、可复制，**不会自动发送**）。

回放验收：`cd apps\api; .venv\Scripts\python scripts\tracker_acceptance.py http://127.0.0.1:8100`

### 4. 网申填表（M4）

打开本地测试表单 `http://127.0.0.1:8123/index.html` → 网申页点「读取表单」→
看每个字段的状态标签（MATCHED / READ / SKIPPED）→ 点「执行填写」。
填写后请重点核对：**密码、验证码、附件为空**，**「同意条款」勾选框没有被代勾**，**提交按钮没被点**。

### 5. 备份与恢复（M6 F 场景，可放心操作）

设置页导出备份 → 恢复。恢复会生成一个**新的独立数据集**，当前数据集**不会被覆盖**，
列表里可以随时切回。损坏的备份会被明确拒绝，不会污染数据。

### 6. 一键回归（全部）

```powershell
cd apps\api; .venv\Scripts\python scripts\e2e_full_chain.py http://127.0.0.1:8100   # A~F 40 步
cd apps\api; .venv\Scripts\python -m pytest tests\test_security_boundaries.py -q    # 安全 31 项
```

---

## 三、测试与证据

### 后端全量 pytest

**887 passed / 7 failed / 5 skipped**（其中本轮新增 31 项安全边界测试全绿）。
7 项失败与基线（`bb5b140`）完全一致：

`test_claim_provider`、`test_gap_analysis`、`test_market_profile`、`test_priorities`、
`test_resume_reliability`、`test_roadmap`、`test_target_jobs`

→ **本轮新增改动引入的失败为 0**。

### 本轮新增测试

| 文件 | 数量 | 覆盖 |
|---|---|---|
| `tests/test_security_boundaries.py` | 31 | SSRF / 桥跨站 / Zip Slip / 解压炸弹 / 备份损坏 / 密钥排除 / 未确认不生效 / 数据集隔离 |
| `tests/test_application_binding.py`（M3） | 8 | 版本绑定 / 话术不编造 / 看板聚合 |
| `tests/test_webform_safety.py`（M4） | 23 | 六态 / 勾选不代劳 / 验证码误判 |
| `tests/test_resume_studio_reimport.py`（M2） | 4 | 板块差异回归 |

### 关键证据文件

- `docs/evaluation/overnight-sprint/m6-full-chain.json`（A~F 40 步逐步明细）
- `docs/evaluation/overnight-sprint/m1-collect-acceptance.json`、`m2-studio-acceptance-{ai-pm,data-analyst}.json`
- `docs/evaluation/overnight-sprint/m3-tracker-acceptance.json`、`m4-webform-acceptance.json`
- `docs/evaluation/overnight-benchmark-report.md` + `evals/overnight-v1/results/{run,score}-20261016T192635Z.json`
- 截图：`docs/screenshots/overnight-m1|m2|m3|m4/`
- 真实 PDF：`m2-studio-{ai-pm,data-analyst}[-tpl].pdf`、`m3-delivery-snapshot.pdf`

---

## 四、本轮修掉的真实缺陷（不是文档修饰）

1. **备份恢复 Zip Slip 路径穿越**：`attachments/../../evil.txt` 会写到数据集目录之外。已加白名单校验 + `is_relative_to` 二次兜底。
2. **备份恢复无解压体积上限**（解压炸弹）：新增单成员 256 MiB / 整包 1 GiB 限制。
3. **M2 板块差异恒为 0**：`_section_breakdown` 把 section 传给期望 document 的函数。
4. **M2 零接受要点也能确认出空简历**：`confirm_target_resume` 增加防呆 409。
5. **M4 确认类勾选被代劳**：checkbox 曾被误标「姓名」并**自动勾选同意条款**——matching + fill 双保险。
6. **M4 `ref_code` 被误判验证码**：收紧规则。
7. **M1 采集统计恒 0**：`recompute_result_totals` 顺序错误。
8. **M1 RemoteOK 随机串导致每次误判 UPDATED**：`stable_text()` 去随机 token。
9. **评测脚本三处方法学缺陷**（会得出假结论，详见 progress.md M5 节）。
10. **测试污染真实数据集**：已修复并加 autouse 隔离，环境已恢复。

---

## 五、明早需要你参与的事项

1. **补 A/B baseline 的模型密钥**（唯一被外部阻塞的验收项）
   设置 `BASELINE_DIRECT_LLM_BASE_URL` / `_API_KEY` / `_MODEL` 后重跑
   `evals\overnight-v1\scripts\run.py`，即可拿到 Direct LLM 对照组。
   在补齐之前，报告里该项一律是 `NOT_RUN`，我没有伪造任何对比数字。

2. **人工标注 90 条改写案例**（决定 M5 能否出最终准确率）
   规范见 `evals/overnight-v1/annotations/GUIDELINES.md`，模板 `template.json`。
   机械评分只能证明「没有编造数字、没有空改写、对抗用例全部安全」，
   **四分类准确率必须靠人工标注**，我不会用模型自评或单测通过率冒充。

3. **确认真实第三方网申页面的兼容性**
   M4 只在本地构造的测试表单上验证（真实第三方站点需要你登录态，
   且按安全边界不做绕过登录/验证码的事）。可挑 1~2 个你正在投的站点实测。

4. **决定是否合并到 main**
   我未自动合并。建议先验一遍「第二节」的演示步骤，尤其是 Studio 差异弹窗与投递快照下载。

5. **清理测试残留（可选）**
   `%LOCALAPPDATA%\AICareerOS\quarantine\` 下是本轮测试产生的临时数据集副本，
   确认无用后可自行删除；当前 active 数据集仍是 `ds2610162021590a18`，未受影响。

---

## 六、仍需说明的限制（没有做，也不打算假装做了）

- 中文招聘平台（BOSS / 实习僧 / 拉勾 / 智联）无合规公开接口，不做绕过；
  合规入口是粘贴 JD / 上传文件 / 浏览器桥读取当前可见页面。
- 没有任何来源支持服务端城市/实习/发布时间过滤，**全部为采集后本地过滤**，界面如实显示 `filter_mode=local`。
- 系统**不做自动投递**、不自动提交网申表单、不填写密码/验证码/支付信息、不读 Cookie。
- 提醒**仅在应用内展示**，不会发送系统推送。
- 改写结果的四分类最终质量依赖人工标注；模型输出本身有随机性。
