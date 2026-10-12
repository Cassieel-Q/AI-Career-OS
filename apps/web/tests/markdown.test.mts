import assert from "node:assert/strict";
import { test } from "node:test";

import { parseMarkdown, safeHref, tokenizeInline } from "../app/markdown.ts";

test("headings are parsed with their level", () => {
  const blocks = parseMarkdown("## 一、JD 到底要什么\n### 三条硬要求");
  assert.deepEqual(blocks, [
    { kind: "heading", level: 2, text: "一、JD 到底要什么" },
    { kind: "heading", level: 3, text: "三条硬要求" },
  ]);
});

test("pipe tables become table blocks (the shape the assistant actually emits)", () => {
  const source = [
    "| JD 要求 | 重要度 | 你的对应弹药 |",
    "|---|-----|------|",
    "| 在读，计算机/工程背景优先 | HIGH | 大连理工（985）+ 计算机相关 |",
    "| 对 AI 应用 / LLM / Agent 框架有浓厚兴趣 | HIGH | IntentFlow、Agent Workflow |",
  ].join("\n");
  const blocks = parseMarkdown(source);
  assert.equal(blocks.length, 1);
  const [table] = blocks;
  assert.equal(table.kind, "table");
  if (table.kind !== "table") return;
  assert.deepEqual(table.header, ["JD 要求", "重要度", "你的对应弹药"]);
  assert.equal(table.rows.length, 2);
  assert.deepEqual(table.rows[0], ["在读，计算机/工程背景优先", "HIGH", "大连理工（985）+ 计算机相关"]);
});

test("a pipe line without a divider stays a paragraph (mid-stream table)", () => {
  const blocks = parseMarkdown("| JD 要求 | 重要度 |");
  assert.equal(blocks[0].kind, "paragraph");
});

test("unordered and ordered lists are grouped", () => {
  const blocks = parseMarkdown("- 第一点\n- 第二点\n\n1. 甲\n2. 乙");
  assert.deepEqual(blocks.map((b) => b.kind), ["list", "list"]);
  assert.deepEqual(blocks[0], { kind: "list", ordered: false, items: ["第一点", "第二点"] });
  assert.deepEqual(blocks[1], { kind: "list", ordered: true, items: ["甲", "乙"] });
});

test("bold and inline code are tokenised", () => {
  assert.deepEqual(tokenizeInline("**强** 和 `code` 以及普通文字"), [
    { kind: "strong", text: "强" },
    { kind: "text", text: " 和 " },
    { kind: "code", text: "code" },
    { kind: "text", text: " 以及普通文字" },
  ]);
});

test("an unclosed bold marker is left as plain text", () => {
  assert.deepEqual(tokenizeInline("还在流式输出 **未闭合"), [
    { kind: "text", text: "还在流式输出 **未闭合" },
  ]);
});

test("horizontal rules and fenced code blocks", () => {
  const blocks = parseMarkdown("---\n\n```\nconst a = 1;\n```");
  assert.deepEqual(blocks[0], { kind: "hr" });
  assert.deepEqual(blocks[1], { kind: "code", text: "const a = 1;" });
});

test("paragraph lines are joined with a space", () => {
  const blocks = parseMarkdown("第一句\n第二句");
  assert.deepEqual(blocks, [{ kind: "paragraph", text: "第一句 第二句" }]);
});

test("safeHref drops javascript: and protocol-relative urls", () => {
  assert.equal(safeHref("https://example.com"), "https://example.com");
  assert.equal(safeHref("/missions"), "/missions");
  assert.equal(safeHref("/"), "/");
  assert.equal(safeHref("javascript:alert(1)"), "#");
  assert.equal(safeHref("//evil.example.com"), "#");
  assert.equal(safeHref("data:text/html,x"), "#");
});
