export type SkillGroup = { label: string; items: string[] };

const categories = [
  { label: "语言能力", terms: ["英语", "english", "cet", "雅思", "托福", "ielts", "toefl", "六级", "四级"] },
  { label: "AI 产品能力", terms: ["llm", "prompt", "agent", "rag", "skill", "模型", "人机协同", "ai 工作流", "ai产品", "ai 产品"] },
  { label: "产品能力", terms: ["需求", "竞品", "prd", "原型", "figma", "axure", "流程", "验收", "迭代", "交互", "用户"] },
  { label: "技术与工具", terms: ["codex", "cursor", "git", "python", "typescript", "javascript", "sql", "api", "react", "expo", "fastapi", "next.js"] },
] as const;

export function groupSkillNames(names: string[]): SkillGroup[] {
  const groups = new Map<string, string[]>();
  for (const name of names) {
    const trimmed = name.trim();
    if (!trimmed) continue;
    const category = categories.find(({ terms }) => terms.some((term) => trimmed.toLocaleLowerCase().includes(term)));
    const label = category?.label ?? "其他技能";
    if (!groups.has(label)) groups.set(label, []);
    if (!groups.get(label)!.includes(trimmed)) groups.get(label)!.push(trimmed);
  }
  return ["产品能力", "AI 产品能力", "技术与工具", "语言能力", "其他技能"]
    .filter((label) => groups.has(label))
    .map((label) => ({ label, items: groups.get(label)! }));
}
