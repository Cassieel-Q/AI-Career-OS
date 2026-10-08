export type ResumeBulletDecision = "SUGGESTED" | "ACCEPTED" | "EDITED" | "REJECTED";

export function factConfirmationPatch(): { fact_confirmed: true; status: "SUGGESTED" } {
  return { fact_confirmed: true, status: "SUGGESTED" };
}

export function isChosenRewrite(status: string): boolean {
  return status === "ACCEPTED" || status === "EDITED";
}

export function resumeDecisionProgress(bullets: Array<{ status: string }>): { decided: number; total: number } {
  return { decided: bullets.filter((item) => item.status !== "SUGGESTED").length, total: bullets.length };
}
