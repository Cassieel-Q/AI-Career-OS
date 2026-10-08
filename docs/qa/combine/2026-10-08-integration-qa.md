# AI Career OS 三线集成 QA

日期：2026-10-08。分支：`feat/aioscareer-combine`。工作树：`G:\myself\ai-career\.worktrees\aioscareer-combine`。

## 证据

| 门槛 | 当前结果 |
|---|---|
| Git 双亲合并 | `8950d5b`，父分支为 Resume Studio 与 Pixel UI；唯一冲突在最终简历 PDF 入口，保留 Studio 入口 |
| Alembic | 013 → 014_resume_studio → 015_interview_records；隔离 SQLite 升级、降级、再升级测试通过 |
| API 完整回归 | `607 passed, 3 failed, 5 skipped, 6 warnings`；三项失败与源分支既有基线同名，详见下文 |
| 针对性 API | 面试记录、档案删除、岗位删除、迁移、Studio 面试桥接 30 passed；新增 PATCH 回归 3 passed |
| Web 测试 | 192 passed、0 failed |
| Web 类型检查 | 通过；依赖目录补齐后重跑 |
| Web 生产构建 | `npm run build` 通过；既有字体及 hooks 提示仍在 |
| 浏览器与 PDF | 桌面全流程、手机 390 px、真实模型三题、固定题目五题、真实面试记录均已验证；见下文截图 |

既有失败：`test_claim_provider_normalizes_partial_claim_schema`、`test_mission_provider_classifies_structured_output_failures`、`test_claim_analysis_fingerprint_requires_regeneration_after_profile_change`。这些失败在两源分支 QA 中已有记录，本次不得写作完整 API 通过。

迁移回归最初用带 `alembic.ini` 的 `Config`，在 pytest 进程内重置日志处理器，导致后续日志断言额外失败；已改为不加载 ini 的独立 `Config()`。“迁移测试 + 后续日志断言”连续运行通过。独立代码审查又发现面试记录 PATCH 可关联别人的岗位、接受无效必填值，以及替换同序号问答时唯一键冲突；已用先失败后通过的路由回归测试修复。真实模型密钥、DeepSeek URL、Typst 路径均在本机环境中；测试命令使用测试密钥、清空 `OPENAI_BASE_URL` 并显式指定 Typst，避免让单测意外走在线接口。

## 浏览器验收

入口为 `http://localhost:3001`，API 为 `http://127.0.0.1:8000`；测试数据只在本分支 `.runtime/combine-e2e.db`，人物和公司均为虚构。浏览器走了上传 PDF A → 建档 → 新建 Acme Labs 岗位并真实分析 JD → 为该岗位上传不同 PDF B → 生成七条定向改写 → 逐条确认/拒绝 → 最终简历 → Studio 模板、联系方式、事实核对、顺序编辑、刷新恢复与确认。上传解析、JD 分析、定向改写调用的是配置好的 DeepSeek；未把固定响应冒充真实 AI。

Studio PDF 浏览器按钮可点击，服务端下载路由返回 HTTP 200、`X-Resume-Revision: 9`。保存的 `.runtime/combine-final-resume.pdf` 为 55,679 字节、一页；PyMuPDF 可抽取 `Kai Chen`、`Northstar Media`、`28%` 等与已确认修订版一致的文字。中文和英文模板各九种，样例均有一页真实预览。

真实模型面试：生成六个岗位问题预览，开始会话，逐题回答并保存评分；模型在三题后结束，复盘列出三题和补强指南。随后用 `five_round_server.py` 在同一隔离数据库上替换**仅面试提问服务**，浏览器完成五题，复盘列出全部五条持久化问答；这验证五题上限和 UI 转场，并非真实模型五题输出。

面试记录库：以虚构“Acme Labs（测试）”新建一面记录，浏览器自动评分，详情页显示 7/10、逐题优缺点与补强建议，公司文件夹按轮次归档。390×844 手机视口分别检查岗位页、Studio 和记录库，DOM 文档宽度未超出视口；截图经目视检查可用。

截图：`01`–`10` 为上传、岗位和定向简历；`11`–`16` 为 Studio 与 PDF；`17`–`20` 为真实模型面试；`21`–`22` 为面试记录；`23`–`26` 为固定五题；`27`–`29` 为手机视口；`30` 为明确区分来源文案与 Studio 投递版的最终页面。文件均保存在本目录，供逐屏复查。

## 推断

源 UI 提交与 Resume 分支中摘取的同名提交不能以提交哈希视作等同。`git range-diff` 表明差异集中在 Studio 入口与 G 盘构建兼容脚本；正式合并及测试用于验证三方行为共同存在。浏览器观察到两项后续产品质量缺口：岗位定向文案的预览从原档案提示“缺少联系方式”，即使 Studio 修订版已补齐；现已在界面明确标记该区域为来源档案检查，投递版以 Studio 为准，但数据源尚未统一。AI 参考回答曾把“分析 50 篇内容”扩写成“访谈 50 位创作者”，不可当作候选人事实。已确认 PDF 不含该虚构访谈，面试指南也要求如实说明证据口径。建议下一轮统一两处预览的数据源，并在参考答案展示前做事实校验。

## 交付与剩余检查

集成改动只提交到本分支，不移动 `main`，不清理原始工作树。未验证：PostgreSQL 上从旧版本全链升级与外部部署；隔离 SQLite 只验证新增的 013→015→013→015。最终 Git 检查和提交号在交付说明中记录。

本机验证命令：API 在 `apps/api` 中将 `OPENAI_API_KEY` 设为测试占位值、清除 `OPENAI_BASE_URL`、指定 Typst 0.15.1 的 `TYPST_BIN` 后运行 `python -m pytest tests -q --tb=no` 和 `python -m compileall -q app`。Web 在 `apps/web` 中运行 `npm test`、`npm run type-check`、`npm run build`。上述 API 的三项失败均保留在报告中，没有作为通过处理。
