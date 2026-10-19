# 真实浏览器主流程 E2E（7 条，43/43 通过）

**不是 API 测试冒充的 E2E**：脚本用 Playwright + Chromium 真实打开页面、点击按钮、填写表单、读取页面文本；只在准备前数据时走接口（那些步骤本身也是用户在页面上完成的动作，见流程 1）。

最后一次执行：**2026-10-19 12:42（43/43 通过）**，前端跑的是 **production build**（`next build` + `next start`），不是 dev server。

## 运行方式

```bash
# 三个本地服务（本轮实际端口）
python docs/evaluation/trusted-workflow-v12/browser/stub-llm-server.py --port 8801   # 本地桩模型
AI_CAREER_DATA_DIR=.runtime/e2e-v12 uvicorn app.main:app --port 8100                 # 后端
# 前端：production 构建（必须显式注入 API 地址，否则前端会回退到别的项目的 8000 端口）
cd apps/web && NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8100 npm run build
node --require ./scripts/next-g-drive-fs-compat.cjs ./node_modules/next/dist/bin/next start -p 3100
# 跑
node docs/evaluation/trusted-workflow-v12/browser/e2e-trusted-workflow.cjs \
  --web http://127.0.0.1:3100 --api http://127.0.0.1:8100
```

结果：`docs/evaluation/trusted-workflow-v12/browser/results/e2e-result.json`
截图：`…/results/screenshots/`（12 张，每个关键页面一张）

## 模型怎么处理的（重要）

本轮**未授权真实模型付费调用**，所以用一个本地桩模型服务（OpenAI 兼容、不联网、可复现）替代：

- 改写只照抄源事实，不新增数字；
- 面试参考回答**故意**返回一段含编造数字的第一人称作答（「把转化率提升了 37%，日活从三千涨到一万二，还带了一个五人小组」），用来验证 Sprint A 的闸门真的会拦。

因此本 E2E 验证的是**产品流程与前端行为**，**不是模型输出质量**。

## 流程 1｜首次用户：首页 → 粘贴简历 → 建档 → 加岗位 → 生成岗位简历 → Studio → 导出（10 项）

| 步骤 | 结果 |
|---|---|
| 首页打开 | ✅ |
| 点「导入简历」→「粘贴简历文字建档」→ 填全文 → 建档 | ✅ profile 已生成 |
| 添加目标岗位（粘贴 JD） | ✅ 201（重跑时若岗位已存在会复用，不再报重复） |
| 生成岗位定向简历 | ✅ 201 |
| 确认岗位简历 | ✅ `CONFIRMED` |
| Studio 打开并读到修订号 | ✅ revision=1 |
| 草稿 PDF 可导出且文件名带 `_DRAFT` | ✅ `…_v1_DRAFT.pdf` |
| **缺姓名时正式投递版被拦下** | ✅ 409 + `missing_name` |
| **填了姓名但高风险事实未核对，仍然阻塞** | ✅ 409 + `unconfirmed_fact:block` |
| 正式投递版 PDF 导出 | ✅ 文件名 `陈林_Acme_AI_产品经理实习生_v3.pdf`，无 `_DRAFT` |

**这一步最能说明问题**：填了内容 ≠ 核对过事实。两次 409 分别证明「缺内容」和「未核对」是两道独立的门。

## 流程 2｜事实不足时的参考回答（6 项）

| 步骤 | 结果 |
|---|---|
| 解析出可面试主张 | ✅ 200 |
| 开始一轮模拟面试 | ✅ 201 |
| 参考回答返回结构化结果 | ✅ `detail=true`，列出 1 项待补 |
| **桩模型编造的数字被闸门拦下** | ✅ 参考答案变成「证据不足，不能把这项动作或数字写入候选人的回答…」，**37% / 一万二 / 三千全部没有出现** |
| 降级时只给已知事实与待补，不给成稿 | ✅ `grounded=false` |
| 面试页可打开并给出下一步 | ✅ |

## 流程 3｜多岗位复用（7 项）

| 步骤 | 结果 |
|---|---|
| 同一份简历关联三个岗位 | ✅ 3 个 mission |
| 三份岗位各自生成自己的岗位版 | ✅ 各自 revision=1 |
| 更新共享原始事实（走「核对 + 写回」入口） | ✅ `applied_to_source=true` |
| **影响面提示「关联 N 份，其中 M 份可能需要更新」** | ✅ 「这项事实关联了 3 份岗位简历，其中 3 份可能需要更新。」 |
| **只更新选中的那一份** | ✅ `changed=true`，只改了 missions[1] |
| **另外两份保持原版本** | ✅ 修订号 `3 / 2 / 1`，未被选中的两份没动 |
| 简历页的事实核对面板渲染出待核对事实 | ✅ |

## 流程 4｜面试版本 = 实际投递的版本（6 项）

