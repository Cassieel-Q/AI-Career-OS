"""校验 overnight-v1 数据集：schema 一致性 + 完整性 + 禁止真实敏感信息。

用法：
    python scripts/validate.py
退出码 0 = 全部通过；1 = 存在问题（逐条列出）。
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
DATA = ROOT / "data"
SCHEMA = ROOT / "schema"

FAILURES: list[str] = []


def fail(msg: str) -> None:
    FAILURES.append(msg)


def check_enum(value, allowed, where):
    if value not in allowed:
        fail(f"{where}: 枚举值 {value!r} 不在 {sorted(allowed)}")


def validate_jd(jd: dict, idx: int) -> None:
    where = f"jobs[{idx}] {jd.get('id')}"
    if not re.match(r"^jd-\d{3}$", str(jd.get("id", ""))):
        fail(f"{where}: id 格式非法")
    check_enum(jd.get("source"), {"REAL_AUTHORIZED", "PUBLIC_SOURCE", "SYNTHETIC", "DEMO"}, where)
    check_enum(jd.get("category"), {"AI_PRODUCT", "BACKEND", "DATA_ANALYST", "CONTENT_OPS", "UI_DESIGN", "SALES_CS", "HR"}, where)
    if len(jd.get("responsibilities", [])) < 3:
        fail(f"{where}: 职责不足 3 条")
    if len(jd.get("requirements", [])) < 3:
        fail(f"{where}: 要求不足 3 条")
    if not jd.get("differentiators"):
        fail(f"{where}: 缺少 differentiators（同类别 JD 必须有可区分差别）")
    if len(str(jd.get("raw_text", ""))) < 40:
        fail(f"{where}: raw_text 过短")


def validate_resume(rs: dict, idx: int) -> None:
    where = f"resumes[{idx}] {rs.get('id')}"
    if not re.match(r"^rs-\d{2}$", str(rs.get("id", ""))):
        fail(f"{where}: id 格式非法")
    check_enum(rs.get("source"), {"REAL_AUTHORIZED", "PUBLIC_SOURCE", "SYNTHETIC", "DEMO"}, where)
    if not rs.get("candidate_alias"):
        fail(f"{where}: 缺少化名")
    if not rs.get("experiences"):
        fail(f"{where}: 无经历")
    if len(str(rs.get("raw_text", ""))) < 40:
        fail(f"{where}: raw_text 过短")


def validate_pair(pair: dict, idx: int, resume_ids: set[str], jd_ids: set[str]) -> None:
    where = f"pairs[{idx}] {pair.get('id')}"
    if pair.get("resume_id") not in resume_ids:
        fail(f"{where}: resume_id {pair.get('resume_id')} 不存在")
    if pair.get("jd_id") not in jd_ids:
        fail(f"{where}: jd_id {pair.get('jd_id')} 不存在")
    check_enum(pair.get("expected_fit"), {"STRONG", "PARTIAL", "WEAK"}, where)


def validate_rewrite(case: dict, idx: int, pair_ids: set[str]) -> None:
    where = f"rewrite_cases[{idx}] {case.get('id')}"
    if case.get("pair_id") not in pair_ids:
        fail(f"{where}: pair_id 不存在")
    gt = case.get("ground_truth") or {}
    check_enum(gt.get("expected_decision"), {"KEEP_AND_HIGHLIGHT", "KEEP", "DEEMPHASIZE", "OMIT"}, where)
    check_enum(gt.get("fact_status"), {"SUPPORTED", "NEEDS_CONFIRMATION", "UNSUPPORTED", "CONTRADICTED"}, where)


def validate_badcase(case: dict, idx: int) -> None:
    where = f"bad_cases[{idx}] {case.get('id')}"
    check_enum(case.get("input_channel"), {"JD", "RESUME", "BOTH"}, where)
    behavior = case.get("expected_behavior") or {}
    if not behavior.get("must") or not behavior.get("must_not"):
        fail(f"{where}: expected_behavior 必须同时包含 must 与 must_not")


def main() -> int:
    # --- 数量要求 ---
    jobs = json.loads((DATA / "jobs.json").read_text(encoding="utf-8"))
    resumes = json.loads((DATA / "resumes.json").read_text(encoding="utf-8"))
    pairs = json.loads((DATA / "pairs.json").read_text(encoding="utf-8"))
    rewrites = json.loads((DATA / "rewrite_cases.json").read_text(encoding="utf-8"))
    bad_cases = json.loads((DATA / "bad_cases.json").read_text(encoding="utf-8"))

    if len(jobs) != 30:
        fail(f"JD 数量必须为 30，当前 {len(jobs)}")
    if len(resumes) != 10:
        fail(f"简历数量必须为 10，当前 {len(resumes)}")
    if len(pairs) != 30:
        fail(f"配对数量必须为 30，当前 {len(pairs)}")
    if len(rewrites) != 90:
        fail(f"改写案例必须为 90，当前 {len(rewrites)}")
    if len(bad_cases) != 15:
        fail(f"Bad Case 必须为 15，当前 {len(bad_cases)}")

    # --- 7 类岗位覆盖 ---
    categories = {jd.get("category") for jd in jobs}
    required = {"AI_PRODUCT", "BACKEND", "DATA_ANALYST", "CONTENT_OPS", "UI_DESIGN", "SALES_CS", "HR"}
    missing = required - categories
    if missing:
        fail(f"缺少岗位类别：{sorted(missing)}")

    # --- 同类别 JD 的 differentiators 必须能区分 ---
    by_cat: dict[str, list[dict]] = {}
    for jd in jobs:
        by_cat.setdefault(jd["category"], []).append(jd)
    for cat, items in by_cat.items():
        if len(items) >= 2:
            texts = {tuple(jd.get("differentiators", [])) for jd in items}
            if len(texts) < len(items):
                fail(f"类别 {cat} 的不同 JD differentiators 重复，评测无法区分")

    # --- 实体校验 ---
    for idx, jd in enumerate(jobs):
        validate_jd(jd, idx)
    resume_ids = {rs["id"] for rs in resumes}
    jd_ids = {jd["id"] for jd in jobs}
    pair_ids = {pr["id"] for pr in pairs}
    for idx, rs in enumerate(resumes):
        validate_resume(rs, idx)
    for idx, pr in enumerate(pairs):
        validate_pair(pr, idx, resume_ids, jd_ids)
    for idx, case in enumerate(rewrites):
        validate_rewrite(case, idx, pair_ids)
    for idx, case in enumerate(bad_cases):
        validate_badcase(case, idx)

    # --- 15 类 Bad Case 类别各至少 1 条 ---
    expected_categories = {
        "PROMPT_INJECTION_JD", "PROMPT_INJECTION_RESUME", "FAKE_SYSTEM_PROMPT",
        "FABRICATE_METRICS_PRESSURE", "OMIT_EVERYTHING_PRESSURE", "INFLATE_TITLE_PRESSURE",
        "SENSITIVE_INFO_REQUEST", "ROLEPLAY_JAILBREAK", "EMPTY_JD", "OVERLONG_INPUT",
        "NON_CHINESE_INPUT", "SPECIAL_CHARS_FLOOD", "JSON_YAML_INJECTION",
        "CONTRADICTORY_JD_REQUIREMENTS", "AUTO_APPLY_REQUEST",
    }
    got = {case.get("category") for case in bad_cases}
    missing_categories = expected_categories - got
    if missing_categories:
        fail(f"缺少 Bad Case 类别：{sorted(missing_categories)}")

    # --- 隐私红线：数据里不得出现真实手机号/身份证号/邮箱（合成简历用化名+示例域名除外） ---
    id_re = re.compile(r"\b\d{17}[\dXx]\b")
    phone_re = re.compile(r"(?<!\d)1[3-9]\d{9}(?!\d)")
    email_re = re.compile(r"[A-Za-z0-9._%+-]+@(?!example\.com)[A-Za-z0-9.-]+\.[A-Za-z]{2,}")
    for rs in resumes:
        blob = json.dumps(rs, ensure_ascii=False)
        for regex, label in ((id_re, "身份证号"), (phone_re, "手机号"), (email_re, "非示例邮箱")):
            if regex.search(blob):
                fail(f"{rs['id']}: 检测到疑似真实{label}（隐私红线）")
    for jd in jobs:
        blob = json.dumps(jd, ensure_ascii=False)
        if id_re.search(blob):
            fail(f"{jd['id']}: 检测到疑似真实身份证号（隐私红线）")

    if FAILURES:
        print(f"validate：{len(FAILURES)} 个问题")
        for item in FAILURES:
            print(f"  ✗ {item}")
        return 1
    print(
        f"validate OK：jobs={len(jobs)} resumes={len(resumes)} pairs={len(pairs)} "
        f"rewrites={len(rewrites)} bad_cases={len(bad_cases)}；类别覆盖={len(categories)}/7"
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
