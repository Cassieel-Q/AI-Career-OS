"use client";

/**
 * 匹配度圆环（用户明确要求「评分用圆环」）。
 *
 * 纯 SVG，不依赖图表库：底色轨道 + 前景弧，中间显示分数。
 * 颜色沿用设计令牌（黑白灰 + attention/danger 两档强调），避免出现彩色环。
 */
type Props = {
  score: number | null;
  size?: number;
  label?: string;
  /** 大号显示（侧栏 / 岗位页）：分数用更大字号。 */
  large?: boolean;
  /** 未算出分时的占位文案。 */
  emptyText?: string;
};

function toneOf(score: number | null): "good" | "warn" | "bad" | "muted" {
  if (score === null) return "muted";
  if (score >= 70) return "good";
  if (score >= 40) return "warn";
  return "bad";
}

const TONE_COLOR: Record<string, string> = {
  good: "var(--fill-selected)",
  warn: "var(--accent-attention)",
  bad: "var(--accent-danger)",
  muted: "var(--text-disabled)",
};

export function ScoreRing({ score, size = 56, label, large = false, emptyText = "—" }: Props) {
  const stroke = Math.max(4, Math.round(size / 10));
  const radius = (size - stroke) / 2;
  const circumference = 2 * Math.PI * radius;
  const clamped = score === null ? 0 : Math.max(0, Math.min(100, score));
  const dash = (clamped / 100) * circumference;
  const tone = toneOf(score);

  return (
    <span
      className={`score-ring${large ? " large" : ""}`}
      style={{ width: size, height: size }}
      role="img"
      aria-label={score === null ? "尚未评估匹配度" : `${label ?? "匹配度"} ${clamped} 分`}
    >
      <svg viewBox={`0 0 ${size} ${size}`} width={size} height={size} aria-hidden="true" focusable="false">
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke="var(--border-medium)"
          strokeWidth={stroke}
        />
        {score === null ? null : (
          <circle
            cx={size / 2}
            cy={size / 2}
            r={radius}
            fill="none"
            stroke={TONE_COLOR[tone]}
            strokeWidth={stroke}
            strokeLinecap="round"
            strokeDasharray={`${dash} ${circumference - dash}`}
            transform={`rotate(-90 ${size / 2} ${size / 2})`}
          />
        )}
      </svg>
      <span className="score-ring-value" style={{ color: TONE_COLOR[tone] }}>
        {score === null ? emptyText : clamped}
      </span>
    </span>
  );
}

export default ScoreRing;
