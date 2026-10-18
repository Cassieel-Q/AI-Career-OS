# 可信求职闭环 v1.2｜实现摘要与差异表

分支 `feature/trusted-workflow-v12`，HEAD `1ea1c65`。**未合并 main**，main 未被改动。

## 一、本轮目标（一句话）

> 让用户针对一个真实岗位，获得一份**事实可核对、版本可辨认**的投递简历，并使用**真正投递出去的那一版**简历准备面试。

## 二、Sprint 交付状态

| Sprint | 主题 | 状态 | 关键交付 |
|---|---|---|---|
| A | 事实可信 | ✅ 完成 | 事实来源 / 用户核对 / 文案采纳三维拆分；确定性闸门；结构化参考答案；≥25 对抗用例（`test_fact_trust.py` 25 + `test_fact_safety_reference_answer.py` 27） |
| B | 匹配与版本一致 | ✅ 完成 | `score → grade → recommendation` 单一来源；输入指纹判过期；过期只提示、不替换（`test_match_contract.py` 21） |
| C | 首用三动作 | ✅ 完成 | 首页单一主线；无模型建档（`resumes/local`）；解析失败降级出口；**服务端档案恢复（本轮补接到首页）** |
| D | 草稿 / 正式投递版分离 | ✅ 完成 | `export_checks(final=)` 三级门禁；草稿 PDF 带 DRAFT 水印与 `_DRAFT` 文件名；正式版绑定公司/岗位/Studio 修订并落不可变快照（`test_export_gate.py` 15） |
| E | 多岗位与面试版本一致性 | ✅ 完成 | 共享事实 + 逐岗位版本；`impact` / `sync` 选择性更新；面试默认读**实际投递**的那一版（`test_multi_job_version_consistency.py` 13） |
| F | 专项测试与完整回归 | ✅ 完成 | 全量回归 + 4 组专项 + **6 条真实浏览器主流程（35/35）** + 隐私边界 |
| P3 | 目标用户研究 | ⚠️ 仅准备 | 只产出招募/任务/观察模板，**没有真实用户，不声称已完成** |

## 三、差异表（改了什么、为什么）

| # | 现状问题 | 本轮做法 | 落点 |
|---|---|---|---|
| 1 | 「提取到 / 采纳改写 / 核实事实」被混为一谈，自动确认即视为已核实 | 拆成 `FactSource` × `VerificationStatus` × 文案采纳；旧状态一律降级为 `UNREVIEWED`，绝不批量升级 | `app/fact_trust.py`、`fact_trust_service.py` |
| 2 | 参考回答会编造候选人第一人称经历与数字 | 结构化契约（已知事实 / 待补 / 回答方法 / 示范表达）+ 三重闸门；不确定一律降级，不给成稿 | `interview_provider._gate_reference_answer` |
| 3 | 匹配分数、等级、建议三处各算各的，互相打架 | 单一契约推导；与分数矛盾的模型建议直接丢弃；输入指纹变了只标 `stale`，不静默替换 | `match_contract.py`（见 `test_match_contract.py`） |
| 4 | 草稿和正式投递版是同一份文件，发出去才发现缺姓名/未核对事实 | `block/warn/info` 三级门禁；草稿始终可导（带 DRAFT），正式版必须过门禁并绑定修订、落快照 | `resume_studio_service.export_checks(final=)` |
| 5 | 改一处事实，其它岗位简历被一起改掉 | `GET /facts/{kind}/{id}/impact` 只报告；`POST .../sync` 一次只改用户选中的那一份；AI 改写要点不自动改写 | `fact_impact_service.py` |
| 6 | 面试准备用的是最新 Master / Studio，不是真正投出去的那版 | 解析顺序：投递快照 → 投递记录绑定修订 → 已确认 Studio（标注未投递）；未投递时明说 | `delivery_version_service.resolve_interview_resume` |
| 7 | 清了浏览器存储就成了新用户，档案找不回来 | 首页接上服务端档案列表（此前 `readLocalProfiles` 定义了但没人用），挑一份继续，不需要 UUID | `apps/web/app/page.tsx` |
| 8 | 事实改了，旧签名还在给新文本背书 | `invalidate_changed_attestations`：文本一变就把 `USER_ATTESTED` 退回 `UNREVIEWED` | `fact_trust_service.py` |
| 9 | 文件名会带出手机号 / 邮箱 / `sk-` 形状的密钥 | 按形状清洗：7 位以上连续数字、带密钥前缀的串、32 位以上随机串、邮箱整体 | `build_resume_filename` |

## 四、明确没做的事（避免被当成已完成）

- **没有**重做 Agent 架构、没有重写 Resume Studio、没有新的桌面框架、没有新的采集平台、没有新增 Agent 工具。
- **没有**动 18 套模板、Studio 历史、已交付 PDF 快照、面试记录、API Key、本地备份。
- **没有**合并 main，也没有在 main 上开发。
- **没有**真实模型调用（本轮未授权付费调用）。浏览器 E2E 用本地桩模型服务替代，验证的是**产品流程与前端行为**，不是模型输出质量。
- **没有**真实目标用户（P3 只出模板）。

## 五、新增 / 修改的数据库迁移

| 迁移 | 表 | 用途 | down_revision |
|---|---|---|---|
| `028_trusted_facts` | `fact_attestations` | 只记录用户**明确核对**的行为；`fact_key` 稳定键，`fact_text` 用于事实变更后重新判定 | `027_application_binding` |
| `029_delivery_snapshots` | `delivery_snapshots` | 正式投递版不可变快照：`document_json` + `content_hash` + `pdf_path` + `studio_revision` | `028_trusted_facts` |

两个迁移都写成幂等（`CREATE TABLE IF NOT EXISTS` 风格 + 索引判存在），重复执行不会炸。`tests/test_alembic_revisions.py` 的链定义与 head 断言已同步更新。

迁移链：`… → 027_application_binding → 028_trusted_facts → 029_delivery_snapshots（当前 head）`。
