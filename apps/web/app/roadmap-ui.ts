import type { RoadmapRead, RoadmapTaskStatus } from "./roadmap.ts";

export type RoadmapUiState = "READY" | "GENERATING" | "SUCCESS" | "ERROR";
export type RoadmapErrorCategory = "TIMEOUT" | "INVALID_RESPONSE" | "UNAVAILABLE" | "NETWORK";

export function roadmapUiState(record: RoadmapRead | null, loading: boolean, error: string): RoadmapUiState {
  if (loading) return "GENERATING";
  if (error) return "ERROR";
  if (record) return "SUCCESS";
  return "READY";
}

export function roadmapErrorMessage(category: RoadmapErrorCategory): string {
  switch (category) {
    case "TIMEOUT":
      return "生成计划耗时较长，本次请求已超时。已有差距和优先级不会丢失，可以重新生成。";
    case "INVALID_RESPONSE":
      return "计划返回内容暂时无法使用。已有差距和优先级不会丢失，请重试。";
    case "UNAVAILABLE":
      return "计划服务暂时不可用。已有差距和优先级不会丢失，请稍后重试。";
    default:
      return "计划生成暂时失败。已有差距和优先级不会丢失，请重试。";
  }
}

export function taskStatusLabel(status: RoadmapTaskStatus | string): string {
  switch (status) {
    case "IN_PROGRESS":
      return "进行中";
    case "DONE":
      return "已完成";
    case "SKIPPED":
      return "已跳过";
    default:
      return "待开始";
  }
}
