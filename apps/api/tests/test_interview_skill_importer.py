import json

from app.interview_skill_importer import sync_interview_skills


def test_sync_imports_only_real_cards_with_source_and_questions(tmp_path) -> None:
    source = tmp_path / "source"
    raw = source / "_raw"
    raw.mkdir(parents=True)
    (raw / "curated_cards.json").write_text(
        json.dumps(
            [
                {
                    "id": 101,
                    "kind": "real",
                    "company": "Baidu",
                    "role": "AI产品经理",
                    "url": "https://example.test/real-101",
                    "abilities": ["智能硬件"],
                    "rounds": [{"focus": "项目深挖", "qs": [{"q": "你如何定义测试指标？", "tags": ["项目"]}]}],
                },
                {
                    "id": 102,
                    "kind": "suggest",
                    "company": "Baidu",
                    "role": "AI产品经理",
                    "url": "https://example.test/suggest-102",
                    "rounds": [{"qs": [{"q": "不应进入真实面经包", "tags": []}]}],
                },
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    dest = tmp_path / "knowledge" / "interview_skills"

    counts = sync_interview_skills(source, dest)

    assert counts == {"Baidu": 1}
    packs = list(dest.glob("curated_*.md"))
    assert [pack.name for pack in packs] == ["curated_baidu_ai_product.md"]
    body = packs[0].read_text(encoding="utf-8")
    assert "provenance: CURATED" in body
    assert "https://example.test/real-101" in body
    assert "你如何定义测试指标？" in body
    assert "不应进入真实面经包" not in body
