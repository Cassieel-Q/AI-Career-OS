"use client";

import { JobDescriptionsStep } from "./job-descriptions-step.tsx";
import { PreferencesStep } from "./preferences-step.tsx";
import { ProfileStep } from "./profile-step.tsx";
import { RoleExplorationStep } from "./role-exploration-step.tsx";
import { WorkflowRoute } from "./workflow-route.tsx";
import type { WorkflowSnapshot, WorkflowStep } from "./workflow-state.ts";
import type { WorkflowStepControls } from "./workflow-route.tsx";
import {
  DashboardStep,
  GapAnalysisStep,
  MarketProfileStep,
  PrioritiesStep,
  ProgressStep,
  RoadmapStep,
} from "./p0-steps.tsx";

type DynamicWorkflowStep = Exclude<WorkflowStep, "start">;

export function WorkflowPage({ profileId, currentStep }: { profileId: string; currentStep: DynamicWorkflowStep }) {
  return (
    <WorkflowRoute
      profileId={profileId}
      currentStep={currentStep}
      renderStep={(snapshot, controls) => renderWorkflowStep(profileId, currentStep, snapshot, controls)}
    />
  );
}

function renderWorkflowStep(profileId: string, step: DynamicWorkflowStep, snapshot: WorkflowSnapshot, controls: WorkflowStepControls) {
  if (step === "profile") {
    return snapshot.profile ? <ProfileStep profile={snapshot.profile} controls={controls} /> : null;
  }
  if (step === "preferences") {
    return snapshot.profile ? <PreferencesStep profile={snapshot.profile} controls={controls} /> : null;
  }
  if (step === "role-exploration") {
    return <RoleExplorationStep snapshot={snapshot} controls={controls} />;
  }
  if (step === "job-descriptions") return <JobDescriptionsStep profileId={profileId} snapshot={snapshot} controls={controls} />;
  if (step === "market-profile") return <MarketProfileStep snapshot={snapshot} controls={controls} />;
  if (step === "gap-analysis") return <GapAnalysisStep snapshot={snapshot} controls={controls} />;
  if (step === "priorities") return <PrioritiesStep snapshot={snapshot} controls={controls} />;
  if (step === "roadmap") return <RoadmapStep snapshot={snapshot} controls={controls} />;
  if (step === "progress") return <ProgressStep snapshot={snapshot} controls={controls} />;
  return <DashboardStep snapshot={snapshot} controls={controls} />;
}
