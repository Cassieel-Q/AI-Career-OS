/** 首页「下一步」：按用户当前状态动态给出主线动作（可信求职 v1.2 · 指令 3.1）。 */

export type NextStepKey = "IMPORT_RESUME" | "ADD_JOB" | "REVIEW_EXPORT" | "AFTER_APPLY";

export type HomeNextStep = {
  key: NextStepKey;
  /** 主行动按钮文案。 */
  action: string;
  title: string;
  desc: string;
  href: string;
};

export type NextStepInput = {
  hasProfile: boolean;
  missionCount: number;
  resumeCount: number;
  appliedCount: number;
  latestMissionId?: string | null;
};

const studioHref = (missionId: string | null | undefined) =>
  missionId ? `/missions/${encodeURIComponent(missionId)}/resume/studio` : "/missions";

/**
 * 四个状态 → 一个主行动：
 * 没有档案 → 导入简历；有档案没岗位 → 添加岗位；有岗位没投递版 → 审阅并导出；
 * 已有投递 → 看历史投递版 / 准备面试 / 跟进状态。
 */
export function nextStepFor(input: NextStepInput): HomeNextStep {
  const { hasProfile, missionCount, resumeCount, appliedCount, latestMissionId } = input;

  if (!hasProfile) {
    return {
      key: "IMPORT_RESUME",
      action: "导入简历",
      title: "先把简历放进来",
      desc: "上传 PDF，或直接粘贴简历文字建档——不配置 AI 模型也能建档、编辑原文和管理岗位。",
      href: "/resumes",
    };
  }
  if (missionCount === 0) {
    return {
      key: "ADD_JOB",
      action: "添加目标岗位",
      title: "挑一个真实岗位",
      desc: "粘贴 JD 或导入岗位链接，系统会按这份岗位生成定向简历。",
      href: "/missions/new",
    };
  }
  if (resumeCount === 0) {
    return {
      key: "REVIEW_EXPORT",
      action: "审阅并导出岗位版简历",
      title: "生成这一版的岗位简历",
      desc: "选择要突出的经历，确认事实，再导出可投递的版本。",
      href: studioHref(latestMissionId),
    };
  }
  if (appliedCount > 0) {
    return {
      key: "AFTER_APPLY",
      action: "查看已投递版本",
      title: "按投出去的那一版准备面试",
      desc: "面试准备默认读取你真正投递的那份 PDF，不会混入投递之后才新增的经历。",
      href: "/tracker",
    };
  }
  return {
    key: "REVIEW_EXPORT",
    action: "继续审阅并导出",
    title: "把岗位版本导出成可投递的 PDF",
    desc: "草稿与正式投递版分开：草稿可随时导出，正式版需要通过投递前检查。",
    href: studioHref(latestMissionId),
  };
}

/** 已投递之后需要保留的次级入口。 */
export const AFTER_APPLY_LINKS = [
  { label: "面试准备", href: "/interview-records" },
  { label: "跟进状态", href: "/tracker" },
  { label: "历史投递版", href: "/resumes" },
] as const;
