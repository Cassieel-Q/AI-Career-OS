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
  "role-exploration": "Role Exploration",
  "target-role": "Target Role",
  "job-descriptions": "Job Descriptions",
};

const NEXT_LABELS: Record<WorkflowStep, string | null> = {
  profile: "确认并继续",
  preferences: "保存并探索岗位",
  "role-exploration": "选择目标岗位",
  "target-role": "确认目标岗位",
  "job-descriptions": null,
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
  if (step === "job-descriptions") return false;
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
