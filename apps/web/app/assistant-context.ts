"use client";

/**
 * 第三阶段：助手页面上下文——让「顺顺」在进入时自动拿到当前岗位与岗位版简历，
 * 用户不需要再手动选择一次。
 *
 * 优先级：URL 查询参数（/assistant?mission_id=..&target_resume_id=..）
 *        > sessionStorage（岗位页/简历工作台写入的「最近查看」上下文）。
 */

const MISSION_KEY = "ai-career.activeMissionId";
const TARGET_RESUME_KEY = "ai-career.activeTargetResumeId";

export type AssistantPageContext = {
  missionId: string | null;
  targetResumeId: string | null;
  route: string | null;
};

function fromUrl(): AssistantPageContext {
  if (typeof window === "undefined") return { missionId: null, targetResumeId: null, route: null };
  const params = new URLSearchParams(window.location.search);
  return {
    missionId: params.get("mission_id"),
    targetResumeId: params.get("target_resume_id"),
    route: params.get("route") || window.location.pathname,
  };
}

function fromStorage(): AssistantPageContext {
  if (typeof window === "undefined") return { missionId: null, targetResumeId: null, route: null };
  return {
    missionId: window.sessionStorage.getItem(MISSION_KEY),
    targetResumeId: window.sessionStorage.getItem(TARGET_RESUME_KEY),
    route: window.location.pathname,
  };
}

/** 岗位页 / 简历工作台调用：把「当前正在看的岗位与岗位版简历」登记为助手上下文。 */
export function publishAssistantContext(missionId: string | null, targetResumeId: string | null): void {
  if (typeof window === "undefined") return;
  if (missionId) window.sessionStorage.setItem(MISSION_KEY, missionId);
  if (targetResumeId) window.sessionStorage.setItem(TARGET_RESUME_KEY, targetResumeId);
}

export function readAssistantContext(): AssistantPageContext {
  const url = fromUrl();
  const stored = fromStorage();
  return {
    missionId: url.missionId || stored.missionId,
    targetResumeId: url.targetResumeId || stored.targetResumeId,
    route: url.route || stored.route,
  };
}

/** 从 /missions/<uuid> 路径里解析岗位 id（浮窗场景没有查询参数时兜底）。 */
export function missionIdFromPath(pathname: string): string | null {
  const match = /\/missions\/([0-9a-fA-F-]{36})/.exec(pathname || "");
  return match ? match[1] : null;
}
