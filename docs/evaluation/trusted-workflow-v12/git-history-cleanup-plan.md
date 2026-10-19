# Git 历史清理方案（待确认，尚未执行）

> **执行记录（2026-10-19，用户已确认的两项决定）**
> 1. ✅ `main` **快进**到 `903db2f`（非破坏性，`a033b21..903db2f`）——远程默认分支的当前树已无真实姓名。
> 2. ⬜ 历史重写 + 强推 **暂不执行**，仓库维持 **Public**，接受「历史提交里仍可翻到真实姓名」的残留风险。
>    另：本轮补清了 `FINAL-FREEZE.md` 里一处把姓名当 grep 示例的引用（HEAD 树现已 0 命中）。

> 生成时间：2026-10-19　适用于 `Cassieel-Q/AI-Career-OS`（当前 **Public**）
> **本文件不写入真实姓名本身**（用 `<真实姓名>` 占位），避免清理动作反而新增一处暴露。
> 替换词表文件必须放在 **未被 Git 跟踪** 的目录（本轮用 `.runtime/name-replacements.txt`）。

---

## 一、核实结论（本轮实际扫描，2026-10-19）

扫描范围：GitHub 上全部 **11 个分支**的历史与当前树、全部 **1971 个 blob**。
（先 `git fetch origin --prune` 拉全远程引用，再逐分支 `git grep` + 全 blob `git cat-file --batch` 扫描。）

| 检查项 | 结果 |
|---|---|
| **真实姓名** | 当前树命中 **9 / 11 个分支**（main + 8 个 feature 分支）；历史命中 **8 个分支**，共 **35 个 blob** |
| API Key（`sk-` / `ghp_` / `AKIA` / `AIza` / `xox`） | **0 命中** |
| 真实手机号 | **0**：出现的 11 个号码里 9 个是 `13800000000` 类样例，另 2 个（`18381088901`、`19049093719`）经核对是 **SHA-256 哈希的子串**，非号码 |
| 身份证号 | **0**：18 位数字全是面经库的雪花 ID 与测试夹具 |
| 个人邮箱 | **0**：全部为 `example.com` 样例或招聘网站上的第三方企业邮箱 |
| 数据库 / `.env` / 密钥文件 | **0**（只有 `.env.example`） |
| 简历原件（PDF/DOCX） | **0**（树内 5 份 PDF 均为评测产物，已抽文本核对，无姓名） |
| 已删除的隐私截图是否被重新引入 | **否**：旧 bundle 里独有的 21 张图片（含 `image/微信图片_20261003164815_*.jpg` 5 张）在远程可达对象里 **0 命中**；远程 195 个图片对象中有 160 个是此前已脱敏后重新加入的版本 |

**扫描未覆盖**：209 张公开图片的**画面内容**未做 OCR 核验（本机无可用的 OCR），
因此「截图中不含个人信息」这一条标记为 **UNVERIFIED**，不写成已确认。

---

## 二、备份（已完成，可恢复）

| 备份 | 位置 | 说明 |
|---|---|---|
| 本地完整备份 | `D:\ai-career-local-final-20261019.bundle` | 35,525,471 B，35 个引用（含全部本地分支、远程跟踪分支、标签 `v1.2.0-rc1`），`git bundle verify` 通过 |
| 更早的备份（含隐私历史） | `D:\ai-career-backup-20261017.bundle` | 30,729,895 B，**保留不删、绝不上传、绝不纳入 Git**；含 `feat/*`、`feature/boss-local-app`、`feature/resumeforge-*` 与旧 `main`（`db9ec58`）等已下线的私有分支 |
| 远程镜像（建议执行前再做一次） | `git clone --mirror https://github.com/Cassieel-Q/AI-Career-OS.git D:\ai-career-github-mirror-20261019` | 强推之前把远程当前状态整个拉下来，是最直接的一键回滚源 |

**恢复办法**：

```bash
# 从 bundle 恢复（会重建完整的分支 / 标签 / 对象）
git clone D:\ai-career-local-final-20261019.bundle G:\myself\ai-career-restored
# 或从远程镜像恢复
git clone --mirror D:\ai-career-github-mirror-20261019 <新目录>
```

---

## 三、清理方案（待你确认后才执行）

### 3.1 思路

只对**文本 blob 做字符串替换**（`git filter-repo --replace-text`），
把 `<真实姓名>` 换成 `示例用户`。**不删文件、不动目录结构、不改代码逻辑**，
因此重写后的 HEAD 树与重写前**逐字节一致（除被替换的姓名）**，可用 `git diff` 校验。

