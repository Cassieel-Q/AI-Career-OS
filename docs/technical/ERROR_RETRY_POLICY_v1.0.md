# AI Career OS — ERROR_RETRY_POLICY v1.0

**Status:** FROZEN

## Error layers

### 1. User/Input Error
例如：
- 空 JD
- 少于 3 个 JD
- 无文本 PDF

处理：
- 直接返回可理解的 4xx 错误
- 不调用 LLM

### 2. LLM Schema Error
Structured Output 未通过 Pydantic Validation。

处理：
1. 自动重试 1 次
2. 第二次失败则返回明确错误
3. 不写入正式数据库状态

### 3. External Provider Error
OpenAI 超时、限流、暂时不可用。

处理：
- 对可重试错误做指数退避重试，最多 2 次
- 仍失败则返回 502/503
- 不偷偷切换到不可控结果

### 4. Business State Error
例如 Profile 未 confirmed 就调用 Role Exploration。

处理：
- 返回 409 Conflict
- 前端提示用户先完成前置步骤

## Key rule

> Retry 解决“暂时失败”，不能用来掩盖错误输入或错误业务状态。
