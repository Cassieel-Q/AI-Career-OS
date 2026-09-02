# 当前阶段交付物说明 — Product Definition Gate

## 当前阶段名称

**Product Definition / PRD Freeze**

完成这个 Gate 后，才进入 Technical Specification。

---

## 当前必须交付的 5 份文档

### 1. `PRD_v1.0_FROZEN.md`
回答：
- 产品解决谁的问题？
- 核心用户结果是什么？
- P0 做什么？
- 明确不做什么？
- 做到什么算完成？

**写作要求：**
- 以决策和规则为主，不写宣传文案；
- 每个需求尽量可测试；
- 避免“智能地、友好地、准确地”等不可验收词；
- Scope Freeze 后，除正式变更外不要直接修改。

### 2. `BACKLOG.md`
回答：
- 有哪些好想法暂时不做？
- 为什么不做？
- 什么时候重新考虑？

**写作要求：**
先写 Problem，再写 Solution。  
不要只写“加一个面试 Agent”，而要写“用户在进入面试阶段后缺少针对个人 Gap 的练习反馈”。

### 3. `DECISIONS.md`
回答：
- 为什么我们这样设计？
- 当时有哪些替代方案？
- 牺牲了什么？

**写作要求：**
一个 Decision 只记录一个关键取舍；重点写 Why 和 Trade-off。

### 4. `PRODUCT_GLOSSARY.md`
回答：
- 项目术语是什么意思？
- 在 Career OS 里具体指什么？

**写作要求：**
必须用本项目例子解释，不复制百科定义。

### 5. `CHANGELOG.md`
回答：
- 冻结后的正式变化是什么？
- 为什么改？
- 谁批准？

初始模板：

```markdown
# CHANGELOG

## v1.0 — 2026-09-02
- Frozen MVP with 14 P0 capabilities.

## Unreleased
- None.
```

---

## 当前不需要交付

以下文档属于下一阶段，不要提前写到失控：

- `TECH_SPEC.md`
- `ARCHITECTURE.md`
- `DATA_MODEL.md`
- `API_SPEC.md`
- `EVAL_SPEC.md`
- `TASKS/`
- 代码

这些会在 PRD v1.0 Review 通过后开始。

---

## 文档统一格式规则

### 文件名
使用大写类型 + 明确版本，例如：

`PRD_v1.0_FROZEN.md`

### 标题层级

```markdown
# 文档名
## 一级模块
### 子模块
```

不要超过 3～4 层。

### 需求写法
优先写：

```text
用户是谁
→ 在什么场景
→ 遇到什么问题
→ 系统做什么
→ 输出什么
→ 什么算完成
```

### Acceptance Criteria 推荐格式

```text
Given ...
When ...
Then ...
```

例：

```text
Given 用户上传有效 PDF 简历
When Resume Parser 成功运行
Then 系统生成 Draft Profile，至少包含教育、技能、经历
```

### 不要写的模糊需求

差：
> 系统应该智能分析用户简历。

好：
> 系统解析 PDF 简历，并输出 education、skills、experience 三类结构化字段；解析结果必须经用户确认后才能进入岗位推荐。

---

## Product Gate 完成标准

当以下条件全部满足时，可以进入 Tech Spec：

- [x] Target User 明确
- [x] Primary Outcome 明确
- [x] 14 个 P0 Capability 冻结
- [x] Out of Scope 明确
- [x] 核心 Acceptance Criteria 已有
- [x] Backlog 已建立
- [x] 关键 Product Decisions 已记录
- [ ] 最后一次 PRD v1.0 Review
- [ ] Project Owner 签字 / 明确批准进入 Technical Spec

---

## 三人分工（当前阶段）

### 你 — Project Owner
负责：
- 审批 PRD；
- 判断需求是否进入 P0；
- 解释每个重要产品决策；
- 对 Scope Freeze 负责。

### ChatGPT — Product Mentor / Tech Lead
负责：
- PRD Review；
- 找矛盾、过度设计、不可验收需求；
- 教你术语和决策方法；
- 下一阶段组织 Technical Spec。

### Codex — Engineer
**当前：待命。**

只有 Tech Spec 最小版本完成后，Codex 才开始写代码。

---

## 下一步

当前只剩一个动作：

> **PRD v1.0 Final Review**

Review 重点：
1. 14 个 P0 是否存在互相矛盾；
2. AC 是否都能验证；
3. 是否有 P0 实际属于 P1；
4. Critical Path 能否完整走通；
5. 是否存在第一版无法获得的数据。

通过后进入：

`TECH_SPEC_v0.1`
