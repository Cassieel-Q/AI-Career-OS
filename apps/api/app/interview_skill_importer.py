"""Import curated Nowcoder cards into knowledge/interview_skills/curated/*.md"""
from __future__ import annotations

import argparse
import json
import re
from collections import defaultdict
from pathlib import Path
from typing import Any

from .company_aliases import canonical_company

COMPANY_DISPLAY = {
    "baidu": "Baidu",
    "bytedance": "ByteDance",
    "xiaohongshu": "Xiaohongshu",
}


def _slug(text: str) -> str:
    s = re.sub(r"[^a-zA-Z0-9\u4e00-\u9fff]+", "_", text.strip()).strip("_").casefold()
    return s[:80] or "unknown"


def _role_family(card: dict[str, Any]) -> str:
    blob = f"{card.get('role','')} {card.get('direction','')} {' '.join(card.get('abilities') or [])}".casefold()
    if any(k in blob for k in ("ai", "aigc", "llm", "大模型", "智能")):
        return "AI_PRODUCT"
    return "PRODUCT"


def load_cards(source_root: Path) -> list[dict[str, Any]]:
    path = source_root / "_raw" / "curated_cards.json"
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise ValueError("curated_cards.json must be a list")
    return data


def group_cards(cards: list[dict[str, Any]]) -> dict[tuple[str, str], list[dict[str, Any]]]:
    groups: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    for card in cards:
        if card.get("kind") != "real":
            continue
        company = canonical_company(str(card.get("company") or "")) or _slug(str(card.get("company") or "unknown"))
        family = _role_family(card)
        groups[(company, family)].append(card)
    return groups


def render_pack(company_key: str, family: str, cards: list[dict[str, Any]]) -> str:
    display = COMPANY_DISPLAY.get(company_key, cards[0].get("company") or company_key)
    urls = sorted({c.get("url") for c in cards if c.get("url")})
    competencies: list[str] = []
    for c in cards:
        for a in c.get("abilities") or []:
            if a and a not in competencies:
                competencies.append(str(a))
        for t in c.get("ai_tech") or []:
            if t and t not in competencies:
                competencies.append(str(t))
    competencies = competencies[:24]
    q_lines: list[str] = []
    focus_lines: list[str] = []
    for c in cards:
        for rnd in c.get("rounds") or []:
            focus = rnd.get("focus")
            if focus:
                focus_lines.append(f"- {focus} （来源面经 {c.get('id')}）")
            for qs in rnd.get("qs") or []:
                q = qs.get("q")
                if q:
                    tags = ",".join(qs.get("tags") or [])
                    q_lines.append(f"- {q}" + (f" [{tags}]" if tags else ""))
    n = len(cards)
    pack_id = f"CURATED_{company_key.upper()}_{family}"
    recency = next((c.get("published") for c in cards if c.get("published")), None)
    body = "\n".join(
        [
            f"在已整理的 {n} 条相关面经中观察到以下信号（CURATED，非合成演示）。",
            "",
            "## Interviewer intent / focus",
            *(focus_lines[:40] or ["- （面经未提供明确 focus）"]),
            "",
            "## Question patterns",
            *(q_lines[:80] or ["- （无题目）"]),
            "",
            "## Weak answer patterns to avoid",
            "- 只背教程定义，说不出自己项目里的证据与边界",
            "- 模型指标上升却说不清业务指标是否同步",
            "- 把团队结果写成个人独立 Ownership 且无法举证",
            "",
            "## Strong evidence to prepare",
            "- 项目中的责任边界（你做了什么 / 没做什么）",
            "- 可复核的指标与决策取舍",
            "- 失败案例与复盘",
        ]
    )
    roles = sorted({str(c.get("role")) for c in cards if c.get("role")})[:8]
    fm = {
        "id": pack_id,
        "kind": "interview_skill",
        "name": f"{display} curated {family} interview signals",
        "version": "1.0.0",
        "provenance": "CURATED",
        "company": display,
        "roles": roles,
        "role_family": family,
        "competencies": competencies,
        "source_count": n,
        "recency": recency,
        "source_refs": list(urls)[:32],
        "confidence": "high" if n >= 3 else "medium",
    }
    # YAML-ish manual dump to avoid pyyaml dependency in script path
    def yml(v: Any, indent: int = 0) -> str:
        sp = "  " * indent
        if isinstance(v, list):
            if not v:
                return "[]"
            lines = []
            for item in v:
                if isinstance(item, (dict, list)):
                    lines.append(f"{sp}- {yml(item, indent+1).lstrip()}")
                else:
                    lines.append(f"{sp}- {json.dumps(item, ensure_ascii=False)}")
            return "\n".join(lines)
        if isinstance(v, str):
            if "\n" in v or ":" in v:
                return json.dumps(v, ensure_ascii=False)
            return v
        if v is None:
            return "null"
        return json.dumps(v, ensure_ascii=False)

    lines = ["---"]
    for k, v in fm.items():
        if isinstance(v, list):
            if not v:
                lines.append(f"{k}: []")
            else:
                lines.append(f"{k}:")
                for item in v:
                    lines.append(f"  - {json.dumps(item, ensure_ascii=False)}")
        else:
            lines.append(f"{k}: {yml(v)}")
    lines.append("---")
    lines.append(body)
    lines.append("")
    return "\n".join(lines)


def sync_interview_skills(source_root: Path, dest_dir: Path) -> dict[str, int]:
    cards = load_cards(source_root)
    groups = group_cards(cards)
    dest_dir.mkdir(parents=True, exist_ok=True)
    # clear previous curated generated files
    for old in dest_dir.glob("curated_*.md"):
        old.unlink()
    counts: dict[str, int] = defaultdict(int)
    for (company_key, family), grouped in sorted(groups.items()):
        text = render_pack(company_key, family, grouped)
        display = COMPANY_DISPLAY.get(company_key, company_key)
        out = dest_dir / f"curated_{_slug(company_key)}_{_slug(family)}.md"
        out.write_text(text, encoding="utf-8")
        counts[display] += 1
    return dict(counts)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Sync curated interview skills")
    parser.add_argument("--source", type=Path, required=True)
    parser.add_argument("--dest", type=Path, required=True)
    args = parser.parse_args(argv)
    counts = sync_interview_skills(args.source, args.dest)
    print(json.dumps({"packs_by_company": counts, "total_packs": sum(counts.values())}, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
