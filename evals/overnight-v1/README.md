# overnight-v1 基准数据集

本目录是通宵冲刺的 M5 交付：可复现的简历改写基准（数据集 + schema + 脚本）。

## 目录

```
evals/overnight-v1/
  schema/           JSON Schema（jd / resume / pair / rewrite_case / badcase / annotation）
  data/             数据集（30 JD / 10 简历 / 30 配对 / 90 改写案例 / 15 Bad Case）
  annotations/      人工标注规范（GUIDELINES.md）+ 模板
  scripts/          build_dataset.py / validate.py / run.py / score.py / report.py
  results/          运行与评分输出（git 忽略大文件，只留汇总）
```

## 数据原则

1. **全部合成**：JD 与简历均为合成内容（`source: SYNTHETIC`），公司化名、人名化名；
   `validate.py` 内置隐私红线（真实手机号 / 身份证号 / 非示例邮箱 → 校验失败）。
2. **7 类岗位**：AI 产品 / 后端 / 数据 / 内容运营 / UI 设计 / 销售客服 / HR，
   每个 JD 带 `differentiators`（同类别不同 JD 的要求差别，评测必须能区分）。
3. **配对与 ground truth**：30 个配对人工预先判定 STRONG/PARTIAL/WEAK；
   90 条改写案例带期望四分类（KEEP_AND_HIGHLIGHT/KEEP/DEEMPHASIZE/OMIT）与事实状态。
4. **15 类对抗/安全案例**：提示词注入（JD/简历）、伪造 system prompt、编造量化压力、
   全 OMIT 压力、头衔膨胀压力、敏感信息请求、角色扮演越狱、空 JD、超长输入、
   非中文输入、特殊字符、JSON 注入、自相矛盾 JD、自动投递请求。

## 用法

```powershell
cd evals\overnight-v1\scripts

# 1) 校验数据集（数量 / schema / 隐私红线 / 类别覆盖）
python validate.py

# 2) 重新生成数据集（可复现，固定内容）
python build_dataset.py

# 3) 运行基准（A/B baseline）
#    B 路径走本地 AI Career OS 服务（默认 http://127.0.0.1:8100）
#    A 路径 Direct LLM 需要环境变量：
#      BASELINE_DIRECT_LLM_BASE_URL / BASELINE_DIRECT_LLM_API_KEY / BASELINE_DIRECT_LLM_MODEL
python run.py --api http://127.0.0.1:8100
# 任一路径不可用 → 该路径全部案例记 NOT_RUN（不伪造）

# 4) 机械评分（decision/数字编造/安全；人工标注仍是最终口径）
python score.py results\run-<时间戳>.json

# 5) 生成报告 → docs/evaluation/overnight-benchmark-report.md
python report.py
```

## 口径声明

- **机械评分 ≠ 人工标注**：`score.py` 输出的是可复现的规则评分；
  最终结论以 `annotations/GUIDELINES.md` 下的人工标注为准，报告里两者分开呈现。
- **单测通过率 ≠ 任务成功率**：pytest 通过率不出现在本基准的任何质量指标里。
- **NOT_RUN 不伪造**：服务未启动或模型未配置时，对应路径如实标注 NOT_RUN。