### 3.2 命令（按顺序）

```bash
# 0) 先做远程镜像备份（回滚源）
git clone --mirror https://github.com/Cassieel-Q/AI-Career-OS.git D:\ai-career-github-mirror-20261019

# 1) 准备替换词表 —— 放在未被跟踪的目录，绝不提交
echo '<真实姓名>==>示例用户' > .runtime/name-replacements.txt

# 2) 重写全部引用（filter-repo 会顺手移除 origin 远端配置，属正常行为）
git filter-repo --replace-text .runtime/name-replacements.txt --force

# 3) 自检：必须全为 0
git log --all -S'<真实姓名>' --oneline | wc -l      # 期望 0
#    另跑一次全 blob 扫描（本轮脚本 .runtime/blobscan.py）确认 0 命中

# 4) 内容等价性校验（重写前后 HEAD 树除姓名外应无差异）
git diff <重写前的 c518b5c/5fef7eb> HEAD --stat

# 5) 重新加回远端，并强推（--force-with-lease 比 --force 安全一档）
git remote add origin https://github.com/Cassieel-Q/AI-Career-OS.git
git push --force-with-lease --all origin
git push --force --tags origin

# 6) 重建标签（旧标签指向旧 SHA，必须重建后才跟得上新历史）
git tag -f v1.2.0-rc1 <新的稳定提交 SHA>
git push --force origin refs/tags/v1.2.0-rc1
```

### 3.3 不做什么

- **不推送旧 bundle 里的任何分支**（`feat/aioscareer-combine`、`feat/pixel-ui-copy`、`feat/resume-studio`、
  `feature/boss-local-app`、`feature/resumeforge-48h`、`feature/resumeforge-overnight`、旧 `main` `db9ec58`）。
  这些分支只存在于本地 bundle，**正是它们携带此前删除的隐私截图**。这是「不重新引入旧截图」的关键约束。
- **不做 `--strip-blobs-bigger-than` 之类的激进裁剪**，避免误删正常图片。
- **不改代码、不加功能**。

---

## 四、影响范围（破坏性操作，须先确认）

| 影响 | 说明 |
|---|---|
| **所有提交 SHA 改变** | 含该姓名的提交及其**全部后代**都会被重写；11 个分支里 9 个受影响 → 实际上近乎全部分支的 SHA 都会变 |
| **标签失效** | `v1.2.0-rc1` 指向的旧提交消失，必须按 3.2 第 6 步重建 |
| **需要强推** | 正常 push 会被拒绝，必须 `--force-with-lease` / `--force`；**这会覆盖 GitHub 上的分支历史** |
| **协作者必须重新 clone** | 任何人本地的旧 clone 都无法再正常 pull（历史分叉）；仓库目前只有你一个账号，实际影响可控 |
| **PR / Issue 里的旧 SHA 链接失效** | 若曾被引用，会变成 404 |
| **GitHub 侧的游离对象不会立即消失** | 强推后旧对象在 GitHub 上仍可能按 SHA 直接访问一段时间，需向 GitHub Support 申请 GC，或删除并重建仓库才能彻底清除 |
| **截图内容不在清理能力内** | `filter-repo` 只改文本；若某张截图的**画面里**有个人信息，需要人工替换图片并重写，本轮未做 OCR 核验 |

### 回滚

任何一步出问题，都用第二节的 bundle 或远程镜像整库恢复后重新强推：

```bash
git clone D:\ai-career-local-final-20261019.bundle <新目录>
cd <新目录> && git remote add origin https://github.com/Cassieel-Q/AI-Career-OS.git
git push --force --all origin && git push --force --tags origin
```

---

## 五、结论：现在适不适合设为 Public

- **当前树**：`feature/trusted-workflow-v12`（`5fef7eb`）已脱敏，**安全**；但默认分支 `main`（`a033b21`）的
  **当前树里仍有真实姓名**，公开状态下任何人打开仓库首页就能看到。
- **历史**：即使把 `main` 快进到最新提交，**历史提交里仍有 35 个含姓名的 blob**，
  任何人翻历史都能看到 —— 只有执行第三节的重写才能消除。
- 因此：**「适合 Public」取决于是否接受历史里的姓名残留**。
  若接受 → 至少应把 `main` 快进到已脱敏的提交（非破坏性，立刻消掉首页暴露）；
  若不接受 → 必须先执行第三节重写 + 强推，或在重写完成前把仓库设为 Private。
