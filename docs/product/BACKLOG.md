# AI Career OS — BACKLOG

**用途：** 收集“有价值但当前不做”的需求。  
**核心规则：** Backlog 不是承诺清单，也不是第二份 PRD。想到新功能先放这里，不直接打断 MVP。

---

## 1. 写法格式

每条需求使用统一格式：

```text
ID:
Title:
Problem:
User Value:
Proposed Solution:
Priority:
Reason Not in MVP:
Dependencies:
Evidence / Source:
Status:
```

### 字段解释

- **ID**：唯一编号，例如 BL-001。
- **Title**：一句话功能名。
- **Problem**：它解决什么真实问题，不要先写技术方案。
- **User Value**：做好后用户获得什么结果。
- **Proposed Solution**：当前想到的方案，可修改。
- **Priority**：P1 / P2 / Icebox。
- **Reason Not in MVP**：为什么现在不做。
- **Dependencies**：依赖什么能力先完成。
- **Evidence / Source**：需求来自用户访谈、自己体验、测试还是面试反馈。
- **Status**：BACKLOG / READY / DOING / DONE / DROPPED。

---

## 2. 当前 Backlog

### BL-001 不推荐岗位解释
**Problem:** 用户可能想知道为什么热门岗位没有被优先推荐。  
**User Value:** 提高岗位推荐的可解释性。  
**Proposed Solution:** 展示“当前不优先推荐”的方向及原因。  
**Priority:** P1  
**Reason Not in MVP:** 不影响从岗位探索进入 Gap 的 Critical Path。  
**Dependencies:** Role Exploration  
**Evidence / Source:** PRD 讨论  
**Status:** BACKLOG

### BL-002 双岗位比较
**Problem:** 用户可能同时纠结两个方向。  
**User Value:** 更容易进行职业取舍。  
**Proposed Solution:** 并排比较薪资、编码强度、Time-to-Ready、Personal Gap、Career Outlook。  
**Priority:** P1  
**Reason Not in MVP:** 需要额外可靠数据源与比较逻辑，三周 MVP 风险较高。  
**Dependencies:** Role Profile / Evidence Layer  
**Status:** BACKLOG

### BL-003 深度 Community Evidence
**Problem:** 社区经验碎片化、观点冲突。  
**User Value:** 理解真实求职体验、共识和争议。  
**Proposed Solution:** 观点聚类、Consensus、Conflict、Credibility。  
**Priority:** P1  
**Reason Not in MVP:** MVP 先用手动 Notes 验证价值。  
**Dependencies:** Evidence Engine  
**Status:** BACKLOG

### BL-004 Accountability Mode
**Problem:** 用户可能只勾选完成，但实际没有掌握。  
**User Value:** 提高执行真实性。  
**Proposed Solution:** 上传成果、AI 验证、小测。  
**Priority:** P1  
**Reason Not in MVP:** 核心闭环可先依赖 Self-check。  
**Dependencies:** Task / Progress  
**Status:** BACKLOG

### BL-005 Career Coach Chat
**Problem:** 用户需要在固定流程之外追问。  
**User Value:** 处理临时卡点。  
**Proposed Solution:** Dashboard 中提供 Ask Career Coach。  
**Priority:** P1  
**Reason Not in MVP:** 防止产品过早退化为 Chatbot。  
**Dependencies:** State / Tools  
**Status:** BACKLOG

### BL-006 自动招聘数据获取
**Problem:** 手动粘贴多个 JD 存在输入摩擦。  
**User Value:** 自动建立更丰富的 Market Evidence。  
**Proposed Solution:** 搜索 / API / 合规的数据接入。  
**Priority:** P2  
**Reason Not in MVP:** 数据稳定性、反爬、合规会分散核心开发。  
**Dependencies:** JD Pipeline  
**Status:** BACKLOG

### BL-007 自动社区内容导入
**Priority:** P2  
**Reason Not in MVP:** 平台接口、登录和合规复杂。  
**Status:** BACKLOG

### BL-008 面试模拟
**Priority:** P2  
**Reason Not in MVP:** 属于独立产品方向，不是 Critical Path。  
**Status:** BACKLOG

### BL-009 简历优化
**Priority:** P2  
**Reason Not in MVP:** 通用 LLM 已较擅长，不是当前差异化。  
**Status:** BACKLOG

### BL-010 历史 Career Plan
**Priority:** P1  
**Reason Not in MVP:** MVP 只维护一个 Active Plan。  
**Status:** BACKLOG

---

## 3. Icebox

这里放“听起来酷，但暂时没有真实需求证据”的想法。

格式：

`ICE-001 | 想法 | 为什么先不做 | 重新评估触发条件`
