# job-collection-v1 · 岗位采集真实验收测试集

目标：证明用户能从 AI Career OS **网页**上采集到真实、有来源、可查看、可保存、
可进入岗位匹配的岗位，而不是只跑通 API。

## 目录

| 路径 | 说明 |
|---|---|
| `fixtures/` | 公开网页结构样例与脱敏 HTML（标准详情页 / 结构改版 / 登录墙 / 提示词注入 / 特殊字符 / 空数组 / 去重标注样本） |
| `cases.jsonl` | 15 类测试场景的输入与预期行为 |
| `expected.jsonl` | 经核对的结构化期望结果（与 `cases.jsonl` 按 id 对应） |
| `test_collection.py` | 解析 / 字段 / 去重 / 安全测试（27 项） |
| `run_live_smoke.py` | 真实公开招聘来源在线采集（RemoteOK / Remotive / Greenhouse / Lever） |
| `report.py` | 6 项指标计算 + 报告 + 158 条人工审核清单 |
| `.dataset_id` | 本次使用的隔离测试数据集 ID |
| `.dataset_origin` | 用户原数据集 ID（验收结束必须切回它） |

## 运行

```powershell
# 后端必须带 AI_CAREER_DATA_DIR，否则回退 DATABASE_URL 会 500
cd apps\api
$env:AI_CAREER_DATA_DIR = "$env:LOCALAPPDATA\AICareerOS"
.venv\Scripts\python -m uvicorn app.main:app --host 127.0.0.1 --port 8100

# 1) 离线测试集（AICAREER_API 用于需要后端的去重/手动编辑用例）
$env:AICAREER_API = "http://127.0.0.1:8100"
.venv\Scripts\python -m pytest ..\..\evals\job-collection-v1\test_collection.py -q

# 2) 真实在线采集
.venv\Scripts\python ..\..\evals\job-collection-v1\run_live_smoke.py --api http://127.0.0.1:8100

# 3) 生成报告与审核清单
.venv\Scripts\python ..\..\evals\job-collection-v1\report.py

# 4) 浏览器 E2E（15 步）
cd apps\web; node scripts\e2e-job-collection-v1.cjs
```

产物：`docs/evaluation/job-collection-v1/{report.md,metrics.json,review-list.md,verdict.json}`，
截图：`docs/screenshots/job-collection-v1/`。

## 两条硬规矩

1. **采集时间 ≠ 岗位发布时间**，接口成功返回**不代表岗位此刻仍在招**，需点开原始链接自行确认。
2. **没有人工标签时，岗位相关性一律记 `UNREVIEWED`**，不输出看似准确的百分比。
   Agent 的「是否 AI 产品相关」只是预判，不是金标准。

## 已知边界

- 只验证了 RemoteOK / Remotive / Greenhouse / Lever 四个**境外公开**来源。
  中文招聘网站（BOSS 直聘、实习僧等）**未做真实验证**，标记 `CHINESE_JOB_SITES_UNVERIFIED`。
- 本机若设置了 `HTTP_PROXY`，访问本机后端的 httpx 客户端必须 `trust_env=False`，
  否则请求会被代理转发并写成绝对路径，后端返回 404（表现为采集莫名其妙失败）。
