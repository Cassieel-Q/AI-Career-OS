# AI Career OS — Development Workflow

## 三人工作流

```text
Project Owner → 决策/批准
ChatGPT → Spec / Task / Review
Codex → Implementation / Test / Git
Project Owner → Run / Verify / Explain
ChatGPT → Review / 面试式追问
Next Task
```

## Codex 不得擅自做

- 改产品 Scope
- 引入大型新框架
- 把 Workflow 改成 Multi-Agent
- 新增 Redis / 消息队列 / 微服务
- 改 API Contract
- 暴露 OpenAI Key
- 没有 Spec 就“一次性做完整项目”

## Task 模板

```text
Task ID:
Goal:
Context:
Inputs:
Expected Outputs:
Allowed Files:
Forbidden Changes:
Acceptance Criteria:
Tests:
Git Requirement:
Definition of Done:
```

## TASK-000 目标

- 初始化 Git
- 整理仓库目录
- 初始化 Next.js / FastAPI skeleton
- `.gitignore`
- `.env.example`
- README
- lint / formatter
- test skeleton
- baseline commit
