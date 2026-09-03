# AI Career OS — DECISIONS v1.1

## DEC-011 — Role Exploration 使用内置 Role Profile
**Status:** ACCEPTED  
**Decision:** 首次探索使用 6 类内置粗粒度岗位画像；真实 JD 导入后，以用户 JD 样本形成的 Market Profile 为主。  
**Why:** 既保持首次体验低摩擦，又避免完全依赖 LLM 常识拍脑袋。  
**Trade-off:** 内置画像不是实时市场事实。  
**Revisit When:** 自动市场数据能力上线。

## DEC-012 — Resume Parser 不判断技能熟练度
**Status:** ACCEPTED  
**Decision:** Parser 只抽取显式事实；技能水平由用户轻量确认。  
**Why:** 防止 Error Propagation。  
**Trade-off:** Onboarding 增加一步。

## DEC-013 — Gap Cost 只用 LOW / MEDIUM / HIGH
**Status:** ACCEPTED  
**Decision:** MVP 不输出精确补齐小时数。  
**Why:** No Fake Precision。  
**Revisit When:** 有足够真实学习时长数据。

## DEC-014 — MVP 不做完整学习资源推荐
**Status:** ACCEPTED  
**Decision:** Roadmap 定义“学什么、做什么、做到什么程度”，不负责全网找课程。  
**Why:** 防止 Scope 膨胀成课程平台。

## DEC-015 — Task Completion 不等于 Skill Mastery
**Status:** ACCEPTED  
**Decision:** Self-check 只更新任务进度，不自动提升技能熟练度。  
**Why:** 没有成果验证就不能宣称用户已掌握。  
**Revisit When:** Accountability / Skill Verification 上线。

## DEC-016 — LLM Intelligence Boundary
**Status:** ACCEPTED  
**Decision:** LLM 用于语言理解、结构化抽取、有证据推理和规划；确定性业务规则优先用代码。  
**Why:** 提高可测试性、稳定性和可解释性。
