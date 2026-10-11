# 功能布局大洗牌：仿 ResumeForge 多模块工作台

> 2026-10-11 · 分支 `feature/workbuddy-ui-func-opt`

## 一、布局大洗牌（已完成）

参照 ResumeForge「侧栏导航 + 多模块工作台」的结构，把项目从「单岗位 Mission 向导」升级为两层结构：

- **顶层模块页**（带全局侧栏）：首页 / 岗位广场 / 简历中心 / 求职进度 / 事实台账 / 面试记录
- **Mission 详情**（保留向导式专注外壳）：岗位理解 → 简历优化 → 模拟面试 → 结果

侧栏含「我的空间」分组（上传简历 / 证据 OS）。实现：`app-shell.tsx`（导航组件）+ `shell-controller.tsx`（按路由决定是否套壳）+ `globals.css` 的 `app-*` 样式段（复用单色系 token）。

## 二、与 ResumeForge 的功能对照

| ResumeForge 模块 | 本项目对应 | 状态 |
| --- | --- | --- |
| 首页（快捷入口+概览） | `/` 首页仪表盘 | ✅ 本次新增 |
| 岗位广场 | `/missions` 岗位广场（原岗位档案升级） | ✅ 已接入侧栏 |
| 简历中心 | `/resumes` 简历中心（跨岗位简历版本聚合） | ✅ 本次新增 |
| 求职进度 | `/tracker` 求职进度（阶段状态机 + 筛选） | ✅ 本次新增 |
| 事实台账 | `/claims` 事实台账（主张/证据/风险/确认态） | ✅ 本次新增 |
| 模拟面试 | Mission 内模拟面试 + `/interview-records` | ✅ 已有 |
| 我的资料 | 简历档案（profile）体系 | ✅ 已有（实现方式不同） |
| 路线图/差距分析 | MarketProfile→GapAnalysis→Roadmap | ✅ 已有且更强 |
| 网申填表 / 自动投递台 / 求职助手 / 回收站 / 全局搜索 | — | 🗺 路线图（见下） |

## 三、新增后端接口（复用现有表，无迁移）

`apps/api/app/career_hub.py`：

- `GET /api/v1/profiles/{id}/tracker` — 聚合 JobMission + InterviewOutcome → 求职阶段状态机
- `GET /api/v1/profiles/{id}/claims` — 聚合 ResumeClaim → 事实台账
- `GET /api/v1/profiles/{id}/resumes` — 聚合 TargetResume + Studio 文档 → 简历中心

## 四、路线图（ResumeForge 有、本版未建的大系统）

按建议优先级：

1. **求职助手**（能查库的对话式 AI，引用台账/面经回答）
2. **投递台**（采集 → 确认 → 投递队列；需浏览器桥接，建议后置）
3. **全局搜索**（一个框搜岗位/简历/台账/面试记录）
4. **回收站 + 收藏夹**（软删 + 恢复）
5. **匹配度五类结论**（把现有 gap 分析改成「已匹配/表达缺口/证据不足/真实缺口/待确认」的呈现）
6. **提醒/日历**（面试与投递日程）
