# Resume Optimization + Mock Interview retest

日期：2026-09-26

## 已落地

- Resume 页面增加双栏结构：左侧读取绑定 Profile 的原始教育、荣誉/证书、项目/科研、工作、校园经历、技能；右侧展示针对当前 JD 的 AI 改写、短理由、AI 优化方向和逐条接受/编辑/拒绝；同一经历的多条 bullet 使用“同一经历的下一条改写”标识，避免看起来像重复经历。
- 更换或重新绑定简历会清理 selections、resume strategy、target resume、red-team、interview pack 等派生数据，并写入 `optimization_reset_at`。
- 已对当前 Supabase 数据库执行 `alembic upgrade head`，补齐 `013_profile_contacts`，Profile 读取不再因缺失联系方式字段返回 500。
- 新增 `POST /api/v1/job-missions/{mission_id}/resume-optimization/regenerate`，用于对旧岗位显式清理并重新运行 AI 排序。
- 经验排序保留四档决策，后端对明显校园事务/课程做相关性护栏；心理委员等无技术内容会判定 `OMIT`，项目/科研/竞赛保留 `KEEP_AND_HIGHLIGHT`。
- Synthetic project 和 `NEEDS_CONFIRMATION` 要点不再默认进入投递导出；新增 `fact_confirmed` 更新字段，事实确认和接受文案分开。
- Interview provider 收到最新 `CONFIRMED` target resume，并在提示词中优先基于 final resume 提问。
- 面试回答提交保存 API 返回的最新 session，加入 `QUESTION_READY / ANSWERING / SUBMITTING / EVALUATED / NEXT_QUESTION / COMPLETED` 前端阶段和中文失败重试文案；回答框保留输入直到提交成功。
- 黄色事实提示改为正常文档流块级元素，避免覆盖正文。

## 验证

- Web type-check：通过。
- Web tests：165 passed。
- API targeted tests：重绑定清理、显式重新生成、连续 5 轮面试均通过。
- API full suite：569 passed、5 skipped、3 个既有契约失败（claim provider 旧乱码断言、mission provider 旧 schema 断言、target-job fingerprint 旧断言）。
- `git diff --check`：无空白错误。

## 当前真实案例观察

真实 API（隔离 8001 进程）已返回正确的 AI 排序：心理委员 `OMIT`、纪律委员/教学助理 `OMIT`、科研/竞赛项目 `KEEP_AND_HIGHLIGHT`；学生会体育部会按具体描述再判定，当前护栏不再因“协作”模板自动重点展示。浏览器 8000 进程仍需重新载入后才能显示这批结果。当前截图中的重复标题来自一个经历含多个 bullet，下一步应把多个 bullet 合并为一个项目卡后再做人工验收。

## 尚未验证

- 未在本机确认真实 DeepSeek 网络调用；测试使用 provider stub，运行服务的环境变量和进程由现有开发服务器持有。
- 未完成包含真实上传 PDF、最终确认、五轮浏览器交互的完整 UI E2E；后端五轮连续回答已通过。
- 需要重启当前开发服务器后再做一次浏览器截图验收，并检查旧岗位数据是否已经被清理。

## 2026-09-27 follow-up

- 优化页确认后增加“最终简历 / 导出 PDF”收口，保留原始简历左栏和 AI 改写右栏；导出仍使用浏览器打印窗口，文件名沿用姓名-公司-岗位。
- 目标简历确认会自动排除未确认的 synthetic / NEEDS_CONFIRMATION 建议，不再被模型补充项卡死；这些建议继续留在优化页供编辑或事实确认。
- 旧 mission proof 的 resume-suggestions / claim-check 路由统一重定向到 `/missions/{missionId}/interview`，避免旧“严格 JSON / 压力测试”页面混入新链路。
- 策略生成若模型漏填 what_to_highlight / what_to_avoid，会从证据型 fallback 补齐；JD 能力缺口会生成标记为 SYNTHETIC_PROJECT 的具体建议补做项目。
- 自动优化在策略已确认时不再重复 POST confirm-strategy，减少一次慢请求和偶发 409。

验证：旧链接浏览器实测跳转到模拟面试页；Web type-check 通过；Web tests 165 passed；Python compileall 通过；provider targeted tests 8 passed / 1 既有 schema 断言失败；git diff --check 通过。8000 旧进程未能在本次会话内重启，因此最终确认按钮的 live API 成功收口仍需重启服务后复测。
