import {
  canEnterStep,
  workflowCompletion,
  workflowHref,
  WORKFLOW_STEPS,
} from "./workflow-state.ts";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import type { Route } from "next";

export type StepIndicatorState = {
  step: WorkflowStep;
  label: string;
  complete: boolean;
  current: boolean;
};

const STEP_LABELS: Record<WorkflowStep, string> = {
  profile: "Profile",
  preferences: "Career Preferences",
  "role-exploration": "Role Selection",
  "job-descriptions": "Job Descriptions",
  "market-profile": "Market Profile",
  "gap-analysis": "Gap Analysis",
  priorities: "Priorities",
  roadmap: "4-Week Roadmap",
  progress: "Progress",
  dashboard: "Dashboard",
};

const NEXT_LABELS: Record<WorkflowStep, string | null> = {
  profile: "确认并继续",
  preferences: "保存并探索岗位",
  "role-exploration": "进入岗位 JD",
  "job-descriptions": "生成市场画像",
  "market-profile": "生成差距分析",
  "gap-analysis": "确认优先级",
  priorities: "生成四周计划",
  roadmap: "查看进度",
  progress: "打开 Dashboard",
  dashboard: null,
};

export function stepLabel(step: WorkflowStep): string {
  return STEP_LABELS[step];
}

export function stepNavigation(
  profileId: string,
  step: WorkflowStep,
): { previous: Route | null; next: Route | null; nextLabel: string | null } {
  const index = WORKFLOW_STEPS.indexOf(step);
  const previousStep = index > 0 ? WORKFLOW_STEPS[index - 1] : null;
  const nextStep = index >= 0 && index < WORKFLOW_STEPS.length - 1 ? WORKFLOW_STEPS[index + 1] : null;
  return {
    previous: previousStep ? workflowHref(profileId, previousStep) : null,
    next: nextStep ? workflowHref(profileId, nextStep) : null,
    nextLabel: NEXT_LABELS[step],
  };
}

export function canNavigateNext(snapshot: WorkflowSnapshot, step: WorkflowStep): boolean {
  if (step === "dashboard") return false;
  return workflowCompletion(snapshot)[step] && canEnterStep(snapshot, step);
}

export function stepIndicatorState(
  snapshot: WorkflowSnapshot,
  currentStep: WorkflowStep,
): StepIndicatorState[] {
  const completion = workflowCompletion(snapshot);
  return WORKFLOW_STEPS.map((step) => ({
    step,
    label: stepLabel(step),
    complete: completion[step] && step !== currentStep,
    current: step === currentStep,
  }));
}

export function stepNumber(step: WorkflowStep): number {
  return WORKFLOW_STEPS.indexOf(step) + 1;
}
