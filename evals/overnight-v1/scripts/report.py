"""生成基准报告：docs/evaluation/overnight-benchmark-report.md。

诚实性原则（写死在报告里）：
- 机械评分与人工标注分开呈现，不混淆；
- NOT_RUN 的路径如实标注「未运行」，绝不伪造；
- 单测通过率不作为任务成功率出现。
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
REPORT = Path(r"G:\myself\ai-career\docs\evaluation\overnight-benchmark-report.md")


def main() -> int:
    results_dir = ROOT / "results"
    run_files = sorted(results_dir.glob("run-*.json"))
    score_files = sorted(results_dir.glob("score-*.json"))

    lines: list[str] = []
    lines.append("# Overnight Benchmark 报告（overnight-v1）")
    lines.append("")
    lines.append(f"生成时间：{datetime.now(timezone.utc).isoformat()}")
    lines.append("")
    lines.append("## 数据集构成")
    lines.append("")
    lines.append("| 项 | 数量 | 来源标记 |")
    lines.append("|---|---|---|")
    lines.append("| JD | 30 | 全部 SYNTHETIC（公司/要求均为化名合成，7 类岗位带 differentiators） |")
    lines.append("| 简历 | 10 | 全部 SYNTHETIC（化名，无真实个人信息；validate.py 有隐私红线检查） |")
    lines.append("| 配对 | 30 | STRONG 9 / PARTIAL 13 / WEAK 8（人工预先判定） |")
    lines.append("| 改写案例 | 90 | 每配对 3 条，带 ground_truth 四分类与事实状态 |")
    lines.append("| 对抗/安全案例 | 15 | 15 类各 1 条（含提示词注入 / 编造压力 / 自动投递请求） |")
    lines.append("")
    lines.append("## A/B Baseline")
    lines.append("")
    if not run_files:
        lines.append("_尚未运行（results/ 下没有 run-*.json）。运行方式见 evals/overnight-v1/README.md。_")
    else:
        latest_score = score_files[-1] if score_files else None
        if latest_score:
            data = json.loads(latest_score.read_text(encoding="utf-8"))
            s = data["summary"]
            lines.append(f"最近一次运行：`{run_files[-1].name}`，评分：`{latest_score.name}`")
            lines.append("")
            lines.append("| 指标 | AI Career OS（B） | Direct LLM（A） |")
            lines.append("|---|---|---|")
            scored = s.get("b_bullets_scored", 0)
            b_cell = f"已运行 {s.get('b_pairs_run', 0)} 个配对 / {scored} 条要点参与机械评分"
            a_cell = "已运行" if s["a_total"] > s["a_not_run"] else f"NOT_RUN（{s['a_not_run']}/{s['a_total']} 未配置模型）"
            lines.append(f"| 运行状态 | {b_cell} | {a_cell} |")
            lines.append(
                f"| 四分类（要点级） | 机械评分**不覆盖**（可比对 {s['b_decision_comparable']} 条）："
                "系统对单条要点输出的是 status + risk_flags，不是四分类，硬猜出来的准确率是假的 | 待人工标注 |"
            )
            lines.append(f"| 疑似编造数字（白名单外的新数字，待人工复核） | {s['b_possibly_fabricated']} | 待人工标注 |")
            lines.append(f"| 空改写 | {s['b_empty_rewrite']} | 待人工标注 |")
            lines.append("")
            lines.append(
                f"对抗/安全案例：{s['bc_safe']}/{s['bc_total']} 通过机械安全检查；"
                f"其中按预期被系统拒绝 {s.get('bc_rejected_as_expected', 0)} 条；"
                f"违规 {len(s['bc_violations'])} 条；未运行 {s.get('bc_not_run', 0)} 条（未运行不计入安全）"
            )
            if s["bc_violations"]:
                lines.append("")
                for item in s["bc_violations"]:
                    lines.append(f"- `{item['case_id']}` {item['category']}：{item['violations']}")
            if s.get("bc_not_run_detail"):
                lines.append("")
                lines.append("未运行明细（如实列出，不算通过）：")
                for item in s["bc_not_run_detail"]:
                    lines.append(f"- `{item['case_id']}` {item['category']}：{item.get('not_run_reason')}")
        lines.append("")
        lines.append("> 说明：A 路径（Direct LLM）未配置 `BASELINE_DIRECT_LLM_*` 时为 NOT_RUN，报告中如实标注，不伪造对比数据。")
    lines.append("")
    lines.append("## 口径声明（防自欺）")
    lines.append("")
    lines.append("1. **机械评分 ≠ 人工标注**：本报告中的四分类正确率来自规则比对，属可复现的机械评分；")
    lines.append("   最终结论以 `annotations/GUIDELINES.md` 规范下的人工标注为准，两者在表格中分开呈现。")
    lines.append("2. **单测通过率 ≠ 任务成功率**：后端 pytest 的通过率不在此报告中作为改写质量指标出现。")
    lines.append("3. **NOT_RUN 不伪造**：任何因服务未启动 / 模型未配置而未运行的路径，均标注 NOT_RUN。")
    lines.append("4. **隐私红线**：数据集校验（validate.py）内置真实手机号 / 身份证号 / 非示例邮箱检测。")
    lines.append("")
    lines.append("## 人工标注状态")
    lines.append("")
    lines.append("_待人工完成：按 annotations/GUIDELINES.md 对 90 条改写案例逐条标注（JSON 模板见 annotations/template.json）。_")

    REPORT.write_text("\n".join(lines) + "\n", encoding="utf-8")
    print(f"报告：{REPORT}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
