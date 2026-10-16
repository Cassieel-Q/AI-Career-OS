# Overnight Sprint 已知问题 / 限制（如实记录）

## 外部限制

1. **中文招聘平台无合规公开接口**：BOSS 直聘 / 实习僧 / 拉勾 / 智联均无公开 API 且条款禁止自动化访问。
   合规入口是「粘贴 JD / 上传文件 / 浏览器桥读取当前页面（仅页面可见内容）」，不做绕过。
   因此「AI 产品经理实习」这类中文关键词在 RemoteOK/Remotive 上命中率天然低，界面已如实说明。
2. **Greenhouse / Lever 是企业招聘板接口，不是全网检索**：必须填 board token；
   已验证可用预设见 progress.md；填错返回真实 HTTP 404（不伪造数据）。
   Greenhouse 公开接口不返回公司名 → 公司列显示 board token 并标「待确认」，保存为 NEEDS_REVIEW。
3. **没有来源支持服务端城市/实习/发布时间过滤**：全部为采集后本地过滤，
   报告里会显示 `filter_mode=local` 与 `filtered_out` 数量。

## 代码/运行时（截至 M1 完成）

4. `next build` 在 G 盘仍可能因 `.next/trace` EPERM 失败（环境问题）；`tsc` 与 dev 正常。M6 会做一次隔离 NTFS 构建验证。
5. 部分岗位创建 Mission 时出现 422「JD requirement without source evidence」
   （`mission_service._validate_grounding` 对 LLM 输出做证据校验；模型未配置或输出无证据时触发）。
   属于既有保护逻辑，非本轮引入；E2E 中约偶发，重试或换岗位可过。
6. 基线既有失败：后端 7 项（M2 已用 worktree 在 `bb5b140` 第三次独立验证，与本轮改动无关）、前端 2 项（见 test-results.md）。
7. 网申真实第三方页面兼容性未验（M4）；自动投递不做。
8. **LLM 改写输出存在随机性**：同一条经历两次生成可能不同（差异弹窗如实展示每次变化）；
   偶尔生成含「待补充」占位标记的要点 → 确认投递版会被 placeholder 防呆拦截（预期行为），
   用户需补齐或省略该条。验收脚本已内置模拟用户补齐的步骤。
9. 换模板会推进修订号并使旧确认失效（需重新确认才能下载正式 PDF）——设计如此，防止悄悄替换已确认的投递版。
