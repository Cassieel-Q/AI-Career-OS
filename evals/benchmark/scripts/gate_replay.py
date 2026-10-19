"""同一组固定输入，分别跑「不经过事实闸门（A）」与「经过正式事实闸门（B）」。

为什么有这个脚本
----------------
离线 interview 对照显示 15 条固定输入里有 5 条参考答案事实错误，但这个统计来自
fixture 里的**标签**，从来没有真正调用过产品的事实闸门——也就是说「5 次事实错误」
只说明这些输入的事实前提在简历里不成立，并不能说明闸门拦得住。

本脚本做最小调整：把同一组固定输入送两条路：

- A：原始生成结果，**不经过**事实闸门（保持原样输出）；
- B：同一份原始生成结果，**经过**产品实际使用的
  ``InterviewProvider._gate_reference_answer``。

记录每一条的：原始输出、是否含无依据主张、闸门是否拦截/降级、是否误伤有证据的
正常回答、以及闸门也无法判断的情况。

诚实边界（不要拿这个脚本宣称事实错误率为零）
--------------------------------------------
1. **A 侧原始输出是确定性重放语料**，不是真实模型输出。真实模型调用次数为 0，
   花费 0；真实模型下的效果仍是 ``NOT_RUN``。
2. 重放语料按 fixture 记录的标签构造（resume_grounded=true → 复述简历原文；
   resume_grounded=false → 采纳问题里不成立的前提），因此「A 侧 5 条含无依据主张」
   与 fixture 标签一致，**不是独立测量**。
3. 真正独立的是「rewrite 语料列」：那 17 条是既有固定文本 + 既有人工标签，
   用它看闸门有没有误伤（false positive）。
4. 闸门判定不确定时保守降级；本脚本不做「未检出编造 ⇒ 不会编造」的推断。
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[3]
sys.path.insert(0, str(REPO_ROOT / "apps" / "api"))

from app.fact_trust import extract_numeric_values, merge_grounding, screen_reference_wording  # noqa: E402
from app.interview_provider import OpenAIInterviewProvider  # noqa: E402

FIXTURES = REPO_ROOT / "evals" / "benchmark" / "fixtures"
REPORTS = REPO_ROOT / "evals" / "benchmark" / "reports"

#: 提问的引导语（去掉后剩下的就是提问所假设的那件事）。
_LEAD_IN = re.compile(
    r"^\s*(tell me about a time|tell me about|walk (?:me )?through|describe|explain how|explain|"
    r"how did you|how would you|how do you|what|share)\b[^A-Za-z]*",
    re.IGNORECASE,
)
_YOU = re.compile(r"\byou(r)?\b", re.IGNORECASE)


def _first_person_answer(question: str, resume_text: str, grounded: bool) -> str:
    """确定性地生成「原始生成结果」（重放语料，非真实模型输出）。

    - grounded=True：复述简历里确实存在的那句话（有证据）；
    - grounded=False：采纳提问里成立不了的前提——旧版 P10 的失败模式：
      按提问的假设作答，把「你做过 X」直接写成第一人称。
    """
    if grounded:
        # 取简历里与提问关键词重合度最高的一行作为复述对象
        keywords = [w.lower() for w in re.findall(r"[A-Za-z]{4,}", question)]
        lines = [line.strip("- ").strip() for line in resume_text.splitlines() if line.strip()]
        best, best_hits = lines[0] if lines else "", -1
        for line in lines:
            hits = sum(1 for word in keywords if word in line.lower())
            if hits > best_hits:
                best, best_hits = line, hits
        return f"我做过这件事：{best}"
    premise = _LEAD_IN.sub("", question).strip().rstrip("?").strip()
    premise = _YOU.sub(lambda m: "我" + ("的" if m.group(1) else ""), premise)
    premise = re.sub(r"\s+", " ", premise).strip(" .")
    return f"我{premise}。"


def _ungrounded_numbers(text: str, corpus: str) -> list[int]:
    """原始输出里、证据语料中不存在的数量值（独立的可核对信号，不是闸门结论）。"""
    corpus_numbers = extract_numeric_values(corpus)
    return sorted(value for value in extract_numeric_values(text) if value not in corpus_numbers)


def run_gate(raw_answer: str, corpus: str) -> dict[str, object]:
    """把原始输出送进产品使用的同一套事实闸门（B 侧）。"""
    evaluation = {
        "reference_answer": raw_answer,
        "reference_answer_detail": {
            "grounded": True,
            "sample_wording": raw_answer,
            "known_facts": [],
            "missing_facts": [],
            "answer_structure": [],
        },
    }
    gated = OpenAIInterviewProvider._gate_reference_answer(
        evaluation,
        target_job={"final_resume": {}},
        claim={"claim": ""},
        evidence=[],
        context=corpus,
    )
    detail = gated.get("reference_answer_detail") or {}
    return {
        "blocked": not bool(detail.get("grounded")),
        "blocked_reason": detail.get("blocked_reason"),
        "sample_wording": detail.get("sample_wording"),
        "screening": detail.get("screening") or {},
        "output_is_degraded": (gated.get("reference_answer") or "") != raw_answer,
    }


def _load_resumes() -> dict[str, str]:
    payload = json.loads((FIXTURES / "resume" / "synthetic_expanded.json").read_text(encoding="utf-8"))
    return {row["resume_id"]: row.get("raw_text") or "" for row in payload}


def _jds() -> dict[str, str]:
    out: dict[str, str] = {}
    for path in (FIXTURES / "jd").glob("*.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            out[row.get("jd_id") or ""] = (
                f"{row.get('company') or ''} {row.get('role_title') or ''} {row.get('must_have') or ''}"
            )
    return out


def build_cases() -> tuple[list[dict[str, object]], list[dict[str, object]]]:
    resumes = _load_resumes()
    jd_text = _jds()
    rows = json.loads((FIXTURES / "interview" / "synthetic_offline.json").read_text(encoding="utf-8"))

    interview_cases: list[dict[str, object]] = []
    for row in rows:
        expected = row.get("expected") or {}
        resume_text = resumes.get(row.get("resume_id"), "")
        corpus = merge_grounding([resume_text, jd_text.get(row.get("jd_id"), "")])
        grounded = bool(expected.get("resume_grounded"))
        raw = _first_person_answer(row.get("question") or "", resume_text, grounded)
        gate = run_gate(raw, corpus)
        interview_cases.append(
            {
                "question_id": row.get("question_id"),
                "question": row.get("question"),
                "labeled_fact_error": bool(expected.get("reference_answer_fact_error")),
                "labeled_resume_grounded": grounded,
                "a_raw_output": raw,
                "a_ungrounded_numbers": _ungrounded_numbers(raw, corpus),
                "a_has_unsupported_claim": bool(_ungrounded_numbers(raw, corpus)) or not grounded,
                "b_blocked": gate["blocked"],
                "b_blocked_reason": gate["blocked_reason"],
                "b_output_is_degraded": gate["output_is_degraded"],
                "b_screening": gate["screening"],
            }
        )

    rewrite_cases: list[dict[str, object]] = []
    for path in (FIXTURES / "rewrite").glob("*.json"):
        for row in json.loads(path.read_text(encoding="utf-8")):
            source = " ".join(row.get("source_facts") or [])
            suggestion = str(row.get("suggestion_text") or "")
            gate = run_gate(suggestion, source)
            rewrite_cases.append(
                {
                    "unit_id": row.get("unit_id"),
                    "labeled_critical_fact_error": bool(row.get("critical_fact_error")),
                    "a_raw_output": suggestion,
                    "a_ungrounded_numbers": _ungrounded_numbers(suggestion, source),
                    "b_blocked": gate["blocked"],
                    "b_blocked_reason": gate["blocked_reason"],
                    "b_screening": gate["screening"],
                }
            )
    return interview_cases, rewrite_cases


def main() -> int:
    parser = argparse.ArgumentParser(description="事实闸门 A/B 重放（离线、零模型调用）")
    parser.add_argument("--out", default="", help="输出报告路径")
    args = parser.parse_args()

    interview_cases, rewrite_cases = build_cases()

    def summarize(cases: list[dict[str, object]], label_key: str) -> dict[str, object]:
        total = len(cases)
        labeled_bad = sum(1 for c in cases if c[label_key])
        blocked = sum(1 for c in cases if c["b_blocked"])
        # 误伤：标签说没问题（或确有证据），闸门却拦了
        false_block = sum(1 for c in cases if not c[label_key] and c["b_blocked"])
        # 漏放：标签说有问题，闸门却没拦
        missed = sum(1 for c in cases if c[label_key] and not c["b_blocked"])
        return {
            "total": total,
            "labeled_unsupported": labeled_bad,
            "gate_blocked": blocked,
            "false_block_on_grounded": false_block,
            "missed_by_gate": missed,
        }

    report = {
        "created_at": datetime.now(timezone.utc).isoformat(),
        "provider_called": False,
        "real_model_runs": 0,
        "estimated_cost_cny": 0,
        "method": "重放既有固定输入；A=原始输出不经过闸门，B=同一输出经过产品闸门",
        "caveats": [
            "A 侧原始输出为确定性重放语料（按 fixture 标签构造），不是真实模型输出",
            "interview 列的『含无依据主张』与 fixture 标签一致，不是独立测量",
            "rewrite 列的文本与标签均来自既有固定语料，可用于观察误伤",
            "未检出编造不代表系统不会编造；人工维度仍为 UNRATED",
        ],
        "interview": {
            "summary": summarize(interview_cases, "labeled_fact_error"),
            "cases": interview_cases,
        },
        "rewrite": {
            "summary": summarize(rewrite_cases, "labeled_critical_fact_error"),
            "cases": rewrite_cases,
        },
    }

    out = Path(args.out) if args.out else REPORTS / f"gate-replay-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print(f"[gate-replay] 报告：{out}")
    print(f"[gate-replay] interview: {json.dumps(report['interview']['summary'], ensure_ascii=False)}")
    print(f"[gate-replay] rewrite  : {json.dumps(report['rewrite']['summary'], ensure_ascii=False)}")
    for case in interview_cases:
        if case["labeled_fact_error"]:
            print(
                f"  · {case['question_id']} 拦截={case['b_blocked']} 降级={case['b_output_is_degraded']} "
                f"无依据数字={case['a_ungrounded_numbers']}"
            )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
