import type { PriorityRead } from "./priorities.ts";

const LANE_LABELS: Record<string, string> = {
  NOW: "现在优先",
  NEXT: "下一阶段",
  NOT_NOW: "暂不优先",
};

const STATE_LABELS: Record<string, string> = {
  MISSING: "明显缺口",
  PARTIAL: "部分具备",
  MATCHED: "已匹配",
  UNCERTAIN: "证据不足",
};

export function priorityLaneLabel(lane: string): string {
  return LANE_LABELS[lane] ?? "待确认";
}

export function priorityStateLabel(state: string): string {
  return STATE_LABELS[state] ?? "证据不足";
}

export function gapSeverityLabel(severity: string): string {
  switch (severity) {
    case "HIGH":
      return "高影响";
    case "MEDIUM":
      return "中等影响";
    case "LOW":
      return "低影响";
    default:
      return "影响待确认";
  }
}

export function priorityLevelLabel(level: string): string {
  switch (level) {
    case "HIGH":
      return "高";
    case "MEDIUM":
      return "中";
    case "LOW":
      return "低";
    default:
      return "待确认";
  }
}

export function priorityMarketSummary(item: Pick<PriorityRead, "frequency_ratio">): string {
  const percentage = Math.round(Math.max(0, Math.min(1, item.frequency_ratio)) * 100);
  return `相关岗位中约 ${percentage}% 提到这项能力。`;
}

export function priorityDecisionReason(item: Pick<PriorityRead, "state" | "frequency_ratio">): string {
  const market = priorityMarketSummary(item);
  switch (item.state) {
    case "MISSING":
      return `${market}当前已确认 Profile 中还缺少直接证据，建议先补足可展示成果。`;
    case "PARTIAL":
      return `${market}当前 Profile 已有部分相关证据，建议补足可核验的结果和范围。`;
    case "MATCHED":
      return `${market}当前 Profile 已有匹配证据，可以保持并把精力转向其他差距。`;
    default:
      return `${market}当前 Profile 证据还不足以做出确定判断，建议先补充事实证据。`;
  }
}
