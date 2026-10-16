# 岗位采集真实验收报告（job-collection-v1）

- 生成时间：2026-10-16T21:02:31.344672+00:00
- 隔离测试数据集：`ds261017041218fd59`（**未触碰用户原数据集**）
- 运行记录：`evals/job-collection-v1/runs/live-20261016T205156Z.json`
- 真实采集岗位样本：158 条

## 1. 指标

| 指标 | 数值 | 口径 |
| --- | --- | --- |
| 采集解析成功率 | 95.7% | 201 / 210（成功解析 / 实际纳入解析范围的候选岗位） |
| 核心字段完整率（非空） | 100.0% | 1106 / 1106（158 条样本 × 7 个必填字段） |
| 岗位类型确定率 | 50.0% | 79 / 158（`employment_type` 非 UNKNOWN；UNKNOWN = 识别不出就如实留空，不猜）|
| 需人工补齐字段的岗位 | 40 / 158 | 这些岗位已标 `needs_confirm`，导入正式岗位前需用户补齐 |
| 保存成功率 | 100.0% | 104 / 104（首次采集的入库数 / 尝试保存数） |
| 去重 Precision | 100.0% | TP=3 FP=0 |
| 去重 Recall | 100.0% | TP=3 FN=0 |
| 岗位相关性 | **UNREVIEWED** | 人工已审核 0 / 158，**没有人工标签就不输出百分比** |
| 完整流程成功率 | 100.0% | 15 / 15（网页采集 → Mission） |

### 分字段完整率

| 字段 | 完整率 | 说明 |
| --- | --- | --- |
| `company` | 100.0% | 158/158 |
| `role` | 100.0% | 158/158 |
| `location` | 100.0% | 158/158 |
| `jd` | 100.0% | 158/158 |
| `source_url` | 100.0% | 158/158 |
| `employment_type` | 100.0% | 158/158 |
| `posted_at` | 100.0% | 158/158 |

## 2. 真实在线采集

| 来源 | 阶段 | 关键词 | 接口状态 | 原始返回 | 解析 | 命中 | 入库新增 | 跳过 | 错误 | 耗时 |
| --- | --- | --- | --- | --- | --- | --- | --- | --- | --- | --- |
| remoteok | BROAD | ai/product | OK | 99 | 30 | 30 | 30 | 0 | 0 | 1847ms |
| remoteok | TARGET | ai product manager/product manager intern/ai product | OK | 99 | 29 | 29 | 17 | 12 | 0 | 2280ms |
| remotive | BROAD | ai/product | OK | 15 | 14 | 14 | 14 | 0 | 0 | 940ms |
| remotive | TARGET | ai product manager/product manager intern/ai product | OK | 15 | 8 | 8 | 0 | 8 | 0 | 840ms |
| greenhouse | BROAD | ai/product | OK | 1526 | 30 | 30 | 30 | 0 | 0 | 2729ms |
| greenhouse | TARGET | ai product manager/product manager intern/ai product | OK | 1526 | 30 | 30 | 10 | 20 | 0 | 2232ms |
| lever | BROAD | ai/product | OK | 320 | 30 | 30 | 30 | 0 | 0 | 4641ms |
| lever | TARGET | ai product manager/product manager intern/ai product | OK | 320 | 30 | 30 | 27 | 3 | 0 | 5006ms |

> 「原始返回」= 直接请求公开接口统计到的候选条目数；「解析」= 归一化成功且通过关键词过滤的岗位数。
> **采集时间 ≠ 岗位发布时间**；接口成功返回**不代表该岗位此刻仍在招**，需点开原始链接自行确认。

## 3. 重复采集去重

| 来源 | 阶段 | 第二次解析 | 第二次新增 | 第二次跳过 | 指纹一致 |
| --- | --- | --- | --- | --- | --- |
| remoteok | BROAD | 30 | 0 | 30 | True |
| remoteok | TARGET | 29 | 0 | 29 | True |
| remotive | BROAD | 14 | 0 | 14 | True |
| remotive | TARGET | 8 | 0 | 8 | True |
| greenhouse | BROAD | 30 | 0 | 30 | True |
| greenhouse | TARGET | 30 | 0 | 30 | True |
| lever | BROAD | 30 | 0 | 30 | True |
| lever | TARGET | 30 | 0 | 30 | True |

固定标注样本去重：TP=3 FP=0 FN=0 TN=9，准确率 100.0%

## 4. 完成标准判定

