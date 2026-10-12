"use client";

import type { ReactNode } from "react";

import { parseMarkdown, tokenizeInline, type Block, type InlineToken } from "./markdown.ts";

/**
 * 把 markdown.ts 解析出的结构渲染成 React 元素。
 * 全程不拼 HTML 字符串，所以不存在注入风险。
 */

function renderTokens(tokens: InlineToken[], keyPrefix: string): ReactNode[] {
  return tokens.map((token, index) => {
    const key = `${keyPrefix}-${index}`;
    switch (token.kind) {
      case "strong":
        return <strong key={key}>{token.text}</strong>;
      case "em":
        return <em key={key}>{token.text}</em>;
      case "code":
        return <code key={key}>{token.text}</code>;
      case "link":
        return (
          <a key={key} href={token.href} target="_blank" rel="noreferrer">
            {token.text}
          </a>
        );
      default:
        return <span key={key}>{token.text}</span>;
    }
  });
}

function inline(text: string, keyPrefix: string): ReactNode[] {
  return renderTokens(tokenizeInline(text), keyPrefix);
}

function renderBlock(block: Block, index: number): ReactNode {
  const key = `md-${index}`;
  switch (block.kind) {
    case "heading": {
      const level = Math.min(Math.max(block.level, 1), 6);
      const Tag = `h${level}` as "h1" | "h2" | "h3" | "h4" | "h5" | "h6";
      return (
        <Tag key={key} className={`md-heading md-heading-${level}`}>
          {inline(block.text, key)}
        </Tag>
      );
    }
    case "paragraph":
      return <p key={key}>{inline(block.text, key)}</p>;
    case "list": {
      const items = block.items.map((item, i) => (
        <li key={`${key}-${i}`}>{inline(item, `${key}-${i}`)}</li>
      ));
      return block.ordered ? <ol key={key}>{items}</ol> : <ul key={key}>{items}</ul>;
    }
    case "table":
      return (
        <div className="md-table-wrap" key={key}>
          <table>
            <thead>
              <tr>
                {block.header.map((cell, c) => (
                  <th key={`${key}-h${c}`}>{inline(cell, `${key}-h${c}`)}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, r) => (
                <tr key={`${key}-r${r}`}>
                  {block.header.map((_, c) => (
                    <td key={`${key}-r${r}-c${c}`}>{inline(row[c] ?? "", `${key}-r${r}-c${c}`)}</td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      );
    case "hr":
      return <hr key={key} />;
    case "code":
      return (
        <pre key={key}>
          <code>{block.text}</code>
        </pre>
      );
    default:
      return null;
  }
}

export function Markdown({ text }: { text: string }) {
  const blocks = parseMarkdown(text);
  return <div className="md-body">{blocks.map(renderBlock)}</div>;
}
