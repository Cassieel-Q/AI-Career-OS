import type { ReactNode } from "react";

import { referenceAnswerSections, type ReferenceAnswerDetail } from "./fact-trust.ts";

const SOURCE_LABEL: Record<string, string> = {
  SOURCE_EXTRACTED: "来自原始简历",
  USER_PROVIDED: "你补充的事实",
  AI_PROPOSED: "AI 建议（未核实）",
};

/**
 * 参考答案展示。
 *
 * 事实充分时展示可使用的示范表达；事实不足时只展示已知事实、待补项与回答结构，
 * 绝不把补造的第一人称经历当成候选人的回答。
 */
export function ReferenceAnswerView({
  detail,
  text,
  title = "参考回答",
}: {
  detail?: ReferenceAnswerDetail | null;
  text?: string | null;
  title?: string;
}): ReactNode {
  if (!detail) {
    // 旧数据没有结构化详情：只做纯文本展示，不声称它经过事实核验。
    if (!text) return null;
    return (
      <div className="reference-answer">
        <strong>{title}</strong>
        <p>{text}</p>
      </div>
    );
  }

  const { wording, known, missing, structure, blocked } = referenceAnswerSections(detail);

  return (
    <div className="reference-answer" data-grounded={detail.grounded ? "true" : "false"}>
      <strong>{title}</strong>
      {wording ? (
        <p className="reference-wording">{wording}</p>
      ) : blocked ? (
        <p className="reference-blocked">
          证据不足，未生成示范表达。下面是已有的事实、还缺的信息和建议的表达结构。
        </p>
      ) : null}

      {known.length ? (
        <div className="reference-block">
          <span className="reference-label">已知事实</span>
          <ul>
            {known.map((item, index) => (
              <li key={`known-${index}`}>
                {item.text}
                {item.source_kind ? (
                  <em className="reference-source">
                    （{SOURCE_LABEL[item.source_kind] ?? item.source_kind}
                    {item.quote ? `：${item.quote}` : ""}）
                  </em>
                ) : null}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {missing.length ? (
        <div className="reference-block">
          <span className="reference-label">还需要你补充</span>
          <ul>
            {missing.map((item, index) => (
              <li key={`missing-${index}`}>
                {item.aspect ?? "待补充"}
                {item.question ? `：${item.question}` : ""}
              </li>
            ))}
          </ul>
        </div>
      ) : null}

      {structure.length ? (
        <div className="reference-block">
          <span className="reference-label">建议回答结构</span>
          <ol>
            {structure.map((step, index) => (
              <li key={`step-${index}`}>{step}</li>
            ))}
          </ol>
        </div>
      ) : null}
    </div>
  );
}
