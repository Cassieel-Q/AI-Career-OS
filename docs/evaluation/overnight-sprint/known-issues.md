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
10. **RemoteOK 空地点兜底为 `Remote`**：来源没给地点时适配器填 `Remote`（该站确实只收录远程岗，属于可辩护的推断），但不会标 `needs_confirm`。用户按城市筛选时需留意这个兜底值不是来源原文。
11. **岗位类型识别率只有 50%**：158 条真实采集样本里 `employment_type` 为 `UNKNOWN` 的有 79 条。这是「识别不出就如实留空、不猜」的设计后果，不是缺陷，但意味着实习筛选会漏掉一半岗位。
12. **本机 `HTTP_PROXY` 会让 httpx 误报 404**：环境里设置了代理时，httpx 默认 `trust_env=True` 会把 `127.0.0.1` 的请求也发给代理，代理转发后路径被写成绝对形式，后端返回 404。采集脚本已用 `trust_env=False` 规避；这不是应用缺陷，但任何用 httpx 访问本机后端的脚本都要注意。

## M5 / M6 新发现并已修复

10. **备份恢复存在 Zip Slip 路径穿越**（真实安全缺陷，已修）：`restore_as_new_dataset`
    直接把压缩包成员名拼进输出路径，`attachments/../../evil.txt` 会写到数据集目录之外。
    修复：`_safe_attachment_rel()` 拒绝 `..` / 绝对路径 / 反斜杠 / 盘符，并用
    `Path.is_relative_to()` 二次兜底；不安全成员跳过并记录到 `skipped_unsafe_members`。
11. **备份恢复无解压体积上限**（真实安全缺陷，已修）：单成员 >256 MiB 或整包解压
    >1 GiB 直接拒绝（防解压炸弹）。
12. **评测脚本的方法学缺陷**（已修，避免得出假结论）：
    - `run.py` 曾强行把每条经历写成 `KEEP_AND_HIGHLIGHT` 再与 ground_truth 比对——
      等于替被测系统作答。现改为**只确认、不改写**系统自己的四分类；
    - `score.py` 曾把 `NOT_RUN` 计入 `bc_safe`（把没执行当成安全），现单独统计
      `bc_not_run`，且 `safe` 对未执行为 `null`；
    - `score.py` 曾靠 `risk_flags` 反推四分类得出「准确率 2/5」——系统并不输出要点级
      四分类，该数字是假的。现如实标 `b_decision_comparable=0`，交人工标注；
    - 数字白名单原只用单条要点，把「跨要点合并改写」误判为编造。现白名单覆盖
      整份简历 + 对应 JD，误报归零。
13. **测试污染了真实本地数据集**（事故，已修复并加固）：安全测试调用
    `restore_as_new_dataset` 时未隔离，导致 active_dataset 指针被切到一个 17 字节的假库，
    服务全部 503。已把指针恢复为 `ds2610162021590a18`（原 5.9 MB 真实数据集完好），
    污染文件移入 `quarantine/`，并为测试加 autouse 隔离 fixture。
    **教训：任何触碰数据集的测试必须隔离 `AI_CAREER_DATA_DIR`。**
14. 后端必须以 `AI_CAREER_DATA_DIR=%LOCALAPPDATA%\AICareerOS` 启动才走本地数据集模式；
    否则回退 `DATABASE_URL`（本项目未装 psycopg2）→ 500。

## 基线既有失败（与本轮改动无关，已用 worktree 在 bb5b140 验证）

后端 7 项：`test_claim_provider` / `test_gap_analysis` / `test_market_profile` /
`test_priorities` / `test_resume_reliability` / `test_roadmap` / `test_target_jobs`。
M6 全量实测 **856 passed / 7 failed / 5 skipped**，失败项与基线完全一致 → 本轮新增 0 失败。
