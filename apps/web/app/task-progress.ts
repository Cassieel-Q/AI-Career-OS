export const TASK_STAGES = {
  jd: ["提交岗位描述", "读取识别结果"],
  "resume-parse": ["提交简历", "读取简历结构", "整理已有经历"],
  "resume-optimize": ["整理经历", "生成岗位策略", "生成岗位定向版本"],
  "interview-questions": ["生成问题预览", "读取题目"],
  "interview-score": ["提交回答", "评分与准备下一题"],
} as const;

export type TaskKind = keyof typeof TASK_STAGES;
export type TaskRow = { label: string; status: "done" | "active" | "pending" };

export function taskProgressRows(kind: TaskKind, activeIndex: number): TaskRow[] {
  return [...TASK_STAGES[kind]].map((label, index) => ({
    label,
    status: index < activeIndex ? "done" : index === activeIndex ? "active" : "pending",
  }));
}

export async function withTaskTimeout<T>(promise: Promise<T>, timeoutMs: number, label: string): Promise<T> {
  let timer: ReturnType<typeof setTimeout> | undefined;
  try {
    return await Promise.race([
      promise,
      new Promise<never>((_, reject) => {
        timer = setTimeout(() => reject(new Error(`${label}超时，请重试。`)), timeoutMs);
      }),
    ]);
  } finally {
    if (timer) clearTimeout(timer);
  }
}
