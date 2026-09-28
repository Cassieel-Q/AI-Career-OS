# AI 产品经理求职信息 · 牛客面经采集包

## 采集说明
- **采集时间**：2026-09-22 18:45 CST (Asia/Shanghai)
- **登录态补采**：
  - batch1：`_raw/logged_in_scrape/delta_login_batch.json`（scraped_at=2026-09-22T18:37:00+08:00）
  - batch2：`_raw/logged_in_scrape/delta_login_batch2.json`（scraped_at=2026-09-22T18:41:00+08:00）
  - 付费墙/partial 仅收录可见部分并备注；suggest 不进真实频率主统计
- **有效面经**：
  - **真实被问面经：38 篇**（含「5家大厂汇总」按公司拆成的 5 卡，共用原链接；拆卡不重复计帖；登录态全文用于补全问题）
  - **建议题库/备战复盘：6 篇**（不计入真实频率主统计；含作者整理校招高频题）
  - **入库合计：44 篇**
- **目标**：真实被问优先；合计未用虚构内容凑数。

## 目录结构
```
aicareeri-interview/
├── README.md
├── 01-面经数据库.md
├── 02-公司岗位要求.md
├── 03-真实面试题库.md
├── 04-求职准备结论.md
├── sources.json
└── _raw/
    ├── sources.jsonl
    ├── curated_cards.json
    ├── posts/
    └── logged_in_scrape/
        ├── delta_login_batch.json
        ├── delta_login_batch2.json
        └── MERGE_NOTES.md
```

## 筛选规则
- **纳入**：AI/大模型/AIGC/Agent/算法产品等产品向；普通产品但明确考查大模型/AIGC/AI工具者（已标注）。
- **排除**：纯开发/算法岗（京东Agent开发、MiniMax前端工程等已skip）、无实际问题、明显无关；重复转载计一次。
- **汇总帖**：可按公司拆卡，共用链接并备注；登录态全文用于**补全问题**，不新增篇数。
- **真实 vs 建议**：`kind=real` 进入频率统计；`suggest` 仅展示（含帖末作者整理题）。

## 局限
1. 牛客桌面端多为 SPA；**移动端/登录态**可抓到更多正文。部分 `feed/main/detail` 仍短或付费墙。
2. 不绕过付费墙；partial 只留可见部分。
3. 字段缺失一律「未提及」，禁止推测。
4. 仍有候选 URL 未打开（见下）。

## 已尝试搜索词（节选）
- site:nowcoder.com AI产品经理 面经
- site:nowcoder.com 大模型产品经理 面经
- site:nowcoder.com AIGC产品经理 面经
- site:nowcoder.com (字节|美团|百度|蚂蚁|腾讯|小米|vivo|钉钉|携程|理想) AI产品|大模型产品 面经
- site:nowcoder.com (MiniMax|智谱|商汤|科大讯飞|OPPO) AI产品 面经
- site:nowcoder.com 美团大模型产品 转正 面经
- site:nowcoder.com 面试官视角 AI大模型产品面试

## 登录态仍失败 / 跳过
- `batch1-skip` https://www.nowcoder.com/feed/main/detail/ce8f1466c5194f0f9108ad5b6c1abcb6 — 页面前端加载错误，仅见标题片段
- `batch1-skip` https://www.nowcoder.com/discuss/625779241275109376 — 正文空白/partial，仅搜索摘要可见部分题目
- `batch1-skip` https://www.nowcoder.com/discuss/876932752833077248 — 京东Agent开发，作者算法工程师，非产品面经
- `batch1-skip` https://www.nowcoder.com/feed/main/detail/41327ef135dc46639d472034424f11e8 — 与5家大厂汇总重复，已跳过
- `batch2-skip` https://www.nowcoder.com/feed/main/detail/f153ec702e2e417caebd9d135548f207 — 前端工程/研发面经，非AI产品
- `batch2-empty` https://www.nowcoder.com/feed/main/detail/27845689bd3f40199f75d7c63650d1f — 美团 AI产品转正实习 / 内容不存在
- `batch2-empty` https://www.nowcoder.com/feed/main/detail/c1e086b9e7524a93a2504a7cd72da17e —  / 求面经帖，无实际面试问题

## 仍待打开的候选 URL（6）
- https://www.nowcoder.com/discuss/926269263122305024
- https://www.nowcoder.com/feed/main/detail/34604aee25184184af515672f38f52a5
- https://www.nowcoder.com/discuss/921941734647439360
- https://www.nowcoder.com/feed/main/detail/df88c21bd63048c596ce6884bb568231
- https://www.nowcoder.com/feed/main/detail/9a4a39ce588544e68a63b50c0007a7ce
- https://www.nowcoder.com/discuss/797092278194933760

## 覆盖公司（真实面经）
MiniMax, OPPO, vivo, 商汤科技, 多公司（作者真实面试汇总）, 字节跳动, 小米, 快手, 携程, 智谱AI, 未具名（某游戏中厂）, 未具名（面试官复盘）, 理想, 百度, 科大讯飞, 美团, 腾讯, 蚂蚁集团, 阿里巴巴/钉钉

## 新增公司（本轮登录态合并）
携程, 未具名（某游戏中厂）, 理想

## 使用建议
1. 先读 `04-求职准备结论.md` 抓高频考点  
2. 按目标公司刷 `01-面经数据库.md`  
3. 用 `03-真实面试题库.md` 默写与录音模拟  
