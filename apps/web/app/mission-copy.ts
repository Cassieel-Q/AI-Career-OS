/** Shared user-facing terms for the existing four-stage mission flow. */
export const MISSION_STAGE_LABELS = ["岗位", "简历", "模拟面试", "面试记录"] as const;

export const MISSION_COPY = {
  listTitle: "岗位档案",
  createRole: "新建岗位",
  addRoleTitle: "添加目标岗位",
  addRoleDescription: "粘贴完整 JD，并确认岗位信息。",
  identifyRole: "识别岗位信息",
  saveRole: "保存岗位",
  resumeSourceTitle: "简历来源",
  resumeSourceDescription: "选择已有简历，或为当前岗位上传新版本。",
  originalResume: "原始简历",
  targetedResume: "岗位定向版本",
  confirmedResume: "确认版本",
  questionPreview: "问题预览",
  interviewReview: "面试复盘",
  strengthening: "补强建议",
} as const;
