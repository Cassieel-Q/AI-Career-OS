/**
 * 顺顺回答用的极简 Markdown 解析器。
 *
 * 只覆盖模型实际会输出的语法：标题、加粗 / 斜体 / 行内代码、有序 / 无序列表、
 * 表格、分隔线、围栏代码块、链接。
 *
 * 这里刻意只做「解析」（纯函数、无 JSX），渲染交给 markdown-render.tsx ——
 * 一来可以单测，二来避免把 HTML 字符串塞进 dangerouslySetInnerHTML。
 */

export type Block =
  | { kind: "heading"; level: number; text: string }
  | { kind: "paragraph"; text: string }
  | { kind: "list"; ordered: boolean; items: string[] }
  | { kind: "table"; header: string[]; rows: string[][] }
  | { kind: "hr" }
  | { kind: "code"; text: string };

export type InlineToken =
  | { kind: "text"; text: string }
  | { kind: "strong"; text: string }
  | { kind: "em"; text: string }
  | { kind: "code"; text: string }
  | { kind: "link"; text: string; href: string };

const HEADING_RE = /^(#{1,6})\s+(.*)$/;
const UL_RE = /^\s*[-*+]\s+(.*)$/;
const OL_RE = /^\s*(\d+)[.)]\s+(.*)$/;
const HR_RE = /^\s*(?:-{3,}|\*{3,}|_{3,})\s*$/;
const FENCE_RE = /^\s*```/;

/** 行内语法一次性切分；捕获组保证分隔符本身留在结果里。 */
const INLINE_RE = /(\*\*[^*\n]+\*\*|`[^`\n]+`|\*[^*\n]+\*|\[[^\]\n]+\]\([^)\n]+\))/g;

function splitRow(line: string): string[] {
  const trimmed = line.trim().replace(/^\|/, "").replace(/\|$/, "");
  return trimmed.split("|").map((cell) => cell.trim());
}

function isDividerRow(line: string): boolean {
  const cells = splitRow(line);
  return cells.length > 0 && cells.every((cell) => /^:?-{2,}:?$/.test(cell.replace(/\s/g, "")));
}

function isBlockStart(line: string): boolean {
  return (
    HEADING_RE.test(line) ||
    HR_RE.test(line) ||
    UL_RE.test(line) ||
    OL_RE.test(line) ||
    FENCE_RE.test(line)
  );
}

export function parseMarkdown(source: string): Block[] {
  const lines = (source ?? "").replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let i = 0;

  while (i < lines.length) {
    const line = lines[i];

    if (FENCE_RE.test(line)) {
      const body: string[] = [];
      i += 1;
      while (i < lines.length && !FENCE_RE.test(lines[i])) {
        body.push(lines[i]);
        i += 1;
      }
      i += 1; // 跳过收尾的 ```
      blocks.push({ kind: "code", text: body.join("\n") });
      continue;
    }

    if (!line.trim()) {
      i += 1;
      continue;
    }

    if (HR_RE.test(line)) {
      blocks.push({ kind: "hr" });
      i += 1;
      continue;
    }

    const heading = HEADING_RE.exec(line);
    if (heading) {
      blocks.push({ kind: "heading", level: heading[1].length, text: heading[2].trim() });
      i += 1;
      continue;
    }

    // 表格：本行是 | a | b |，下一行是 |---|---| 这样的分隔行。
    // 分隔行里可能带空格（| --- | --- |），所以先去掉空白再判断。
    if (line.trim().startsWith("|") && i + 1 < lines.length && isDividerRow(lines[i + 1])) {
      const header = splitRow(line);
      const rows: string[][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(splitRow(lines[i]));
        i += 1;
      }
      blocks.push({ kind: "table", header, rows });
      continue;
    }

    if (UL_RE.test(line) || OL_RE.test(line)) {
      const ordered = OL_RE.test(line);
      const items: string[] = [];
      while (i < lines.length) {
        const matched = ordered ? OL_RE.exec(lines[i]) : UL_RE.exec(lines[i]);
        if (!matched) break;
        items.push((ordered ? matched[2] : matched[1]).trim());
        i += 1;
      }
      blocks.push({ kind: "list", ordered, items });
      continue;
    }

    // 段落：吞掉连续的非块起始行（流式输出中途也能正确成段）。
    const paragraph: string[] = [];
    while (i < lines.length && lines[i].trim() && !isBlockStart(lines[i])) {
      paragraph.push(lines[i].trim());
      i += 1;
    }
    if (paragraph.length) blocks.push({ kind: "paragraph", text: paragraph.join(" ") });
  }

  return blocks;
}

/** 只允许 http(s) / mailto / 站内相对路径，其余一律降级为 #。 */
export function safeHref(href: string): string {
  const value = (href ?? "").trim();
  if (/^(https?:\/\/|mailto:|\/(?!\/))/i.test(value)) return value;
  return "#";
}

export function tokenizeInline(text: string): InlineToken[] {
  const tokens: InlineToken[] = [];
  for (const part of (text ?? "").split(INLINE_RE)) {
    if (!part) continue;
    if (/^\*\*[^*]+\*\*$/.test(part)) {
      tokens.push({ kind: "strong", text: part.slice(2, -2) });
      continue;
    }
    if (/^`[^`]+`$/.test(part)) {
      tokens.push({ kind: "code", text: part.slice(1, -1) });
      continue;
    }
    if (/^\*[^*]+\*$/.test(part)) {
      tokens.push({ kind: "em", text: part.slice(1, -1) });
      continue;
    }
    const link = /^\[([^\]]+)\]\(([^)]+)\)$/.exec(part);
    if (link) {
      tokens.push({ kind: "link", text: link[1], href: safeHref(link[2]) });
      continue;
    }
    tokens.push({ kind: "text", text: part });
  }
  return tokens;
}