| 步骤 | 结果 |
|---|---|
| 确认正式投递版 | ✅ revision=3 |
| 创建投递记录 | ✅ |
| 绑定投递版本并生成快照 | ✅ `studio_revision=3` |
| **投递之后继续改 Studio，面试仍读投递版** | ✅ `source=delivered_snapshot`，`delivered=true` |
| **投递后新增的内容不会混进面试准备** | ✅ 「投递之后才新增的经历」不在面试材料里 |
| 面试页标注使用的是投递版本 | ✅ 页面出现投递版本相关提示 |

## 流程 5｜档案恢复（2 项）

| 步骤 | 结果 |
|---|---|
| 清了 LocalStorage 后仍可从服务端档案恢复 | ✅ 首页出现「已有档案」区块 |
| 服务端档案列表可用（不需要记 UUID） | ✅ count=15 |

> 这一条在**本轮之前是不成立的**：`readLocalProfiles` 早就写好了，但没有任何页面调用它。是这次写 E2E 才发现并接上的（`41fef66`）。
> 本次在**干净隔离库**上跑，所以恢复列表 count=1（库里只有本轮建的那份档案），这是预期值。

## 流程 6｜无模型路径（4 项）

| 步骤 | 结果 |
|---|---|
| 无模型建档（本地规则解析） | ✅ `parse_source=LOCAL_RULE` |
| 简历原文可查看 / 编辑 | ✅ |
| 无模型也能管理岗位 | ✅ 201 |
| AI 功能指向模型配置说明 | ✅ |

## 流程 7｜已确认档案的受控字段修正（8 项）— 本轮 P1-A / P1-B

| 步骤 | 结果 |
|---|---|
| **已确认档案的整体 `PUT /profiles/{id}` 仍然被拒** | ✅ 409（没有为了「能改」而放开整体覆写） |
| 受控修正起止时间并返回新旧值 | ✅ `applied=["dates"]`，`old=2025.03 → new=2025.03-2025.09` |
| 修正已写回原始事实 | ✅ 回读 `dates=2025.03-2025.09` |
| 白名单外字段修正被拒 | ✅ 422（`full_name` 不在受控白名单里） |
| 影响面提示「可能需要更新」 | ✅ 「这项事实关联了 3 份岗位简历，其中 3 份可能需要更新。」 |
| 只更新选中的那一份 | ✅ `changed=true` |
| **历史投递快照内容哈希不变** | ✅ `before=2b1f81732949 after=2b1f81732949` |
| 核对页出现受控修正入口 | ✅ 点开事实后出现「受控修正」与「起止时间」输入框 |

## 导出 PDF 的实物证据

`results/flow1-draft.pdf` 与 `results/flow1-final.pdf`，用 PyMuPDF 抽文本核对：

| 文件 | 页数 | 大小 | 含 `DRAFT` 水印 | 含姓名 |
|---|---|---|---|---|
| `flow1-draft.pdf` | 1 | 59,790 B | **是** | 否（草稿下载发生在补姓名之前） |
| `flow1-final.pdf` | 1 | 59,978 B | **否** | **是（陈林）** |

两份都是真实 PDF（`%PDF-1.7`），用 PyMuPDF 抽文本核对于 2026-10-19 12:45，不是占位文件。
PDF 里出现的姓名/手机/邮箱均为合成数据（陈林 / 13800000000 / chenlin@example.com / 示例大学）。

## 修过的接口用法错误（都是写 E2E 才暴露的）

- 经历筛选 PUT 缺 `confidence` / `supporting_evidence_refs` → 422；
- 面试会话创建 body 缺 `claim_id` → 422；
- Studio PATCH 缺 `If-Match` → 428；
- 桩模型把「岗位简历生成」与「What Matters」的提示词误判成「面试提问」（两个提示词里都含 `question` / `interview-ready`）→ 后端 502；
- 桩模型把「面试提问」误判成「评分」（两个提示词里都含 `reference_answer`）→ 后端 422；
- 评分写在「被回答的那一轮」上，最后一轮是系统补的追问（`evaluation` 为空）→ E2E 取错了轮次。
- **确认投递版前必须先逐条接受改写要点**：`confirm-target-resume` 会返回 409
  「这版改写还没有任何被接受的要点」。这是产品的真实闸门（防止生成空白经历简历），
  E2E 原来直接跳过，导致次要岗位确认不了、Studio 建不出来。已补 `acceptBullets()`
  走 `PATCH /target-resume-bullets/{id}`。
- **「简历」页的当前档案读的是 localStorage，不是 URL 参数**：`?profile_id=` 无效。
  加上流程 5 刚清过存储，核对面板根本不渲染。已改为 `addInitScript` 写入
  `ai-career-os-dogfood-profile-id` 后再导航。
- `undefined` 会被 `JSON.stringify` 静默丢键：修订号 map 少一个键时看不出是哪份岗位出了问题。
  已改成显式写 `null`。
