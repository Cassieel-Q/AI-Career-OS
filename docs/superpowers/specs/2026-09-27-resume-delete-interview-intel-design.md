# 简历删除与真实面经统一接入设计

**日期：** 2026-09-27  
**状态：** 已获用户确认，进入实现

## 目标

1. 允许用户从简历档案列表彻底删除一份简历及其关联岗位、目标简历、面试会话、复盘与证明数据。
2. 将 `G:\myself\aicareeri-interview` 中整理的真实牛客面经导入 SoT 的 `knowledge/interview_skills/`，并让简历优化、面试题、面试复盘和补强建议共享同一套检索结果。
3. 保持现有数据库模型和产品概念，不新增软删除体系或新的用户流程。

## 已确认的用户决策

- 删除范围：彻底删除服务器档案及其关联数据；删除后不可通过档案 ID 恢复。
- 面经来源：真实牛客面经卡片与 `interview skills`，优先同公司、其次同岗位族、最后通用内容。
- 用户界面只显示简短来源提示；`skill_id`、`source_refs` 等内部字段留在后端。

## 设计

### 1. 简历删除

- 后端新增 `DELETE /api/v1/profiles/{profile_id}`。
- 服务层在事务中锁定 `UserProfile`，删除依赖档案的关联数据；数据库级联负责 profile、target job、claim、mission、target resume、interview session/turn、proof action/artifact、roadmap 等关系，服务层显式清理 `SET NULL` 关系，避免任务或会话孤儿记录。
- 不存在的档案返回 404；成功返回 204。
- Web 在 `/missions` 和上传页的本机档案列表提供删除按钮。确认提示明确列出会删除原始简历、岗位准备、优化简历和面试记录。
- 删除成功后从 `profile-label` localStorage 注册表移除档案，并清理当前档案选择；当前档案被删时返回 `/missions`。

### 2. SoT 面经同步

- 复用 `apps/api/app/interview_skill_importer.py`，从外部仓库 `_raw/curated_cards.json` 读取 `kind=real` 卡片。
- 生成 `knowledge/interview_skills/curated/curated_<company>_<family>.md`，保留 `provenance: CURATED`、公司/岗位族、来源 URL、卡片数量、面试关注点和真实问题模式。
- 合成 demo 包继续存在但默认不参与真实公司检索。
- 同步产物纳入版本库；同步命令和数量写入测试/文档，便于后续更新。

### 3. 统一检索上下文

- `InterviewIntelRetriever` 继续负责同公司 > 同岗位族 > 通用排序和数量上限。
- Mission 的简历选择、策略、目标简历和 interview pack prompt 都接收精简后的 `interview_intel`；简历重写利用面经高频追问来强化可被追问的事实、边界和量化验证，不能新增未确认事实。
- Mock interview 读取最终确认版简历、JD、相关 curated skill pack、interview pack 主题和问题模式，优先生成真实面经中出现的同主题问法。
- 复盘/补强生成沿用当前会话检索结果：事实追问是 3–5 个针对性问题；项目补齐是基于面经关注点给出的具体学习、实践和交付建议。
- 对用户显示 `参考百度相关牛客面经 N 篇` 之类的来源说明，内部引用仍写入 `skill_id/source_refs`。
- 不将完整面经库发送给 LLM；每次只发送排名靠前、与 JD/主题相关的有限条目。

## 验收标准

### 删除

- 删除一个有岗位、目标简历、面试和证明数据的档案后，档案 GET 返回 404。
- 该档案的岗位、面试会话、复盘和证明接口均不可再读取。
- 删除其他档案不会改变当前档案或其他岗位列表。
- 前端删除成功后列表、localStorage 和当前路由同步更新。

### 面经

- 导入产物至少包含真实 Baidu/ByteDance/Xiaohongshu 等公司包，并带 `CURATED` provenance 与来源引用。
- 百度 AI 产品经理检索优先命中百度 curated 包，返回真实问题模式；合成 demo 不进入默认结果。
- 简历优化、面试题、复盘请求的 provider payload 均带有限的 curated 面经上下文。
- 简历和面试 UI 不显示内部标签、UUID 或原始导入元数据。

### 回归

- API 删除服务与路由单测。
- 面经导入、检索、prompt 上下文单测。
- Web profile label 删除与列表交互单测。
- 运行相关 API/Web 测试、类型检查、编译检查和 `git diff --check`。

## 不在本次范围

- 不增加 `deleted_at` 软删除字段。
- 不重做现有简历优化、面试或数据库 schema。
- 不把建议补做的 portfolio 项目写成已完成经历。
- 不把全部面经正文直接展示给用户或一次性发送给模型。