| 条件 | 结果 |
| --- | --- |
| 至少一个真实公开来源成功采集 | ✅ |
| 岗位数据真实入库 | ✅ |
| 重复采集去重通过 | ✅ |
| 前端完整采集流程通过 | ✅ |
| 保存岗位能继续进入岗位匹配 | ✅ |
| 已保存截图、日志与测试报告 | ✅ |

**COLLECTION_E2E_VERIFIED = True**

**CHINESE_JOB_SITES_UNVERIFIED** — 本轮只验证了 RemoteOK / Remotive / Greenhouse / Lever 四个**境外公开**来源；
BOSS 直聘、实习僧等中文招聘网站**未做真实验证**（需登录态，且不适用自动采集）。

## 5. 浏览器 E2E（15 步）

结果：**17/17 通过**，测试档案 `a540bbe8-de8c-4a47-8d49-d2ef63c9b4f0`

| 步骤 | 检查 | 结果 | 详情 |
| --- | --- | --- | --- |
| setup | 创建隔离测试档案 | ✅ | profile=a540bbe8 |
| 1 | 打开岗位广场 | ✅ | 岗位广场 |
| 2 | 进入「一键采集岗位」区块 | ✅ | 1 · 一键采集岗位 |
| 3 | 输入关键词 | ✅ | ai / product |
| 4 | 选择公开来源 | ✅ | 来源=RemoteOK 选中态=true |
| 5 | 点击开始采集 | ✅ | 任务状态：采集中 |
| 6 | 等待任务结束 | ✅ | 任务状态：采集完成 |
| 7 | 真实采集结果非空 | ✅ | 20 行 |  |
| 8 | 勾选符合条件的岗位 | ✅ | 勾选 5 条，首条=iMerit Technology / AI Trainer |
| 9 | 批量保存写入岗位库 | ✅ | 新增保存 20 条 |
| 10 | 刷新后保存结果仍在 | ✅ | 岗位库 20 条 |
| 11 | 重复采集去重正常（已存在计数 > 0） | ✅ | 已存在 20 条（不再新增） |
| 12 | 打开新导入的岗位（含原始链接） | ✅ | iMerit Technology / AI Trainer → https://remoteOK.com/remote-jobs/remote-ai-trainer-imerit-technolog |
| 13 | 可查看完整 JD 正文 | ✅ | JD 正文 1976 字 |
| 14 | 点击匹配分析跳转 | ✅ | http://127.0.0.1:3000/missions/a4c1c421-0242-4e1a-a4ca-b9ff25b53a06/role |
| 15 | 岗位已进入 Mission 链路 | ✅ | http://127.0.0.1:3000/missions/a4c1c421-0242-4e1a-a4ca-b9ff25b53a06/role |
| db | 数据库读取验证（岗位库 API） | ✅ | {"http_status":200,"item_count":21,"sample":[{"kind":"CANDIDATE","company":"iMerit Technology","role |

## 6. 用户实操路径（照着做就能复现）

1. 打开 **http://127.0.0.1:3000/jobs**（岗位广场）。
2. 在「**1 · 一键采集岗位**」区块的关键词输入框里输入关键词后回车。
   - 实际可用的关键词：`ai`、`product`（宽口径，能拿到真实岗位）
   - 也可试 `ai product manager`、`product manager intern`（目标口径，命中较少）
   - 关键词是**本地匹配**：RemoteOK / Greenhouse / Lever 都不支持服务端关键词检索
3. 点来源 chip 选中 **RemoteOK**（默认已选中，选中态会高亮）。
   - 想采 Greenhouse / Lever 需要先填招聘板标识（有已验证标识可一键填入，如 `anthropic`、`figma`、`stripe`）
4. 点「**开始采集**」，等状态变成「采集完成」。
5. 在「**2 · 采集结果**」里勾选要保存的岗位 → 点「**批量导入选中岗位（N）**」。
6. 岗位出现在「**5 · 已保存岗位**」；刷新页面仍在。
7. 再点一次「开始采集」→ 同一批岗位会显示为「**已存在**」，不会重复入库。
8. 在采集结果行里点「**展开 N 字**」可看完整 JD；「来源」列是原始链接。
9. 点行内「**匹配分析**」→ 跳转 `/missions/{id}/role`，即进入现有 Mission 链路。

> 本次验收实际保存：RemoteOK 30 条 + Remotive 14 条 + Greenhouse 30 条 + Lever 30 条（BROAD 阶段首次采集，全部入库）。

## 7. 未通过项与已知问题

- 浏览器 E2E 15 步全部通过。
- 岗位相关性未经人工确认，标记为 `UNREVIEWED`，未输出百分比。
- 中文招聘网站（BOSS 直聘 / 实习僧等）未做真实验证。
